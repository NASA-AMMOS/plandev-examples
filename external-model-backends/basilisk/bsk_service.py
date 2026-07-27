#!/usr/bin/env python3
"""BASILISK external-model backend for PlanDev — a real astrodynamics simulator as a mission model.

Third adapter on the same wire contract, after Blackbird (a JVM discrete-event simulator) and the
toy Python battery. Where those two show the contract is language-neutral, this one shows it carries
a physics engine: SPICE ephemerides, eclipse geometry, a solar array that follows the true sun angle,
a battery, a data recorder, and a downlink that only moves bits while a ground station is above the
horizon. `bsk_model.py` holds all of that; this file is the contract.

Everything generic -- HTTP, routing, ValueSchema typechecking, defaults, the identity hash, response
validation -- comes from `adapter_core`, shared with the other two adapters. What is left is the
three things Basilisk specifically needs:

  1. The DECLARATION: activity types, resources, configuration.
  2. Reducing overlapping directives to a piecewise-constant KNOB TIMELINE, so two concurrent
     observations sum rather than one silently overwriting the other.
  3. QUANTIZATION. Basilisk is a fixed-step integrator and PlanDev's timeline is microsecond
     resolution, so the two clocks genuinely disagree and every failure mode is silent. This is the
     hard part, and the reason the adapter is more than a declaration. The sample-to-segment half of
     it is generic and lives in `adapter_core` (`snap_up`, `real_segments`, `discrete_segments`);
     what is here is the activity half -- see `_place`.

Endpoints (see adapter_core for the full contract):
  GET  /models                 -> {models:[{key,name,version,identityHash}]}
  GET|POST /introspect         -> {activityTypes, resourceTypes, parameters, identityHash}
  POST /simulate               -> {realProfiles, discreteProfiles, spans}
  POST /validate               -> {results:[{valid, notices, effectiveArguments}]}

Run:  python3 bsk_service.py [port]
"""
import os
import sys
import threading

# adapter_core sits one directory up in the repo and NEXT TO this file inside the container image
# (the Dockerfile copies it in). Appending -- not inserting -- the repo root keeps the co-located
# copy winning when there is one, so the image always runs the module it shipped with.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter_core                                                             # noqa: E402
from adapter_core import (ActivityType, BadRequest, Declaration,                # noqa: E402
                          Parameter, ResourceType)

from bsk_model import BASILISK_VERSION, KNOBS, ConfigError, Spacecraft          # noqa: E402

MODEL_KEY, MODEL_NAME, MODEL_VERSION = "orbiter", "orbiter", "1.0.0"
US_PER_S = 1_000_000

#: A fat-finger guard, not a policy cap. A week-long plan at the default 5-second step is 120 960
#: steps; this allows eighty times that. What it stops is `timeStepSeconds: 0.001` on that same
#: plan -- 604 million steps, which is an OOM kill with no diagnosis, half an hour later. The message
#: names the knob, because the fix is always the same one.
MAX_SAMPLES = 10_000_000

REAL = {"type": "real"}

# --- declaration ------------------------------------------------------------------------------------
# Activity parameters, in order. Order is load-bearing: PlanDev persists each parameter's index and
# plandev-ui lays the argument form out in it.
ACTIVITIES = {
    "Observe": [("duration",   {"type": "duration"}, None),
                ("baudRate",   REAL,                 12.0e6),
                ("powerWatts", REAL,                 55.0)],
    "Downlink": [("duration",   {"type": "duration"}, None),
                 ("baudRate",   REAL,                 8.0e6),
                 ("powerWatts", REAL,                 78.0)],
}

#: What each activity does to the spacecraft, as a knob fed from one of its arguments. The adapter
#: sums these across every directive live at a given instant, which is what makes overlap mean
#: something physical: two Observes are two instruments, not one at the second one's baud rate.
KNOB_CONTRIBUTIONS = {
    "Observe":  {"instrumentBaudRate": "baudRate",  "instrumentPowerWatts": "powerWatts"},
    "Downlink": {"transmitterBaudRate": "baudRate", "transmitterPowerWatts": "powerWatts"},
}

#: Values the model DERIVED, as opposed to arguments it was handed. Every one is read back out of the
#: recorded telemetry over the span's own window, so they say what happened rather than restating the
#: request. `accessFraction` is the one that earns its place: a Downlink scheduled while the ground
#: station is below the horizon comes back with accessFraction 0.0 and no bits moved.
COMPUTED = {
    "Observe": {"type": "struct", "items": {
        "minStateOfCharge":     REAL,
        "meanSunlightFraction": REAL,
        "storedBitsAtEnd":      REAL}},
    "Downlink": {"type": "struct", "items": {
        "accessFraction":      REAL,
        "netStoredBitsChange": REAL,
        "minStateOfCharge":    REAL}},
}

CONFIG = [
    # The integration grid. Exposed rather than hidden because it is an honest property of a
    # fixed-step integrator: it sets the resolution of every profile and the precision to which an
    # activity's start time can be honoured.
    ("timeStepSeconds",              REAL, 5.0),
    # Orbit, as classical elements at the plan's start epoch.
    ("semiMajorAxisKm",              REAL, 7000.0),
    ("eccentricity",                 REAL, 0.0001),
    ("inclinationDeg",               REAL, 33.3),
    ("rightAscensionDeg",            REAL, 48.2),
    ("argumentOfPeriapsisDeg",       REAL, 347.8),
    ("trueAnomalyDeg",               REAL, 85.3),
    # Power.
    ("solarPanelAreaSquareMeters",   REAL, 0.4),
    ("solarPanelEfficiency",         REAL, 0.29),
    ("batteryCapacityWattHours",     REAL, 120.0),
    ("initialChargeFraction",        REAL, 0.8),
    ("busPowerWatts",                REAL, 45.0),
    # Data. 50 Gb of solid-state recorder: enough that the default instrument does not saturate it
    # in the first ten minutes, which would make every subsequent Observe a no-op.
    ("dataCapacityBits",             REAL, 50.0e9),
    # Ground station. Defaults are Goldstone DSS-14.
    ("groundStationLatitudeDeg",     REAL, 35.4267),
    ("groundStationLongitudeDeg",    REAL, -116.89),
    ("groundStationAltitudeMeters",  REAL, 1001.0),
    ("groundStationMinElevationDeg", REAL, 10.0),
]

#: Resource names are the model's business, not PlanDev's -- the Blackbird adapter reports
#: Blackbird's dotted names, this one reports paths, and merlin stores both without caring.
REAL_RESOURCES = {
    "/power/solarArrayWatts":       REAL,
    "/power/netWatts":              REAL,
    "/power/battery/wattHours":     REAL,
    "/power/battery/stateOfCharge": REAL,
    "/data/storedBits":             REAL,
    "/geometry/sunlightFraction":   REAL,
    "/geometry/altitudeKm":         REAL,
}


def _variant(*labels):
    return {"type": "variant", "variants": [{"key": k, "label": k} for k in labels]}


DISCRETE_RESOURCES = {
    "/geometry/eclipse":         _variant("Sunlight", "Penumbra", "Umbra"),
    "/comm/groundStationInView": {"type": "boolean"},
    "/instrument/mode":          _variant("Idle", "Imaging"),
    "/comm/transmitterMode":     _variant("Idle", "Transmitting"),
}

#: Which recorded channel feeds which resource; `bsk_model.channels` already did the unit conversion.
#: The two mode resources are absent on purpose -- they come from the commanded timeline, not from
#: telemetry (see `_timeline_segments`).
CHANNEL_FOR_RESOURCE = {
    "/power/solarArrayWatts":       "solarArrayWatts",
    "/power/netWatts":              "netPowerWatts",
    "/power/battery/wattHours":     "batteryWattHours",
    "/power/battery/stateOfCharge": "stateOfCharge",
    "/data/storedBits":             "storedBits",
    "/geometry/sunlightFraction":   "sunlightFraction",
    "/geometry/altitudeKm":         "altitudeKm",
    "/geometry/eclipse":            "eclipseState",
    "/comm/groundStationInView":    "groundStationInView",
}

#: Commanded-mode resources: (resource, knob, off label, on label).
TIMELINE_RESOURCES = (
    ("/instrument/mode",      "instrumentBaudRate",  "Idle", "Imaging"),
    ("/comm/transmitterMode", "transmitterBaudRate", "Idle", "Transmitting"),
)


def declaration():
    """Built from the tables above, per call. Reading them live rather than caching keeps
    `identity_hash()` honest for anything that edits them -- the identity tests do exactly that."""
    return Declaration(
        key=MODEL_KEY, name=MODEL_NAME, version=MODEL_VERSION,
        activity_types=[
            ActivityType(name=typ,
                         parameters=[Parameter(n, s, d) for n, s, d in params],
                         computed_attributes_schema=COMPUTED[typ])
            for typ, params in ACTIVITIES.items()],
        resource_types=[ResourceType(n, s) for n, s in
                        list(REAL_RESOURCES.items()) + list(DISCRETE_RESOURCES.items())],
        config_parameters=[Parameter(n, s, d) for n, s, d in CONFIG],
        # A pure simulator, and a fast one: a 24-hour plan runs in well under a second, so the full
        # re-simulation that PlanDev's scheduler pays per placement is affordable here in a way it
        # would not be for a backend with a heavy per-run cost.
        capabilities={adapter_core.PLANDEV_SCHEDULING: adapter_core.supported()})


# --- quantization -------------------------------------------------------------------------------
# The sample-to-segment conversion itself is generic to any fixed-step simulator and lives in
# adapter_core: `snap_up` (ceil onto the grid), `real_segments` (secant rates, final segment extended
# to close the window) and `discrete_segments`. What stays here is the part that is about Basilisk
# and about activities.
def _timeline_segments(timeline, sim_duration_us, knob, off_label, on_label):
    """A commanded-mode profile, taken from the knob timeline rather than from telemetry.

    Deliberately what was COMMANDED, not what physically happened: `/comm/transmitterMode` reads
    Transmitting whether or not the ground station was above the horizon. Pairing it with
    `/comm/groundStationInView` is what lets a PlanDev constraint state the rule -- never transmit
    out of view -- over two resources, with no span query and no knowledge of this model.
    """
    segments = []
    for index, (start_us, knobs) in enumerate(timeline):
        end_us = timeline[index + 1][0] if index + 1 < len(timeline) else sim_duration_us
        if end_us > start_us:
            segments.append({"duration": end_us - start_us,
                             "dynamics": on_label if knobs[knob] > 0.0 else off_label})
    return adapter_core.coalesce_discrete(segments)


def knob_timeline(activities, last_step_us):
    """Overlapping activities -> `[(time_us, {knob: total}), ...]`, one entry per instant the totals
    change.

    Summing at each edge, rather than emitting an on and an off event per activity, is what makes
    concurrency mean something: two Observes at once draw both instruments' power and fill the
    recorder at the combined baud rate. Per-activity toggles would let the first one's "off" switch
    the second one off too -- the class of bug a plan only exhibits once someone happens to overlap
    two activities.
    """
    edges = {0}
    for activity in activities:
        edges.add(activity["start"])
        if activity["end"] <= last_step_us:
            edges.add(activity["end"])
    timeline = []
    for time_us in sorted(e for e in edges if e <= last_step_us):
        totals = {knob: 0.0 for knob in KNOBS}
        for activity in activities:
            if activity["start"] <= time_us < activity["end"]:
                for knob, argument_value in activity["knobs"].items():
                    totals[knob] += argument_value
        # An edge where nothing actually changed -- one activity ending exactly as an identical one
        # begins -- is a Basilisk event that would do no work; dropping it also keeps the mode
        # profiles free of zero-information segment boundaries.
        if not timeline or timeline[-1][1] != totals:
            timeline.append((time_us, totals))
    return timeline


# --- backend ----------------------------------------------------------------------------------------
class OrbiterBackend(adapter_core.Backend):
    """adapter_core hands `simulate` a request that is already normalized: the configuration is
    resolved and typechecked, and every directive has a known type, all its required parameters,
    defaults filled in and every argument checked against its schema."""

    def __init__(self):
        # Basilisk registers its modules with a process-wide C++ messaging system, so two
        # simulations in one process corrupt each other's state rather than merely running slowly.
        # adapter_core serves on a ThreadingHTTPServer, so this lock is not optional. Simulations are
        # fast -- a 24-hour plan is well under a second -- so serializing them costs little, and a
        # deployment needing real concurrency runs more replicas, which is the honest answer anyway.
        self._lock = threading.Lock()

    def declaration(self):
        return declaration()

    def deep_validate(self, subjects):
        """Per-parameter semantic checks no ValueSchema can express. These carry `subjects`, so they
        render on the offending field rather than as a whole-activity message."""
        notices = []
        for subject in subjects:
            found = []
            for name in ("baudRate", "powerWatts"):
                value = subject.arguments.get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
                    found.append({"subjects": [name],
                                  "message": "'%s' must be >= 0 (got %s)" % (name, value)})
            duration = subject.arguments.get("duration")
            if isinstance(duration, int) and not isinstance(duration, bool) and duration <= 0:
                found.append({"subjects": ["duration"],
                              "message": "'duration' must be > 0 (got %d)" % duration})
            notices.append(found)
        return notices

    def simulate(self, request):
        with self._lock:
            return self._simulate(request)

    def _simulate(self, request):
        sim_duration_us = request.duration
        if sim_duration_us <= 0:
            raise BadRequest("simulation duration must be positive, got %dus" % sim_duration_us)

        try:
            vehicle = Spacecraft(request.configuration, request.plan_start)
        except ConfigError as e:
            raise BadRequest(str(e))
        step_us = vehicle.step_us

        # The last grid point Basilisk will actually reach. Anything past it -- an event, an
        # activity's end -- simply never happens during this run.
        last_step_us = (sim_duration_us // step_us) * step_us
        steps = last_step_us // step_us + 1
        if steps > MAX_SAMPLES:
            raise BadRequest(
                "a %.1f-hour plan at timeStepSeconds=%s is %d integration steps, past this "
                "adapter's %d-step ceiling; raise timeStepSeconds"
                % (sim_duration_us / US_PER_S / 3600.0,
                   request.configuration["timeStepSeconds"], steps, MAX_SAMPLES))

        activities, spans = self._place(request.directives, step_us, last_step_us)
        timeline = knob_timeline(activities, last_step_us)

        try:
            vehicle.schedule(timeline)
            vehicle.run(sim_duration_us)
            times_us = vehicle.times_us
            channels = vehicle.channels
        except ConfigError as e:
            raise BadRequest(str(e))
        if not times_us:
            raise adapter_core.ModelError(
                "Basilisk recorded no samples for a %dus simulation at a %dus step"
                % (sim_duration_us, step_us))

        self._attach_computed(spans, channels, step_us, len(times_us) - 1)

        real_profiles = {
            name: {"schema": schema,
                   "segments": adapter_core.real_segments(times_us, channels[CHANNEL_FOR_RESOURCE[name]],
                                              sim_duration_us)}
            for name, schema in REAL_RESOURCES.items()}
        discrete_profiles = {
            name: {"schema": schema,
                   "segments": adapter_core.discrete_segments(times_us, channels[CHANNEL_FOR_RESOURCE[name]],
                                                  sim_duration_us)}
            for name, schema in DISCRETE_RESOURCES.items() if name in CHANNEL_FOR_RESOURCE}
        for name, knob, off_label, on_label in TIMELINE_RESOURCES:
            discrete_profiles[name] = {
                "schema": DISCRETE_RESOURCES[name],
                "segments": _timeline_segments(timeline, sim_duration_us, knob,
                                               off_label, on_label)}

        return {"realProfiles": real_profiles,
                "discreteProfiles": discrete_profiles,
                "spans": spans}

    def _place(self, directives, step_us, last_step_us):
        """Snap every directive onto the integration grid and build its span.

        The span reports the SNAPPED offsets, not the requested ones. Reporting what was asked for
        while simulating something else is the quantization bug in its purest form: the timeline
        would show an observation starting at 00:10:03 while the power profile shows the draw
        beginning at 00:10:05, and nothing would say why.
        """
        activities, spans = [], []
        for directive in directives:
            if directive.start_offset < 0:
                raise BadRequest("directive %s (%s) starts %dus before the plan"
                                 % (directive.id, directive.type, -directive.start_offset))
            duration_us = int(directive.arguments["duration"])
            if duration_us <= 0:
                raise BadRequest("directive %s (%s) has duration %dus; it must be positive"
                                 % (directive.id, directive.type, duration_us))
            start_us = adapter_core.snap_up(directive.start_offset, step_us)
            end_us = adapter_core.snap_up(directive.start_offset + duration_us, step_us)
            # Out-of-window first: an activity that begins past the last step Basilisk reaches is
            # simply not this simulation's business, and complaining about its duration instead
            # would be answering a question nobody asked.
            if start_us > last_step_us:
                continue
            if duration_us < step_us:
                # An activity shorter than one integration step cannot be represented at all, and
                # WHICH way it fails depends on nothing the planner controls: land it between two
                # steps and both edges snap to the same instant, so it does nothing; land it on a
                # step and it stretches to a full one, so it does five times what was asked. Either
                # would be recorded as if it were what the plan said. Refusing both is the only
                # answer that is the same answer, and the knob that fixes it is in the
                # configuration -- so the message names it.
                raise BadRequest(
                    "directive %s (%s) lasts %dus, shorter than the %dus integration step -- the "
                    "simulator cannot represent it, and running it anyway would either do nothing "
                    "or stretch it to a whole step. Lengthen it, or lower timeStepSeconds."
                    % (directive.id, directive.type, duration_us, step_us))
            activities.append({
                "start": start_us, "end": end_us,
                "knobs": {knob: float(directive.arguments[argument])
                          for knob, argument in KNOB_CONTRIBUTIONS[directive.type].items()}})

            span = {"spanId": len(spans) + 1, "type": directive.type, "startOffset": start_us,
                    "arguments": directive.arguments, "parentId": None, "directiveId": directive.id}
            # An activity whose end lands past the last grid point never has its "off" event fire, so
            # it genuinely is still running when the simulation ends. PlanDev models that directly --
            # a span with no duration -- and clamping to the window edge instead would be a different
            # and false claim. (`end_us` is a grid multiple, so `end_us > last_step_us` is equivalent
            # to `end_us > sim_duration_us`, which is also the ingest gate's rule.)
            if end_us <= last_step_us:
                span["duration"] = end_us - start_us
            spans.append(span)
        return activities, spans

    def _attach_computed(self, spans, channels, step_us, last_index):
        """Read each finished span's computed attributes back out of the recorded telemetry.

        Only finished spans get them: an unfinished activity has not produced its final values, and
        merlin tells the two apart by whether a span carries BOTH a duration and computed attributes
        (PostgresResultsCellRepository). Attaching them to an unfinished span reads to merlin as
        finished-with-no-end.
        """
        for span in spans:
            if "duration" not in span:
                continue
            # The grid starts at 0 and is uniform, so a snapped offset indexes the samples directly.
            lo = min(span["startOffset"] // step_us, last_index)
            hi = min((span["startOffset"] + span["duration"]) // step_us, last_index)
            window = slice(lo, hi + 1)
            charge = channels["stateOfCharge"][window]
            if span["type"] == "Observe":
                sunlight = channels["sunlightFraction"][window]
                span["computedAttributes"] = {
                    "minStateOfCharge": float(min(charge)),
                    "meanSunlightFraction": float(sum(sunlight) / len(sunlight)),
                    "storedBitsAtEnd": float(channels["storedBits"][hi])}
            else:
                access = [1.0 if a else 0.0 for a in channels["groundStationInView"][window]]
                span["computedAttributes"] = {
                    "accessFraction": float(sum(access) / len(access)),
                    "netStoredBitsChange": float(channels["storedBits"][hi]
                                                 - channels["storedBits"][lo]),
                    "minStateOfCharge": float(min(charge))}


BACKEND = OrbiterBackend()


# --- module-level entry points ------------------------------------------------------------------
# Thin wrappers over adapter_core so the tests and the server exercise the same code path -- a
# second, "convenient" implementation next to the real one is exactly how the typechecking gap that
# prompted adapter_core opened up in the first place.
def effective_args(typ, args):
    return declaration().effective_args(typ, args)


def effective_config(configuration):
    return declaration().effective_config(configuration)


def validate_one(typ, args, effective_only=False):
    return adapter_core.run_validate(
        BACKEND, {"activities": [{"type": typ, "arguments": args}],
                  "effectiveOnly": effective_only})["results"][0]


def simulate(req):
    return adapter_core.run_simulate(BACKEND, req)


def identity_hash():
    return declaration().identity_hash()


def introspect():
    return declaration().introspect()


def models_list():
    return adapter_core.Registry({MODEL_KEY: BACKEND}).models_list()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5021
    adapter_core.serve(
        {MODEL_KEY: BACKEND}, port,
        banner="Basilisk orbiter backend on :%d  (Basilisk %s, activity types: %d, resources: %d, "
               "id=%s)" % (port, BASILISK_VERSION, len(ACTIVITIES),
                           len(REAL_RESOURCES) + len(DISCRETE_RESOURCES), identity_hash()))
