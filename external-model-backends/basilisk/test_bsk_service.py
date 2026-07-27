#!/usr/bin/env python3
"""Tests for the BASILISK-specific half of bsk_service.py.

    python3 test_bsk_service.py            # needs `pip install bsk numpy`; no network, no kernels
    python3 test_bsk_service.py -v

The generic half lives in adapter_core and is tested by ../test_adapter_core.py -- including the
sample-to-segment conversion (`snap_up`, `real_segments`, `discrete_segments`), which is common to
any fixed-step backend rather than particular to Basilisk.

What is left here is the part that is about Basilisk and about activities, and it is where this
adapter can be wrong in ways nothing else would catch:

  * PLACEMENT. Basilisk's clock only exists on task-step multiples, so a directive's start and end
    move. Every failure mode is silent: a span that reports the requested time while the simulator
    acted at the following step, an activity that runs past the window reported as if it finished,
    an activity past the last step reported at all.
  * THE KNOB TIMELINE. Overlapping activities must SUM. The obvious implementation -- an on event
    and an off event per activity -- passes every single-activity test and then has the first
    activity's "off" switch the second one off too.
  * COMPUTED ATTRIBUTES. Read back out of telemetry over the span's own window, and only ever on
    finished spans (merlin discriminates finished from unfinished by their presence).
  * THE DECLARATION and the identity hash minted from it.

Most of these need no propagation, so they run with no SPICE kernels on disk. The handful that do
run a real orbit are in `TestRealSimulation`, which skips when the kernels are absent -- they are
128 MB and downloading them from naif.jpl.nasa.gov on every CI run would be both flaky and rude. The
container bakes them in, so that class does run in the image and in the e2e suite.
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bsk_service as S                                                          # noqa: E402
from adapter_core import BadRequest, Directive, SimulationRequest                # noqa: E402
from bsk_model import KNOBS, ConfigError, Spacecraft, spice_utc                  # noqa: E402

US = 1_000_000
STEP = 5 * US                       # the default timeStepSeconds, in microseconds
EPOCH = datetime(2026, 7, 27, tzinfo=timezone.utc)


def kernels_present():
    """True when the SPICE kernels are on disk, so a real propagation is possible offline."""
    try:
        from Basilisk.utilities.supportDataTools.dataFetcher import POOCH
    except Exception:                                                            # noqa: BLE001
        return False
    return os.path.exists(os.path.join(str(POOCH.abspath), "supportData", "EphemerisData",
                                       "de430.bsp"))


def directive(id_, typ, start_us, duration_us, **args):
    """A directive as adapter_core would hand it to `simulate`: arguments already defaulted."""
    return Directive(id=id_, type=typ, start_offset=start_us,
                     arguments=S.declaration().effective_args(typ,
                                                              dict(args, duration=duration_us)))


def request(duration_us, directives=(), **config):
    return SimulationRequest(duration=duration_us,
                             configuration=S.effective_config(config),
                             directives=list(directives),
                             plan_start_iso=EPOCH.isoformat(), _plan_start=EPOCH)


# --- declaration ------------------------------------------------------------------------------------
class TestDeclaration(unittest.TestCase):
    def test_introspection_reports_both_activity_types_with_ordered_parameters(self):
        intro = S.introspect()
        self.assertEqual([a["name"] for a in intro["activityTypes"]], ["Observe", "Downlink"])
        # Order is load-bearing: merlin assigns each parameter an `order` from its index here,
        # persists it, and plandev-ui lays the argument form out in it.
        observe = intro["activityTypes"][0]
        self.assertEqual([p["name"] for p in observe["parameters"]],
                         ["duration", "baudRate", "powerWatts"])
        self.assertEqual(observe["requiredParameters"], ["duration"])

    def test_every_resource_is_declared_exactly_once_and_has_a_source(self):
        names = [r["name"] for r in S.introspect()["resourceTypes"]]
        self.assertEqual(len(names), len(set(names)))
        # A resource with no channel and no timeline entry would be declared and then never
        # emitted, which merlin stores as a resource that is permanently absent.
        from_timeline = {name for name, _, _, _ in S.TIMELINE_RESOURCES}
        for name in names:
            self.assertTrue(name in S.CHANNEL_FOR_RESOURCE or name in from_timeline, name)

    def test_the_two_commanded_mode_resources_are_NOT_read_from_telemetry(self):
        # They are what the plan asked for, not what happened -- see `_timeline_segments`.
        for name, _, _, _ in S.TIMELINE_RESOURCES:
            self.assertNotIn(name, S.CHANNEL_FOR_RESOURCE)

    def test_configuration_defaults_are_complete(self):
        # An unsupplied configuration must still build a spacecraft: merlin sends only what the
        # planner overrode.
        resolved = S.effective_config({})
        self.assertEqual(sorted(resolved), sorted(name for name, _, _ in S.CONFIG))
        self.assertEqual(resolved["timeStepSeconds"], 5.0)

    def test_computed_attribute_schemas_match_what_simulate_attaches(self):
        # A mismatch here is rejected by merlin's ingest gate rather than stored, so the declaration
        # and the emission have to be checked against each other somewhere.
        self.assertEqual(set(S.COMPUTED["Observe"]["items"]),
                         {"minStateOfCharge", "meanSunlightFraction", "storedBitsAtEnd"})
        self.assertEqual(set(S.COMPUTED["Downlink"]["items"]),
                         {"accessFraction", "netStoredBitsChange", "minStateOfCharge"})

    def test_every_knob_is_driven_by_some_activity(self):
        driven = {knob for contributions in S.KNOB_CONTRIBUTIONS.values() for knob in contributions}
        self.assertEqual(driven, set(KNOBS))


class TestIdentityHash(unittest.TestCase):
    """The hash merlin STORES as an attestation that it introspected the model it is about to
    simulate. It must move whenever anything PlanDev persists moves, and not otherwise."""

    def test_it_is_stable_across_calls(self):
        self.assertEqual(S.identity_hash(), S.identity_hash())

    def test_reordering_parameters_changes_it(self):
        original = S.ACTIVITIES["Observe"]
        try:
            S.ACTIVITIES["Observe"] = [original[0], original[2], original[1]]
            self.assertNotEqual(S.identity_hash(), self.baseline)
        finally:
            S.ACTIVITIES["Observe"] = original

    def test_changing_a_default_changes_it(self):
        original = S.CONFIG[0]
        try:
            S.CONFIG[0] = (original[0], original[1], 10.0)
            self.assertNotEqual(S.identity_hash(), self.baseline)
        finally:
            S.CONFIG[0] = original

    def test_changing_a_computed_attribute_schema_changes_it(self):
        original = S.COMPUTED["Downlink"]
        try:
            S.COMPUTED["Downlink"] = {"type": "struct", "items": {"accessFraction": S.REAL}}
            self.assertNotEqual(S.identity_hash(), self.baseline)
        finally:
            S.COMPUTED["Downlink"] = original

    def test_renaming_a_resource_changes_it(self):
        original = dict(S.REAL_RESOURCES)
        try:
            S.REAL_RESOURCES["/power/renamed"] = S.REAL_RESOURCES.pop("/power/netWatts")
            self.assertNotEqual(S.identity_hash(), self.baseline)
        finally:
            S.REAL_RESOURCES.clear()
            S.REAL_RESOURCES.update(original)

    def setUp(self):
        self.baseline = S.identity_hash()


# --- placement ---------------------------------------------------------------------------------
class TestPlacement(unittest.TestCase):
    """`_place` is where PlanDev's microsecond timeline meets Basilisk's step grid."""

    def place(self, directives, sim_duration_us=3600 * US):
        last_step = (sim_duration_us // STEP) * STEP
        return S.BACKEND._place(list(directives), STEP, last_step)

    def test_a_start_between_steps_is_reported_at_the_step_the_effect_lands_on(self):
        _, spans = self.place([directive(1, "Observe", 600 * US + 1, 900 * US)])
        # Not 600000001: Basilisk applies the effect at 605s, so that is when the activity ran.
        self.assertEqual(spans[0]["startOffset"], 605 * US)
        self.assertEqual(spans[0]["duration"], 900 * US)

    def test_both_edges_snap_so_the_duration_grows_to_the_grid(self):
        # Requested [1s, 7s); both edges snap up, so it runs [5s, 10s).
        _, spans = self.place([directive(1, "Observe", 1 * US, 6 * US)])
        self.assertEqual(spans[0]["startOffset"], STEP)
        self.assertEqual(spans[0]["duration"], STEP)

    def test_an_activity_shorter_than_one_step_is_REFUSED_wherever_it_lands(self):
        # Off the grid both edges snap to the same instant and it does nothing; ON the grid it
        # stretches to a full step and does five times what was asked. Neither is representable, and
        # which one you get depends on nothing the planner controls -- so both are refused.
        for start in (1, 0, 600 * US, 600 * US + 1):
            with self.assertRaises(BadRequest) as caught:
                self.place([directive(1, "Observe", start, US)])
            message = str(caught.exception)
            self.assertIn("shorter than the", message)
            self.assertIn("timeStepSeconds", message)

    def test_an_activity_of_exactly_one_step_is_accepted(self):
        # The boundary: one step is the shortest representable activity.
        _, spans = self.place([directive(1, "Observe", 600 * US, STEP)])
        self.assertEqual(spans[0]["duration"], STEP)

    def test_a_short_activity_is_fine_once_the_step_is_small_enough(self):
        # The same 3us activity at a 1us step: the knob names the fix, so the fix must work.
        last_step = 3600 * US
        _, spans = S.BACKEND._place([directive(1, "Observe", 1, 3)], 1, last_step)
        self.assertEqual(spans[0]["startOffset"], 1)
        self.assertEqual(spans[0]["duration"], 3)

    def test_an_activity_running_past_the_window_is_UNFINISHED_not_clamped(self):
        _, spans = self.place([directive(1, "Observe", 3500 * US, 600 * US)])
        self.assertNotIn("duration", spans[0])
        self.assertNotIn("computedAttributes", spans[0])

    def test_an_activity_starting_past_the_last_step_produces_no_span_at_all(self):
        activities, spans = self.place([directive(1, "Observe", 3600 * US + 1, US)])
        self.assertEqual(spans, [])
        self.assertEqual(activities, [])

    def test_an_activity_ending_exactly_at_the_window_edge_is_finished(self):
        _, spans = self.place([directive(1, "Observe", 3000 * US, 600 * US)])
        self.assertEqual(spans[0]["duration"], 600 * US)
        self.assertEqual(spans[0]["startOffset"] + spans[0]["duration"], 3600 * US)

    def test_spans_carry_the_effective_arguments_not_a_raw_echo(self):
        _, spans = self.place([directive(1, "Observe", 0, 60 * US)])
        self.assertEqual(spans[0]["arguments"],
                         {"duration": 60 * US, "baudRate": 12.0e6, "powerWatts": 55.0})

    def test_a_nonpositive_duration_is_a_400(self):
        with self.assertRaises(BadRequest) as caught:
            self.place([directive(1, "Observe", 0, 0)])
        self.assertIn("must be positive", str(caught.exception))

    def test_a_start_before_the_plan_is_a_400(self):
        with self.assertRaises(BadRequest) as caught:
            self.place([directive(1, "Observe", -US, 60 * US)])
        self.assertIn("before the plan", str(caught.exception))

    def test_span_ids_are_dense_even_when_a_directive_is_dropped(self):
        # spanId numbering follows the spans emitted, not the directives received; a gap would make
        # a parentId reference unresolvable.
        _, spans = self.place([directive(1, "Observe", 3600 * US + 1, US),
                               directive(2, "Observe", 0, 60 * US),
                               directive(3, "Downlink", 0, 60 * US)])
        self.assertEqual([s["spanId"] for s in spans], [1, 2])
        self.assertEqual([s["directiveId"] for s in spans], [2, 3])


# --- the knob timeline --------------------------------------------------------------------------
class TestKnobTimeline(unittest.TestCase):
    LAST = 3600 * US

    def totals_at(self, timeline, time_us):
        current = timeline[0][1]
        for start_us, knobs in timeline:
            if start_us <= time_us:
                current = knobs
        return current

    def test_overlapping_observations_SUM_rather_than_overwrite(self):
        activities = [{"start": 0, "end": 100 * US, "knobs": {"instrumentBaudRate": 12e6,
                                                              "instrumentPowerWatts": 55.0}},
                      {"start": 50 * US, "end": 150 * US, "knobs": {"instrumentBaudRate": 4e6,
                                                                    "instrumentPowerWatts": 20.0}}]
        timeline = S.knob_timeline(activities, self.LAST)
        self.assertEqual(self.totals_at(timeline, 10 * US)["instrumentBaudRate"], 12e6)
        self.assertEqual(self.totals_at(timeline, 60 * US)["instrumentBaudRate"], 16e6)
        self.assertEqual(self.totals_at(timeline, 60 * US)["instrumentPowerWatts"], 75.0)

    def test_the_first_activity_ending_does_not_switch_the_second_one_off(self):
        # The bug that per-activity on/off events would have, and that only appears once two
        # activities overlap.
        activities = [{"start": 0, "end": 100 * US, "knobs": {"instrumentBaudRate": 12e6}},
                      {"start": 50 * US, "end": 150 * US, "knobs": {"instrumentBaudRate": 4e6}}]
        timeline = S.knob_timeline(activities, self.LAST)
        self.assertEqual(self.totals_at(timeline, 120 * US)["instrumentBaudRate"], 4e6)
        self.assertEqual(self.totals_at(timeline, 200 * US)["instrumentBaudRate"], 0.0)

    def test_it_always_starts_at_zero_with_every_knob_defined(self):
        timeline = S.knob_timeline([], self.LAST)
        self.assertEqual(timeline[0][0], 0)
        self.assertEqual(set(timeline[0][1]), set(KNOBS))
        self.assertEqual(set(timeline[0][1].values()), {0.0})

    def test_an_edge_that_changes_nothing_is_dropped(self):
        # One activity ending exactly as an identical one begins: the totals never move, so there is
        # no event to schedule and no segment boundary to draw.
        activities = [{"start": 0, "end": 50 * US, "knobs": {"instrumentBaudRate": 12e6}},
                      {"start": 50 * US, "end": 100 * US, "knobs": {"instrumentBaudRate": 12e6}}]
        timeline = S.knob_timeline(activities, self.LAST)
        self.assertEqual([t for t, _ in timeline], [0, 100 * US])

    def test_an_activity_ending_past_the_last_step_never_turns_off(self):
        activities = [{"start": 0, "end": self.LAST + 10 * STEP,
                       "knobs": {"instrumentBaudRate": 12e6}}]
        timeline = S.knob_timeline(activities, self.LAST)
        self.assertEqual([t for t, _ in timeline], [0])
        self.assertEqual(timeline[0][1]["instrumentBaudRate"], 12e6)

    def test_the_timeline_is_independent_of_the_order_directives_arrive_in(self):
        a = {"start": 0, "end": 100 * US, "knobs": {"instrumentBaudRate": 12e6}}
        b = {"start": 50 * US, "end": 150 * US, "knobs": {"instrumentBaudRate": 4e6}}
        self.assertEqual(S.knob_timeline([a, b], self.LAST), S.knob_timeline([b, a], self.LAST))


class TestTimelineSegments(unittest.TestCase):
    def test_a_commanded_mode_profile_covers_the_window_exactly(self):
        timeline = S.knob_timeline(
            [{"start": 100 * US, "end": 200 * US, "knobs": {"instrumentBaudRate": 12e6}}],
            3600 * US)
        segments = S._timeline_segments(timeline, 3600 * US + 7,
                                        "instrumentBaudRate", "Idle", "Imaging")
        self.assertEqual(sum(s["duration"] for s in segments), 3600 * US + 7)
        self.assertEqual([s["dynamics"] for s in segments], ["Idle", "Imaging", "Idle"])

    def test_an_empty_plan_is_one_idle_segment(self):
        segments = S._timeline_segments(S.knob_timeline([], 3600 * US), 3600 * US,
                                        "transmitterBaudRate", "Idle", "Transmitting")
        self.assertEqual(segments, [{"duration": 3600 * US, "dynamics": "Idle"}])


# --- computed attributes ---------------------------------------------------------------------------
class TestComputedAttributes(unittest.TestCase):
    """Attached from recorded telemetry over the span's own window. The arrays here stand in for a
    propagation so the windowing can be checked exactly."""

    def channels(self, samples):
        return {"stateOfCharge": [0.9 - 0.01 * i for i in range(samples)],
                "sunlightFraction": [1.0 if i % 2 == 0 else 0.0 for i in range(samples)],
                "storedBits": [1000.0 * i for i in range(samples)],
                "groundStationInView": [i >= 4 for i in range(samples)]}

    def test_an_unfinished_span_gets_none(self):
        spans = [{"spanId": 1, "type": "Observe", "startOffset": 0}]
        S.BACKEND._attach_computed(spans, self.channels(10), STEP, 9)
        self.assertNotIn("computedAttributes", spans[0])

    def test_the_window_is_the_spans_own_and_includes_both_ends(self):
        spans = [{"spanId": 1, "type": "Observe", "startOffset": 2 * STEP, "duration": 2 * STEP}]
        S.BACKEND._attach_computed(spans, self.channels(10), STEP, 9)
        computed = spans[0]["computedAttributes"]
        # samples 2, 3, 4 -> soc 0.88, 0.87, 0.86 and sunlight 1, 0, 1
        self.assertAlmostEqual(computed["minStateOfCharge"], 0.86)
        self.assertAlmostEqual(computed["meanSunlightFraction"], 2.0 / 3.0)
        self.assertEqual(computed["storedBitsAtEnd"], 4000.0)

    def test_a_downlink_reports_the_fraction_of_its_window_that_had_access(self):
        spans = [{"spanId": 1, "type": "Downlink", "startOffset": 2 * STEP, "duration": 4 * STEP}]
        S.BACKEND._attach_computed(spans, self.channels(10), STEP, 9)
        # samples 2..6; access is True from 4 -> 3 of 5
        self.assertAlmostEqual(spans[0]["computedAttributes"]["accessFraction"], 0.6)
        self.assertEqual(spans[0]["computedAttributes"]["netStoredBitsChange"], 4000.0)

    def test_indices_are_clamped_to_the_samples_that_exist(self):
        # A span may finish on the last grid point while the sub-step tail of the window has no
        # sample of its own; indexing past the end would be an IndexError mid-response.
        spans = [{"spanId": 1, "type": "Observe", "startOffset": 8 * STEP, "duration": 2 * STEP}]
        S.BACKEND._attach_computed(spans, self.channels(10), STEP, 9)
        self.assertEqual(spans[0]["computedAttributes"]["storedBitsAtEnd"], 9000.0)


# --- validation --------------------------------------------------------------------------------
class TestValidate(unittest.TestCase):
    def test_a_missing_required_duration_is_reported_by_the_generic_layer(self):
        result = S.validate_one("Observe", {})
        self.assertFalse(result["valid"])
        self.assertIn("duration", str(result["notices"]))

    def test_a_negative_baud_rate_is_attributed_to_its_own_field(self):
        result = S.validate_one("Downlink", {"duration": 60 * US, "baudRate": -1.0})
        self.assertFalse(result["valid"])
        # subjects is what makes the notice render on the field rather than as a whole-activity
        # message, which plandev-ui drops.
        self.assertEqual([n["subjects"] for n in result["notices"]], [["baudRate"]])

    def test_a_wrongly_typed_duration_is_caught_before_the_model_sees_it(self):
        result = S.validate_one("Observe", {"duration": "not-a-duration"})
        self.assertFalse(result["valid"])
        self.assertIn("duration", str(result["notices"]))

    def test_a_valid_activity_comes_back_with_its_defaults_filled_in(self):
        result = S.validate_one("Observe", {"duration": 60 * US})
        self.assertTrue(result["valid"])
        self.assertEqual(result["effectiveArguments"],
                         {"duration": 60 * US, "baudRate": 12.0e6, "powerWatts": 55.0})


class TestConfigurationRejection(unittest.TestCase):
    """Every check that can be made from the numbers alone runs before any Basilisk object exists,
    so these need no SPICE kernels."""

    def build(self, **overrides):
        return Spacecraft(S.effective_config(overrides), EPOCH)

    def test_a_step_that_is_not_a_whole_microsecond_is_rejected(self):
        with self.assertRaises(ConfigError) as caught:
            self.build(timeStepSeconds=0.0000005)
        self.assertIn("whole number of microseconds", str(caught.exception))

    def test_a_zero_or_negative_step_is_rejected(self):
        for value in (0.0, -1.0):
            with self.assertRaises(ConfigError):
                self.build(timeStepSeconds=value)

    def test_an_orbit_inside_the_earth_is_rejected_with_a_reason(self):
        with self.assertRaises(ConfigError) as caught:
            self.build(semiMajorAxisKm=3000.0)
        self.assertIn("periapsis is inside the Earth", str(caught.exception))

    def test_an_eccentricity_that_dips_the_periapsis_underground_is_rejected(self):
        with self.assertRaises(ConfigError):
            self.build(semiMajorAxisKm=7000.0, eccentricity=0.5)

    def test_a_charge_fraction_outside_zero_to_one_is_rejected(self):
        for value in (-0.1, 1.5):
            with self.assertRaises(ConfigError):
                self.build(initialChargeFraction=value)

    def test_a_nonpositive_battery_or_recorder_is_rejected(self):
        with self.assertRaises(ConfigError):
            self.build(batteryCapacityWattHours=0.0)
        with self.assertRaises(ConfigError):
            self.build(dataCapacityBits=0.0)

    def test_an_impossible_step_count_is_a_400_that_names_the_knob(self):
        with self.assertRaises(BadRequest) as caught:
            S.BACKEND.simulate(request(7 * 24 * 3600 * US, timeStepSeconds=0.001))
        self.assertIn("timeStepSeconds", str(caught.exception))

    def test_a_zero_length_plan_is_a_400(self):
        with self.assertRaises(BadRequest):
            S.BACKEND.simulate(request(0))


class TestSpiceEpochFormat(unittest.TestCase):
    def test_it_is_the_calendar_string_spice_parses(self):
        self.assertEqual(spice_utc(datetime(2026, 7, 27, 4, 5, 6, 7, tzinfo=timezone.utc)),
                         "2026 JUL 27 04:05:06.000007 (UTC)")

    def test_a_non_utc_epoch_is_converted_rather_than_relabelled(self):
        from datetime import timedelta
        eastern = timezone(timedelta(hours=-5))
        self.assertEqual(spice_utc(datetime(2026, 1, 1, 20, 0, 0, tzinfo=eastern)),
                         "2026 JAN 02 01:00:00.000000 (UTC)")


# --- a real propagation ---------------------------------------------------------------------------
@unittest.skipUnless(kernels_present(), "SPICE kernels are not on disk (the container bakes them in)")
class TestRealSimulation(unittest.TestCase):
    """The claims that only a real orbit can settle."""

    @classmethod
    def setUpClass(cls):
        cls.out = S.simulate({
            "planStart": EPOCH.isoformat(), "duration": 2 * 3600 * US + 123, "configuration": {},
            "directives": [
                {"id": 1, "type": "Observe", "startOffset": 600 * US + 1,
                 "arguments": {"duration": 900 * US}},
                {"id": 2, "type": "Observe", "startOffset": 1000 * US,
                 "arguments": {"duration": 900 * US, "baudRate": 4.0e6}},
                {"id": 3, "type": "Observe", "startOffset": 7100 * US,
                 "arguments": {"duration": 600 * US}},
            ]})
        cls.sim_duration = 2 * 3600 * US + 123

    def test_every_declared_resource_is_actually_emitted(self):
        emitted = set(self.out["realProfiles"]) | set(self.out["discreteProfiles"])
        self.assertEqual(emitted, set(S.REAL_RESOURCES) | set(S.DISCRETE_RESOURCES))

    def test_every_profile_covers_the_plan_exactly(self):
        # Including the 123us that is not a step multiple. merlin's ingest gate rejects a profile
        # that stops short.
        for kind in ("realProfiles", "discreteProfiles"):
            for name, profile in self.out[kind].items():
                self.assertEqual(sum(s["duration"] for s in profile["segments"]),
                                 self.sim_duration, name)

    def test_real_profiles_agree_with_themselves_across_segment_boundaries(self):
        # `initial + rate*elapsed` at the end of one segment must land on the next segment's
        # `initial`; the secant rate is what guarantees it even where the model saturates.
        for name, profile in self.out["realProfiles"].items():
            for a, b in zip(profile["segments"], profile["segments"][1:]):
                self.assertAlmostEqual(
                    a["dynamics"]["initial"] + a["dynamics"]["rate"] * (a["duration"] / US),
                    b["dynamics"]["initial"], places=9, msg=name)

    def test_the_solar_array_generates_power_and_the_battery_responds(self):
        watts = [s["dynamics"]["initial"] for s in
                 self.out["realProfiles"]["/power/solarArrayWatts"]["segments"]]
        # 1367 W/m^2 scaled for Earth's distance in late July, x 0.4 m^2 x 0.29.
        self.assertGreater(max(watts), 140.0)
        self.assertLess(max(watts), 165.0)
        self.assertEqual(min(watts), 0.0)                    # eclipse
        charge = [s["dynamics"]["initial"] for s in
                  self.out["realProfiles"]["/power/battery/stateOfCharge"]["segments"]]
        self.assertTrue(all(0.0 <= c <= 1.0 for c in charge))

    def test_the_orbit_passes_through_eclipse(self):
        states = {s["dynamics"] for s in self.out["discreteProfiles"]["/geometry/eclipse"]["segments"]}
        self.assertIn("Umbra", states)
        self.assertIn("Sunlight", states)

    def test_the_instrument_fills_the_recorder_only_while_observing(self):
        bits = [s["dynamics"]["initial"] for s in
                self.out["realProfiles"]["/data/storedBits"]["segments"]]
        self.assertEqual(bits[0], 0.0)
        # 12 Mbps for 900s then 16 Mbps (both instruments) overlapping: strictly increasing overall.
        self.assertGreater(bits[-1], 0.0)

    def test_a_directive_off_the_grid_is_reported_at_the_step_it_ran_on(self):
        span = next(s for s in self.out["spans"] if s["directiveId"] == 1)
        self.assertEqual(span["startOffset"], 605 * US)

    def test_the_activity_running_past_the_window_is_unfinished(self):
        span = next(s for s in self.out["spans"] if s["directiveId"] == 3)
        self.assertNotIn("duration", span)
        self.assertNotIn("computedAttributes", span)

    def test_finished_spans_carry_computed_attributes_matching_their_schema(self):
        for span in self.out["spans"]:
            if "duration" not in span:
                continue
            self.assertEqual(set(span["computedAttributes"]),
                             set(S.COMPUTED[span["type"]]["items"]))

    def test_a_downlink_out_of_view_moves_no_bits_and_says_so(self):
        out = S.simulate({
            "planStart": EPOCH.isoformat(), "duration": 3600 * US, "configuration": {},
            "directives": [
                {"id": 1, "type": "Observe", "startOffset": 0, "arguments": {"duration": 600 * US}},
                {"id": 2, "type": "Downlink", "startOffset": 2400 * US,
                 "arguments": {"duration": 300 * US}}]})
        view = out["discreteProfiles"]["/comm/groundStationInView"]["segments"]
        # The default orbit's only pass over Goldstone in this hour is early; a downlink at 40
        # minutes is out of view.
        self.assertIn(False, [s["dynamics"] for s in view])
        downlink = next(s for s in out["spans"] if s["directiveId"] == 2)
        self.assertEqual(downlink["computedAttributes"]["accessFraction"], 0.0)
        self.assertGreaterEqual(downlink["computedAttributes"]["netStoredBitsChange"], 0.0)

    def test_a_downlink_in_view_actually_drains_the_recorder(self):
        # Find the real access window first, then schedule into it -- the pass geometry is a
        # property of the orbit, not a number to hard-code.
        base = {"planStart": EPOCH.isoformat(), "duration": 3 * 3600 * US, "configuration": {}}
        geometry = S.simulate(dict(base, directives=[]))
        offset, window = 0, None
        for segment in geometry["discreteProfiles"]["/comm/groundStationInView"]["segments"]:
            if segment["dynamics"] and segment["duration"] > 240 * US:
                window = (offset, offset + segment["duration"])
                break
            offset += segment["duration"]
        self.assertIsNotNone(window, "the default orbit has no ground-station pass in 3 hours")

        out = S.simulate(dict(base, directives=[
            {"id": 1, "type": "Observe", "startOffset": 0, "arguments": {"duration": 600 * US}},
            {"id": 2, "type": "Downlink", "startOffset": window[0] + 60 * US,
             "arguments": {"duration": 120 * US}}]))
        downlink = next(s for s in out["spans"] if s["directiveId"] == 2)
        self.assertEqual(downlink["computedAttributes"]["accessFraction"], 1.0)
        # 120 s at the default 8 Mbps.
        self.assertAlmostEqual(downlink["computedAttributes"]["netStoredBitsChange"], -960.0e6,
                               delta=1.0e6)

    def test_two_overlapping_observations_fill_the_recorder_at_the_combined_rate(self):
        out = S.simulate({
            "planStart": EPOCH.isoformat(), "duration": 600 * US, "configuration": {},
            "directives": [
                {"id": 1, "type": "Observe", "startOffset": 0,
                 "arguments": {"duration": 300 * US, "baudRate": 10.0e6}},
                {"id": 2, "type": "Observe", "startOffset": 100 * US,
                 "arguments": {"duration": 300 * US, "baudRate": 5.0e6}}]})
        # 100s at 10 Mbps + 200s at 15 Mbps + 100s at 5 Mbps = 4.5 Gb.
        final = out["realProfiles"]["/data/storedBits"]["segments"][-1]["dynamics"]["initial"]
        self.assertAlmostEqual(final, 4.5e9, delta=2.0e7)

    def test_the_same_request_twice_gives_the_same_answer(self):
        # Determinism is what lets merlin cache a simulation against a plan revision.
        req = {"planStart": EPOCH.isoformat(), "duration": 1800 * US, "configuration": {},
               "directives": [{"id": 1, "type": "Observe", "startOffset": 60 * US,
                               "arguments": {"duration": 120 * US}}]}
        self.assertEqual(S.simulate(req), S.simulate(req))


if __name__ == "__main__":
    unittest.main()
