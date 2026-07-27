#!/usr/bin/env python3
"""Minimal PYTHON external-model backend for PlanDev — proof that the `external` wire contract is
language-neutral (same contract the Blackbird adapter speaks; Merlin needs zero new code).

This is an Archetype-A "pure simulator": simulate(directives) -> profiles + spans, with no internal
scheduling (PlanDev's own scheduler could drive it as an oracle).

Model: a toy spacecraft BATTERY.
  Resources: SoC (real, LINEAR — a genuine rate-based profile, which Blackbird's constant reals can't show),
             Mode (variant: Idle | Charging | Discharging), Cycles (int).
  Activities: Charge(duration, rate=1.0/s), Discharge(duration, load=2.0/s).

Everything that is not about batteries — HTTP, routing, `?model=` resolution, ValueSchema
typechecking, default resolution, the identity hash, response validation — lives in
`adapter_core`, which the Blackbird adapter shares. What is left here is the declaration tables and
one `simulate`.

Endpoints (see adapter_core for the full contract; `?model=` is optional but, if given, must match):
  GET  /models                 -> {models:[{key,name,version,identityHash}]}
  GET|POST /introspect         -> {activityTypes, resourceTypes, parameters, identityHash}
  POST /simulate   {planStart, duration(us), configuration, directives:[{id,type,startOffset(us),arguments}]}
                -> {realProfiles, discreteProfiles, spans}
  POST /validate   {activities:[{type,arguments}], effectiveOnly}
                -> {results:[{valid, notices:[{subjects,message}], effectiveArguments}]}

Run:  python3 py_model_server.py [port]   (stdlib only)
"""
import os
import sys

# adapter_core sits one directory up in the repo and NEXT TO this file inside the container image
# (the Dockerfile copies it in). Appending -- not inserting -- the repo root keeps the co-located
# copy winning when there is one, so the image always runs the module it shipped with.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter_core                                                            # noqa: E402
from adapter_core import (ActivityType, BadRequest, Declaration,               # noqa: E402,F401
                          Parameter, ResourceType, nonconformance)

MODEL_KEY, MODEL_NAME, MODEL_VERSION = "battery", "battery", "1.0.0"
US_PER_S = 1_000_000

# --- model definition (types + defaults + per-parameter validation) --------------------------------
# Each activity: params as (name, valueSchema, default-or-None). None default => required.
MODEL = {
    "Charge":    [("duration", {"type": "duration"}, None),
                  ("rate",     {"type": "real"},     1.0)],
    "Discharge": [("duration", {"type": "duration"}, None),
                  ("load",     {"type": "real"},     2.0)],
}
# Simulation configuration: model-wide settings a planner edits per plan, distinct from an activity's
# arguments. PlanDev stores these in mission_model_parameters and sends them as `configuration`.
CONFIG = [
    ("initialSoC",    {"type": "real"}, 50.0),
    ("initialCycles", {"type": "int"},  0),
]
COMPUTED_ATTRIBUTES_SCHEMA = {"type": "struct", "items": {"socDelta": {"type": "real"}}}
RESOURCE_TYPES = {
    "SoC":    {"type": "real"},
    "Mode":   {"type": "variant", "variants": [{"key": k, "label": k} for k in ("Idle", "Charging", "Discharging")]},
    "Cycles": {"type": "int"},
}


# --- declaration -----------------------------------------------------------------------------------
def _published_digest_payload(decl):
    """The exact bytes this model's PUBLISHED identityHash was minted from.

    adapter_core has a canonical payload (`Declaration.digest_payload`) that a new model should use.
    This one is pinned because the battery model has already shipped: merlin STORES the hash as an
    attestation that it introspected the model it is about to simulate, so re-shaping the payload
    would invalidate every deployment without a single thing about the model having moved. The
    canonical payload covers strictly more, so switching to it is a real (and one-day worthwhile)
    migration, not a tidy-up.

    What it covers, and why each part is in it:
      * activity parameters in DECLARATION ORDER, with their defaults. Order is not cosmetic --
        merlin assigns each parameter an `order` from its index in the introspection array
        (ResponseSerializers.serializeParameters), persists it, reads activity types back sorted by
        it (GetActivityTypesAction), and plandev-ui lays the argument form out in that order.
        Defaults carry required-ness, which merlin persists in activity_type and its gate enforces:
        flipping a parameter between required and optional changes what PlanDev believes without
        changing any schema.
      * resource schemas, and the configuration parameters PlanDev stores in
        mission_model_parameters.
      * the computed-attributes schema, stored in activity_type -- if it drifts, the gate starts
        rejecting spans against a stale schema.
    """
    return {
        "acts": {a.name: [[p.name, p.schema, p.default] for p in a.parameters]
                 for a in decl.activity_types},
        "res": {r.name: r.schema for r in decl.resource_types},
        "params": [[p.name, p.schema, p.default] for p in decl.config_parameters],
        "computed": COMPUTED_ATTRIBUTES_SCHEMA,
    }


def declaration():
    """Build the Declaration from the tables above.

    Rebuilt per call rather than cached: the tables ARE the model here, and reading them live keeps
    `identity_hash()` honest for anything that edits them (the identity-hash tests do exactly that,
    and a cached declaration would report the old hash for the new model).
    """
    return Declaration(
        key=MODEL_KEY, name=MODEL_NAME, version=MODEL_VERSION,
        activity_types=[
            ActivityType(name=typ,
                         parameters=[Parameter(n, s, d) for n, s, d in params],
                         computed_attributes_schema=COMPUTED_ATTRIBUTES_SCHEMA)
            for typ, params in MODEL.items()],
        resource_types=[ResourceType(n, s) for n, s in RESOURCE_TYPES.items()],
        config_parameters=[Parameter(n, s, d) for n, s, d in CONFIG],
        digest_payload=_published_digest_payload)


# --- simulation ------------------------------------------------------------------------------------
class BatteryBackend(adapter_core.Backend):
    """The battery itself. adapter_core hands `simulate` a request that is already normalized:
    the configuration is resolved and typechecked, and every directive has a known type, all its
    required parameters, defaults filled in and every argument checked against its schema."""

    def declaration(self):
        return declaration()

    def deep_validate(self, subjects):
        """Per-parameter SEMANTIC checks -- the ones no schema can express.

        Unlike Blackbird, a Python model CAN attribute an error to a specific parameter, so these
        carry `subjects` and render inline on that field in the UI. They run even for an activity
        that already has notices: a half-filled form should light up everything that is wrong at
        once, not one problem per round trip.
        """
        out = []
        for subject in subjects:
            notices = []
            args = subject.arguments
            for pname in ("rate", "load"):
                v = args.get(pname)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and v <= 0:
                    notices.append({"subjects": [pname],
                                    "message": "'%s' must be > 0 (got %s)" % (pname, v)})
            v = args.get("duration")
            if isinstance(v, int) and not isinstance(v, bool) and v < 0:
                notices.append({"subjects": ["duration"],
                                "message": "'duration' must be >= 0 (got %d)" % v})
            out.append(notices)
        return out

    def simulate(self, request):
        sim_dur = request.duration
        cfg = request.configuration

        # Resolve every directive to an absolute half-open window [start, end) clamped into the
        # simulation, BEFORE any profile is built. Everything downstream then works in absolute
        # offsets.
        acts, spans = [], []
        for d in request.directives:
            eff = d.arguments
            start, dur = d.start_offset, int(eff["duration"])
            if dur < 0:
                raise BadRequest("directive %s (%s) has negative duration %d" % (d.id, d.type, dur))
            if start >= sim_dur:
                continue                               # begins after the window; contributes nothing
            # Belt-and-braces; the real clamping is the breakpoint filter below, which drops anything
            # outside [0, sim_dur]. Kept so `end` is meaningful on its own.
            end = min(start + dur, sim_dur)
            rate = float(eff["rate"]) if d.type == "Charge" else -float(eff["load"])
            acts.append({"start": start, "end": end, "rate": rate, "type": d.type})
            # An activity still running when the simulation ended is reported UNFINISHED --
            # `duration` omitted -- rather than clamped. Clamping would claim it ended at the window
            # edge, which is a different and false statement; PlanDev models this state directly and
            # stores the span with a null end. Arguments are the coerced effective ones, not a raw
            # echo of the request.
            span = {"spanId": len(spans) + 1, "type": d.type, "startOffset": start,
                    "arguments": eff, "parentId": None, "directiveId": d.id}
            if start + dur <= sim_dur:
                span["duration"] = dur
                # Computed attributes are values the model DERIVED, as opposed to arguments it was
                # given. socDelta is the charge this activity moved. Only finished spans get them: an
                # unfinished activity has not produced its final values, and
                # PostgresResultsCellRepository uses the presence of computed attributes as part of
                # how it tells the two apart. (Which also means this only ever runs when
                # end == start + dur, so it is not doing truncation arithmetic -- an earlier comment
                # here claimed it was.)
                span["computedAttributes"] = {"socDelta": rate * ((end - start) / US_PER_S)}
            spans.append(span)

        # Build the profile from a breakpoint timeline rather than a running cursor. A cursor cannot
        # express overlap -- and for a battery, a Charge overlapping a Discharge is the ordinary
        # case, not an edge case. The old cursor appended each activity's segment wherever the cursor
        # happened to be, so the SECOND of two overlapping activities landed at a cumulative offset
        # later than its own span said it ran, and the profile silently disagreed with the timeline.
        # Deriving segments from sorted absolute breakpoints makes cumulative segment offsets equal
        # wall-clock offsets by construction, and makes the result independent of the order
        # directives arrive in.
        points = {0, sim_dur}
        for a in acts:
            points.add(a["start"]); points.add(a["end"])
        breaks = sorted(p for p in points if 0 <= p <= sim_dur)

        real_segs, mode_segs, cyc_segs = [], [], []
        soc, cycles = cfg["initialSoC"], cfg["initialCycles"]
        for lo, hi in zip(breaks, breaks[1:]):
            if hi <= lo:
                continue
            active = [a for a in acts if a["start"] <= lo < a["end"]]
            rate = float(sum(a["rate"] for a in active))   # concurrent effects superpose
            cycles = cfg["initialCycles"] + sum(1 for a in acts if a["type"] == "Charge" and a["start"] <= lo)
            mode = "Charging" if rate > 0 else "Discharging" if rate < 0 else "Idle"
            dur = hi - lo
            real_segs.append({"duration": dur, "dynamics": {"initial": soc, "rate": rate}})
            mode_segs.append({"duration": dur, "dynamics": mode})
            cyc_segs.append({"duration": dur, "dynamics": cycles})
            soc += rate * (dur / US_PER_S)

        return {
            "realProfiles":     {"SoC": {"schema": RESOURCE_TYPES["SoC"], "segments": real_segs}},
            "discreteProfiles": {"Mode":   {"schema": RESOURCE_TYPES["Mode"],   "segments": mode_segs},
                                 "Cycles": {"schema": RESOURCE_TYPES["Cycles"], "segments": cyc_segs}},
            "spans": spans,
        }


BACKEND = BatteryBackend()


# --- module-level entry points ----------------------------------------------------------------------
# Thin wrappers over adapter_core so that what the tests call and what the server serves are the
# same code path -- a second, "convenient" implementation next to the real one is exactly how the
# typechecking gap that prompted adapter_core opened up in the first place.
def effective_args(typ, args):
    return declaration().effective_args(typ, args)


def undeclared(typ, args):
    return declaration().undeclared(typ, args)


def effective_config(configuration):
    return declaration().effective_config(configuration)


def validate_one(typ, args, effective_only=False):
    return adapter_core.run_validate(
        BACKEND, {"activities": [{"type": typ, "arguments": args}],
                  "effectiveOnly": effective_only})["results"][0]


def simulate(req):
    return BACKEND.simulate(declaration().normalize(req))


def identity_hash():
    return declaration().identity_hash()


def introspect():
    return declaration().introspect()


def models_list():
    return adapter_core.Registry({MODEL_KEY: BACKEND}).models_list()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5002
    adapter_core.serve(
        {MODEL_KEY: BACKEND}, port,
        banner="Python battery model backend on :%d  (activity types: %d, resources: %d, id=%s)"
               % (port, len(MODEL), len(RESOURCE_TYPES), identity_hash()))
