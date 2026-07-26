#!/usr/bin/env python3
"""Tests for py_model_server.py -- the Python external-model backend.

    python3 test_py_model_server.py            # offline; no server, no Docker, no network
    python3 test_py_model_server.py -v

Everything here is a direct call into the module's pure functions. The HTTP server lives behind
`if __name__ == "__main__"`, so importing the module is side-effect free (pinned by
`TestModuleIsImportable`) and no socket is ever bound.

What these tests are FOR. The module was rebuilt after an audit; the bugs it fixed were mostly
SILENT ones -- a simulation that returns a well-formed, plausible, wrong answer. Those are the
behaviours pinned hardest here:

  * Superposition. Profiles come from a breakpoint timeline of absolute offsets, not a running
    cursor. A cursor cannot express two activities running at once, and for a battery a Charge
    overlapping a Discharge is the ordinary case. The cursor also made the answer depend on the
    order directives happened to arrive in.
  * Profile/span agreement. Cumulative segment offsets must equal wall-clock offsets. The cursor
    version could report a span starting at 1.5h whose rate change landed at 3h in the profile --
    two views of the same run disagreeing, with nothing to flag it.
  * Finished vs unfinished spans. merlin tells the two apart by the presence of BOTH `duration`
    and `computedAttributes`, so that pairing is load-bearing, not cosmetic.
  * Typechecking. merlin DELEGATES authoritative validation to the backend for external models,
    so if `nonconformance` does not catch a type-wrong argument, nothing does.
"""
import copy
import os
import unittest

import py_model_server as pms
from py_model_server import (BadRequest, effective_args, effective_config, identity_hash,
                             introspect, models_list, nonconformance, simulate, undeclared,
                             validate_one)

S = 1_000_000                                  # microseconds per second
MIN = 60 * S
H = 3600 * S
PLAN_START = "2024-01-01T00:00:00Z"

REAL = {"type": "real"}
INT = {"type": "int"}
DURATION = {"type": "duration"}
BOOLEAN = {"type": "boolean"}
STRING = {"type": "string"}
VARIANT = {"type": "variant", "variants": [{"key": "Idle", "label": "Idle"},
                                           {"key": "Charging", "label": "Charging"}]}


# --- helpers ---------------------------------------------------------------------------------------
def directive(did, typ, start, **arguments):
    return {"id": did, "type": typ, "startOffset": start, "arguments": arguments}


def charge(did, start, duration, **kw):
    return directive(did, "Charge", start, duration=duration, **kw)


def discharge(did, start, duration, **kw):
    return directive(did, "Discharge", start, duration=duration, **kw)


def run(directives, duration=4 * H, configuration=None):
    return simulate({"planStart": PLAN_START, "duration": duration,
                     "configuration": configuration if configuration is not None else {},
                     "directives": list(directives)})


def total_duration(segments):
    return sum(s["duration"] for s in segments)


def timeline(result, resource="SoC"):
    """[(start, end, dynamics)] in ABSOLUTE offsets, obtained by cumulating segment durations.

    This is the only way a consumer can place a segment in time -- the wire format carries
    durations, not offsets -- so it is also the only way to check that the profile agrees with
    the spans."""
    profiles = dict(result["realProfiles"], **result["discreteProfiles"])
    out, off = [], 0
    for s in profiles[resource]["segments"]:
        out.append((off, off + s["duration"], s["dynamics"]))
        off += s["duration"]
    return out


def rates(result):
    return [(lo, hi, dyn["rate"]) for lo, hi, dyn in timeline(result)]


def rate_at(result, t):
    for lo, hi, rate in rates(result):
        if lo <= t < hi:
            return rate
    return None


def span_rate(span):
    """The rate a span implies, recovered from its own reported arguments."""
    args = span["arguments"]
    return float(args["rate"]) if span["type"] == "Charge" else -float(args["load"])


def rate_from_spans(spans, sim_duration, t):
    """What the profile SHOULD read at `t`, derived independently from the spans."""
    total = 0.0
    for s in spans:
        start = s["startOffset"]
        # No `duration` means the activity outlived the window, so it is still running at the end.
        end = start + s["duration"] if "duration" in s else sim_duration
        if start <= t < end:
            total += span_rate(s)
    return total


class SimTestCase(unittest.TestCase):
    """Invariants that must hold for EVERY simulation, checked by the tests that call them."""

    def assertTiles(self, result, sim_duration):
        """Every profile covers the window exactly once -- no gap, no overhang, no double count."""
        profiles = dict(result["realProfiles"], **result["discreteProfiles"])
        for name, prof in profiles.items():
            self.assertEqual(total_duration(prof["segments"]), sim_duration,
                             "%s segments sum to %d, want exactly %d"
                             % (name, total_duration(prof["segments"]), sim_duration))

    def assertProfilesAgreeWithSpans(self, result, sim_duration):
        """The rate the profile reports at time t equals the rate the spans imply at time t.

        Checked at both edges and the middle of every segment, which is enough to catch a whole
        profile shifted in time as well as a single misplaced segment."""
        self.assertTiles(result, sim_duration)
        for lo, hi, rate in rates(result):
            for t in {lo, (lo + hi) // 2, hi - 1}:
                self.assertAlmostEqual(
                    rate, rate_from_spans(result["spans"], sim_duration, t), places=9,
                    msg="profile says rate %r over [%d, %d) but the spans imply %r at %d"
                        % (rate, lo, hi, rate_from_spans(result["spans"], sim_duration, t), t))

    def assertSoCIsContinuous(self, result):
        """Each segment's `initial` is the previous segment's endpoint: initial + rate * dt."""
        segs = timeline(result)
        for (lo, hi, dyn), (_, _, nxt) in zip(segs, segs[1:]):
            self.assertAlmostEqual(nxt["initial"], dyn["initial"] + dyn["rate"] * ((hi - lo) / S),
                                   places=6, msg="SoC jumps at %d" % hi)


# --- interval timeline / superposition ---------------------------------------------------------------
class TestSuperposition(SimTestCase):
    """Two activities running at once must SUM. The pre-audit cursor could not express this."""

    def test_overlapping_charge_and_discharge_produce_the_summed_rate(self):
        # Charge +1.0/s over [1h, 3h); Discharge -2.0/s over [2h, 4h). The overlap is [2h, 3h).
        result = run([charge(1, 1 * H, 2 * H, rate=1.0),
                      discharge(2, 2 * H, 2 * H, load=2.0)])
        self.assertEqual(rates(result), [(0, 1 * H, 0.0),
                                         (1 * H, 2 * H, 1.0),
                                         (2 * H, 3 * H, -1.0),      # 1.0 + (-2.0), superposed
                                         (3 * H, 4 * H, -2.0)])
        self.assertProfilesAgreeWithSpans(result, 4 * H)
        self.assertSoCIsContinuous(result)

    def test_three_overlapping_activities_all_contribute(self):
        result = run([charge(1, 0, 4 * H, rate=1.0),
                      charge(2, 1 * H, 2 * H, rate=0.5),
                      discharge(3, 2 * H, 2 * H, load=2.0)])
        self.assertAlmostEqual(rate_at(result, 30 * MIN), 1.0)
        self.assertAlmostEqual(rate_at(result, 90 * MIN), 1.5)      # 1.0 + 0.5
        self.assertAlmostEqual(rate_at(result, 150 * MIN), -0.5)    # 1.0 + 0.5 - 2.0
        self.assertAlmostEqual(rate_at(result, 210 * MIN), -1.0)    # 1.0 - 2.0
        self.assertProfilesAgreeWithSpans(result, 4 * H)

    def test_fully_coincident_activities_superpose_rather_than_replace(self):
        result = run([charge(1, 1 * H, 2 * H, rate=1.0),
                      discharge(2, 1 * H, 2 * H, load=2.0)])
        self.assertEqual(rates(result), [(0, 1 * H, 0.0), (1 * H, 3 * H, -1.0), (3 * H, 4 * H, 0.0)])

    def test_segment_durations_sum_exactly_to_the_simulation_duration(self):
        result = run([charge(1, 1 * H, 2 * H), discharge(2, 2 * H, 2 * H)])
        self.assertEqual(total_duration(result["realProfiles"]["SoC"]["segments"]), 4 * H)
        self.assertTiles(result, 4 * H)

    def test_the_result_does_not_depend_on_the_order_directives_arrive_in(self):
        """A tie at the same startOffset used to give a different answer per ordering.

        Only spanId is allowed to differ: it is a per-response handle assigned in request order,
        while directiveId is the stable link back to the plan."""
        a = charge(1, 1 * H, 2 * H, rate=1.0)
        b = discharge(2, 1 * H, 2 * H, load=2.0)      # same startOffset -- the tie
        c = charge(3, 0, 4 * H, rate=0.25)
        forward, reverse = run([a, b, c]), run([c, b, a])
        self.assertEqual(forward["realProfiles"], reverse["realProfiles"])
        self.assertEqual(forward["discreteProfiles"], reverse["discreteProfiles"])

        def by_directive(result):
            return {s["directiveId"]: {k: v for k, v in s.items() if k != "spanId"}
                    for s in result["spans"]}

        self.assertEqual(by_directive(forward), by_directive(reverse))
        self.assertEqual([s["directiveId"] for s in forward["spans"]], [1, 2, 3])
        self.assertEqual([s["spanId"] for s in forward["spans"]], [1, 2, 3])
        self.assertEqual([s["directiveId"] for s in reverse["spans"]], [3, 2, 1])

    def test_an_idle_gap_between_activities_is_its_own_zero_rate_segment(self):
        result = run([charge(1, 0, 1 * H), charge(2, 2 * H, 1 * H)])
        self.assertEqual([r for _, _, r in rates(result)], [1.0, 0.0, 1.0, 0.0])
        self.assertEqual([lo for lo, _, _ in rates(result)], [0, 1 * H, 2 * H, 3 * H])


# --- profile / span agreement --------------------------------------------------------------------
class TestProfileSpanAgreement(SimTestCase):
    """The critical bug: a span said an activity ran at 1.5h while its segment landed at 3h."""

    def test_a_rate_change_lands_at_the_span_start_offset_not_at_a_cumulative_offset(self):
        # The exact shape that broke: back-to-back activities of 1.5h. A cursor that appends
        # (gap = absolute start) + (activity duration) puts the SECOND segment at 3h.
        result = run([charge(1, 0, 90 * MIN, rate=1.0),
                      discharge(2, 90 * MIN, 90 * MIN, load=2.0)], duration=6 * H)
        second = next(s for s in result["spans"] if s["directiveId"] == 2)
        self.assertEqual(second["startOffset"], 90 * MIN)
        self.assertAlmostEqual(rate_at(result, 90 * MIN), -2.0,
                               msg="the discharge does not appear in the profile where its span says")
        self.assertAlmostEqual(rate_at(result, 90 * MIN - 1), 1.0)
        self.assertAlmostEqual(rate_at(result, 3 * H), 0.0,
                               msg="the discharge landed at 3h -- the cursor bug is back")
        self.assertEqual(rates(result), [(0, 90 * MIN, 1.0), (90 * MIN, 3 * H, -2.0), (3 * H, 6 * H, 0.0)])

    def test_every_span_start_is_a_segment_boundary(self):
        result = run([charge(1, 17 * MIN, 43 * MIN), discharge(2, 100 * MIN, 25 * MIN),
                      charge(3, 110 * MIN, 30 * MIN)])
        boundaries = {lo for lo, _, _ in rates(result)}
        for span in result["spans"]:
            self.assertIn(span["startOffset"], boundaries,
                          "span %s starts at %d, which is not a segment boundary"
                          % (span["spanId"], span["startOffset"]))
        self.assertProfilesAgreeWithSpans(result, 4 * H)

    def test_discrete_profiles_are_placed_on_the_same_timeline_as_the_real_profile(self):
        result = run([charge(1, 1 * H, 1 * H), discharge(2, 2 * H, 1 * H)])
        self.assertEqual([(lo, hi) for lo, hi, _ in timeline(result, "SoC")],
                         [(lo, hi) for lo, hi, _ in timeline(result, "Mode")])
        self.assertEqual([dyn for _, _, dyn in timeline(result, "Mode")],
                         ["Idle", "Charging", "Discharging", "Idle"])
        self.assertEqual([dyn for _, _, dyn in timeline(result, "Cycles")], [0, 1, 1, 1])

    def test_soc_accumulates_continuously_across_the_whole_window(self):
        result = run([charge(1, 0, 1 * H, rate=1.0), discharge(2, 1 * H, 1 * H, load=2.0)])
        self.assertSoCIsContinuous(result)
        first = timeline(result)[0][2]
        self.assertEqual(first["initial"], 50.0)                       # the configuration default
        self.assertAlmostEqual(timeline(result)[1][2]["initial"], 50.0 + 3600.0)


# --- clamping --------------------------------------------------------------------------------------
class TestClamping(SimTestCase):
    def test_a_directive_starting_past_the_end_contributes_nothing(self):
        result = run([charge(1, 5 * H, 1 * H)])
        self.assertEqual(result["spans"], [])
        self.assertEqual([r for _, _, r in rates(result)], [0.0])
        self.assertTiles(result, 4 * H)

    def test_a_directive_starting_exactly_at_the_end_contributes_nothing(self):
        """The window is half-open [0, duration), so an activity at the closing instant is out."""
        self.assertEqual(run([charge(1, 4 * H, 1 * H)])["spans"], [])

    def test_a_directive_extending_past_the_end_is_truncated_in_the_profile(self):
        result = run([charge(1, 3 * H, 5 * H, rate=1.0)])
        self.assertEqual(rates(result), [(0, 3 * H, 0.0), (3 * H, 4 * H, 1.0)])
        self.assertTiles(result, 4 * H)
        # Truncated in the PROFILE only: the span still reports what was asked for, minus a duration.
        self.assertEqual(result["spans"][0]["arguments"]["duration"], 5 * H)

    def test_segments_sum_to_the_simulation_duration_for_every_clamping_shape(self):
        shapes = {
            "empty":            [],
            "wholly before":    [charge(1, 5 * H, 1 * H)],
            "truncated":        [charge(1, 3 * H, 5 * H)],
            "spanning":         [charge(1, 0, 9 * H)],
            "zero duration":    [charge(1, 1 * H, 0)],
            "at instant zero":  [charge(1, 0, 1 * H)],
            "ends at the edge": [charge(1, 3 * H, 1 * H)],
            "mixed":            [charge(1, 0, 9 * H), discharge(2, 2 * H, 1 * H),
                                 charge(3, 5 * H, 1 * H), discharge(4, 3 * H, 3 * H)],
        }
        for label, directives in shapes.items():
            with self.subTest(shape=label):
                result = run(directives)
                self.assertTiles(result, 4 * H)
                self.assertProfilesAgreeWithSpans(result, 4 * H)

    def test_a_zero_length_simulation_produces_no_segments(self):
        result = run([charge(1, 0, 1 * H)], duration=0)
        self.assertEqual(result["realProfiles"]["SoC"]["segments"], [])
        self.assertEqual(result["spans"], [])
        self.assertTiles(result, 0)

    def test_a_zero_duration_activity_never_becomes_active(self):
        result = run([charge(1, 1 * H, 0)])
        # Its start/end breakpoints still split the window, so the idle stretch arrives as two
        # abutting zero-rate segments -- redundant but not wrong; segments are never coalesced.
        self.assertEqual({r for _, _, r in rates(result)}, {0.0})
        self.assertTiles(result, 4 * H)
        self.assertEqual(result["spans"][0]["duration"], 0)
        self.assertEqual(result["spans"][0]["computedAttributes"], {"socDelta": 0.0})


# --- finished vs unfinished spans ---------------------------------------------------------------
class TestFinishedAndUnfinishedSpans(SimTestCase):
    """merlin distinguishes finished from unfinished by the presence of BOTH `duration` and
    `computedAttributes` (PostgresResultsCellRepository), so the two must travel together."""

    def test_an_activity_outliving_the_window_has_neither_duration_nor_computed_attributes(self):
        span = run([charge(1, 3 * H, 5 * H)])["spans"][0]
        self.assertNotIn("duration", span)
        self.assertNotIn("computedAttributes", span)
        self.assertEqual(set(span),
                         {"spanId", "type", "startOffset", "arguments", "parentId", "directiveId"})

    def test_a_finished_activity_has_both(self):
        span = run([charge(1, 1 * H, 1 * H)])["spans"][0]
        self.assertEqual(span["duration"], 1 * H)
        self.assertIn("computedAttributes", span)

    def test_an_activity_ending_exactly_at_the_window_edge_counts_as_finished(self):
        span = run([charge(1, 3 * H, 1 * H)])["spans"][0]
        self.assertEqual(span["duration"], 1 * H)
        self.assertIn("computedAttributes", span)

    def test_duration_and_computed_attributes_are_never_separated(self):
        result = run([charge(1, 0, 1 * H), charge(2, 3 * H, 9 * H),
                      discharge(3, 2 * H, 2 * H), discharge(4, 1 * H, 7 * H)])
        for span in result["spans"]:
            self.assertEqual("duration" in span, "computedAttributes" in span,
                             "span %s has one of duration/computedAttributes but not the other"
                             % span["spanId"])

    def test_a_span_reports_the_effective_arguments_not_a_raw_echo(self):
        """Undeclared names would ride through into the span, where merlin's ingest gate flags
        every span carrying an argument the model never declared."""
        span = run([directive(1, "Charge", 0, duration=1 * H, bogus="x", rate=None)])["spans"][0]
        self.assertEqual(span["arguments"], {"duration": 1 * H, "rate": 1.0})   # default filled in
        self.assertNotIn("bogus", span["arguments"])

    def test_span_identity_fields(self):
        result = run([charge(7, 0, 1 * H), discharge(9, 1 * H, 1 * H)])
        self.assertEqual([s["spanId"] for s in result["spans"]], [1, 2])
        self.assertEqual([s["directiveId"] for s in result["spans"]], [7, 9])
        self.assertEqual([s["parentId"] for s in result["spans"]], [None, None])
        self.assertEqual([s["type"] for s in result["spans"]], ["Charge", "Discharge"])


# --- computed attributes ------------------------------------------------------------------------
class TestComputedAttributes(SimTestCase):
    def test_soc_delta_is_the_charge_moved_inside_the_window(self):
        span = run([charge(1, 1 * H, 2 * H, rate=1.5)])["spans"][0]
        self.assertAlmostEqual(span["computedAttributes"]["socDelta"], 1.5 * 7200)

    def test_soc_delta_is_negative_for_a_discharge(self):
        span = run([discharge(1, 0, 1 * H, load=2.0)])["spans"][0]
        self.assertAlmostEqual(span["computedAttributes"]["socDelta"], -2.0 * 3600)

    def test_soc_delta_matches_the_declared_computed_attributes_schema(self):
        """A value that does not fit the declared schema is rejected by merlin's results gate."""
        result = run([charge(1, 0, 1 * H), discharge(2, 1 * H, 30 * MIN)])
        for span in result["spans"]:
            self.assertIsNone(nonconformance(span["computedAttributes"],
                                             pms.COMPUTED_ATTRIBUTES_SCHEMA), span)

    def test_soc_delta_agrees_with_the_profile_the_activity_produced(self):
        result = run([charge(1, 1 * H, 2 * H, rate=1.5)])
        moved = sum((hi - lo) / S * rate for lo, hi, rate in rates(result))
        self.assertAlmostEqual(result["spans"][0]["computedAttributes"]["socDelta"], moved)

    def test_soc_delta_is_never_actually_truncated(self):
        """computedAttributes is emitted only when `start + dur <= sim_dur`, i.e. only when the
        activity fits. So socDelta always equals rate * full duration and its window-clamped form
        (`rate * (end - start)`) can never differ. Pinned so the pairing stays deliberate: if
        unfinished spans ever start carrying computed attributes, this is where it shows up."""
        for start, dur, sim in ((0, 1 * H, 4 * H), (3 * H, 1 * H, 4 * H), (1 * H, 0, 4 * H)):
            with self.subTest(start=start, duration=dur):
                span = run([charge(1, start, dur, rate=1.0)], duration=sim)["spans"][0]
                self.assertAlmostEqual(span["computedAttributes"]["socDelta"], dur / S)


# --- ValueSchema conformance ----------------------------------------------------------------------
class TestNonconformance(unittest.TestCase):
    def assertConforms(self, value, schema):
        self.assertIsNone(nonconformance(value, schema),
                          "%r should satisfy %r" % (value, schema))

    def assertRejects(self, value, schema):
        self.assertIsNotNone(nonconformance(value, schema),
                             "%r should NOT satisfy %r" % (value, schema))

    def test_real(self):
        for v in (1.0, -2.5, 0.0, 7):
            self.assertConforms(v, REAL)
        for v in ("1.0", [], {}, float("inf"), float("nan"), float("-inf"), True):
            self.assertRejects(v, REAL)

    def test_an_int_satisfies_real(self):
        """PlanDev widens int to real; refusing it would reject a perfectly ordinary argument."""
        self.assertConforms(7, REAL)
        self.assertConforms(0, REAL)

    def test_int(self):
        for v in (0, -3, 10 ** 20):
            self.assertConforms(v, INT)
        for v in (1.0, 1.5, "1", []):
            self.assertRejects(v, INT)

    def test_a_bool_does_not_satisfy_int(self):
        """bool is an int subclass in Python; PlanDev's int schema does not accept one, and a
        `True` silently stored as 1 is a type error that only surfaces much later."""
        self.assertRejects(True, INT)
        self.assertRejects(False, INT)
        self.assertRejects(True, REAL)

    def test_duration(self):
        self.assertConforms(0, DURATION)
        self.assertConforms(-1_000, DURATION)
        self.assertConforms(3_600_000_000, DURATION)

    def test_a_non_integral_value_does_not_satisfy_duration(self):
        """Durations are integer microseconds on the wire; 1.5 has no representation."""
        self.assertRejects(1.5, DURATION)
        self.assertRejects(1.0, DURATION)          # float, even though integral
        self.assertRejects("01:00:00", DURATION)
        self.assertRejects(True, DURATION)

    def test_boolean(self):
        self.assertConforms(True, BOOLEAN)
        self.assertConforms(False, BOOLEAN)
        for v in (1, 0, "true", []):
            self.assertRejects(v, BOOLEAN)

    def test_string_and_path(self):
        self.assertConforms("", STRING)
        self.assertConforms("x", {"type": "path"})
        self.assertRejects(5, STRING)
        self.assertRejects(["x"], STRING)

    def test_variant(self):
        self.assertConforms("Idle", VARIANT)
        self.assertConforms("Charging", VARIANT)
        self.assertRejects("Discharging", VARIANT)     # not among this schema's variants
        self.assertRejects(0, VARIANT)                 # not the ordinal, the key
        self.assertIn("Idle", nonconformance("nope", VARIANT))

    def test_series(self):
        self.assertConforms([], {"type": "series", "items": INT})
        self.assertConforms([1, 2, 3], {"type": "series", "items": INT})
        self.assertRejects("abc", {"type": "series", "items": STRING})
        self.assertIn("at [1]", nonconformance([1, "x"], {"type": "series", "items": INT}))

    def test_series_recurses_into_its_items(self):
        nested = {"type": "series", "items": {"type": "series", "items": INT}}
        self.assertConforms([[1], [2, 3]], nested)
        self.assertRejects([[1], ["x"]], nested)

    def test_struct(self):
        schema = {"type": "struct", "items": {"a": INT, "b": STRING}}
        self.assertConforms({"a": 1, "b": "x"}, schema)
        self.assertRejects(["a", 1], schema)
        self.assertIn("at .a", nonconformance({"a": "x", "b": "y"}, schema))

    def test_a_struct_rejects_a_missing_field(self):
        schema = {"type": "struct", "items": {"a": INT, "b": STRING}}
        self.assertIn("missing field 'b'", nonconformance({"a": 1}, schema))

    def test_a_struct_rejects_an_unexpected_field(self):
        schema = {"type": "struct", "items": {"a": INT}}
        self.assertIn("unexpected field 'z'", nonconformance({"a": 1, "z": 2}, schema))

    def test_null_is_accepted_against_any_schema(self):
        """A schema says nothing about nullability; absence is handled by default resolution."""
        for schema in (REAL, INT, DURATION, BOOLEAN, STRING, VARIANT,
                       {"type": "series", "items": INT},
                       {"type": "struct", "items": {"a": INT}}):
            self.assertConforms(None, schema)

    def test_every_declared_resource_and_config_schema_is_understood(self):
        for name, schema in pms.RESOURCE_TYPES.items():
            self.assertIn(schema["type"],
                          {"real", "int", "duration", "boolean", "string", "path",
                           "variant", "series", "struct"}, name)


# --- effective arguments ---------------------------------------------------------------------------
class TestEffectiveArgs(unittest.TestCase):
    def test_defaults_fill_in_for_absent_optional_parameters(self):
        self.assertEqual(effective_args("Charge", {"duration": 5}), {"duration": 5, "rate": 1.0})
        self.assertEqual(effective_args("Discharge", {"duration": 5}), {"duration": 5, "load": 2.0})

    def test_a_supplied_value_wins_over_the_default(self):
        self.assertEqual(effective_args("Charge", {"duration": 5, "rate": 9.0}),
                         {"duration": 5, "rate": 9.0})

    def test_an_explicit_null_counts_as_absent_so_the_default_applies(self):
        """Otherwise a null sails past default resolution and reaches the arithmetic as None."""
        self.assertEqual(effective_args("Charge", {"duration": 5, "rate": None}),
                         {"duration": 5, "rate": 1.0})

    def test_an_explicit_null_on_a_required_parameter_leaves_it_absent(self):
        self.assertEqual(effective_args("Charge", {"duration": None}), {"rate": 1.0})

    def test_undeclared_arguments_are_dropped_not_echoed(self):
        self.assertEqual(effective_args("Charge", {"duration": 5, "bogus": 1, "rate": 2.0}),
                         {"duration": 5, "rate": 2.0})

    def test_an_unknown_activity_type_yields_nothing(self):
        self.assertEqual(effective_args("Nope", {"duration": 5}), {})

    def test_none_and_empty_arguments_are_both_accepted(self):
        self.assertEqual(effective_args("Charge", None), {"rate": 1.0})
        self.assertEqual(effective_args("Charge", {}), {"rate": 1.0})

    def test_undeclared_lists_exactly_the_unknown_names(self):
        self.assertEqual(undeclared("Charge", {"duration": 1, "rate": 2, "x": 3, "y": 4}),
                         ["x", "y"])
        self.assertEqual(undeclared("Charge", {}), [])
        self.assertEqual(undeclared("Charge", None), [])


# --- validation --------------------------------------------------------------------------------------
class TestValidateOne(unittest.TestCase):
    @staticmethod
    def messages(result):
        return [n["message"] for n in result["notices"]]

    @staticmethod
    def subjects(result):
        return [n["subjects"] for n in result["notices"]]

    def test_a_well_formed_activity_validates_green(self):
        result = validate_one("Charge", {"duration": 1 * H, "rate": 2.0}, False)
        self.assertTrue(result["valid"])
        self.assertEqual(result["notices"], [])
        self.assertEqual(result["effectiveArguments"], {"duration": 1 * H, "rate": 2.0})

    def test_an_unknown_activity_type_is_reported_without_effective_arguments(self):
        result = validate_one("Nope", {}, False)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["effectiveArguments"])
        self.assertEqual(self.subjects(result), [[]])          # not attributable to a parameter
        self.assertIn("unknown activity type 'Nope'", self.messages(result))

    def test_a_missing_required_parameter_is_reported_against_that_parameter(self):
        result = validate_one("Charge", {}, False)
        self.assertFalse(result["valid"])
        self.assertEqual(self.messages(result), ["missing required parameter 'duration'"])
        self.assertEqual(self.subjects(result), [["duration"]])

    def test_an_explicit_null_counts_as_missing(self):
        result = validate_one("Charge", {"duration": None}, False)
        self.assertFalse(result["valid"])
        self.assertIn("missing required parameter 'duration'", self.messages(result))

    def test_an_absent_optional_parameter_is_not_reported(self):
        result = validate_one("Charge", {"duration": 1 * H}, False)
        self.assertTrue(result["valid"])

    def test_an_unrecognized_parameter_is_reported(self):
        result = validate_one("Charge", {"duration": 1 * H, "bogus": 1}, False)
        self.assertFalse(result["valid"])
        self.assertIn("unrecognized parameter 'bogus'", self.messages(result))
        self.assertEqual(self.subjects(result), [["bogus"]])

    def test_a_type_wrong_argument_is_reported(self):
        """merlin delegates authoritative validation here, so this is the only typecheck there is."""
        result = validate_one("Charge", {"duration": "01:00:00"}, False)
        self.assertFalse(result["valid"])
        self.assertTrue(any("expected a duration as integer microseconds" in m
                            for m in self.messages(result)), self.messages(result))

    def test_a_bool_supplied_for_a_real_is_reported(self):
        result = validate_one("Charge", {"duration": 1 * H, "rate": True}, False)
        self.assertFalse(result["valid"])
        self.assertTrue(any("rate" in m and "finite real" in m for m in self.messages(result)))

    def test_semantic_checks_on_rate_and_load(self):
        for typ, param in (("Charge", "rate"), ("Discharge", "load")):
            for bad in (0, -1, -0.5):
                with self.subTest(param=param, value=bad):
                    result = validate_one(typ, {"duration": 1 * H, param: bad}, False)
                    self.assertFalse(result["valid"])
                    self.assertIn([param], self.subjects(result))
                    self.assertTrue(any("must be > 0" in m for m in self.messages(result)))

    def test_a_negative_duration_is_reported(self):
        result = validate_one("Charge", {"duration": -1}, False)
        self.assertFalse(result["valid"])
        self.assertEqual(self.subjects(result), [["duration"]])
        self.assertTrue(any("must be >= 0" in m for m in self.messages(result)))

    def test_a_zero_duration_is_allowed(self):
        self.assertTrue(validate_one("Charge", {"duration": 0}, False)["valid"])

    def test_several_problems_are_all_reported_at_once(self):
        result = validate_one("Charge", {"rate": -1.0, "bogus": 1}, False)
        self.assertFalse(result["valid"])
        self.assertEqual(sorted(self.messages(result)),
                         sorted(["missing required parameter 'duration'",
                                 "unrecognized parameter 'bogus'",
                                 "'rate' must be > 0 (got -1.0)"]))

    def test_effective_only_short_circuits_every_check(self):
        """The editor asks for effective arguments while a form is still half-filled; that is not
        the moment to paint it red."""
        result = validate_one("Charge", {}, True)
        self.assertTrue(result["valid"])
        self.assertEqual(result["notices"], [])
        self.assertEqual(result["effectiveArguments"], {"rate": 1.0})

    def test_effective_only_still_refuses_an_unknown_type(self):
        result = validate_one("Nope", {}, True)
        self.assertFalse(result["valid"])

    def test_effective_arguments_are_returned_even_when_invalid(self):
        result = validate_one("Charge", {"bogus": 1}, False)
        self.assertFalse(result["valid"])
        self.assertEqual(result["effectiveArguments"], {"rate": 1.0})


# --- configuration -----------------------------------------------------------------------------------
class TestEffectiveConfig(unittest.TestCase):
    def test_defaults_fill_in(self):
        self.assertEqual(effective_config(None), {"initialSoC": 50.0, "initialCycles": 0})
        self.assertEqual(effective_config({}), {"initialSoC": 50.0, "initialCycles": 0})

    def test_supplied_values_win(self):
        self.assertEqual(effective_config({"initialSoC": 10.0, "initialCycles": 3}),
                         {"initialSoC": 10.0, "initialCycles": 3})

    def test_a_null_means_use_the_default(self):
        self.assertEqual(effective_config({"initialSoC": None})["initialSoC"], 50.0)

    def test_only_declared_keys_come_out(self):
        self.assertEqual(set(effective_config({})), {"initialSoC", "initialCycles"})

    def test_an_unknown_key_is_refused_rather_than_silently_honoured(self):
        with self.assertRaises(BadRequest) as ctx:
            effective_config({"initialSOC": 10.0})        # note the casing typo
        self.assertIn("unknown configuration parameter 'initialSOC'", str(ctx.exception))

    def test_values_are_typechecked(self):
        for key, bad in (("initialCycles", 1.5), ("initialCycles", True),
                         ("initialSoC", "50"), ("initialSoC", [])):
            with self.subTest(key=key, value=bad):
                with self.assertRaises(BadRequest):
                    effective_config({key: bad})

    def test_the_configuration_reaches_the_simulation(self):
        result = simulate({"planStart": PLAN_START, "duration": 2 * H,
                           "configuration": {"initialSoC": 12.5, "initialCycles": 4},
                           "directives": [charge(1, 0, 1 * H)]})
        self.assertEqual(timeline(result)[0][2]["initial"], 12.5)
        self.assertEqual([dyn for _, _, dyn in timeline(result, "Cycles")], [5, 5])


# --- identity hash -----------------------------------------------------------------------------------
class TestIdentityHash(unittest.TestCase):
    """The attestation merlin stores. A spurious change refuses simulations and invalidates the
    cache; a missed change lets PlanDev's stored beliefs drift from the model silently."""

    def setUp(self):
        self.saved_model = copy.deepcopy(pms.MODEL)
        self.saved_config = list(pms.CONFIG)
        self.baseline = identity_hash()
        self.addCleanup(self.restore)

    def restore(self):
        pms.MODEL.clear()
        pms.MODEL.update(copy.deepcopy(self.saved_model))
        pms.CONFIG[:] = self.saved_config

    def test_the_hash_is_stable_across_calls(self):
        self.assertEqual(identity_hash(), identity_hash())
        self.assertEqual(len(identity_hash()), 16)

    def test_models_list_and_introspect_report_the_same_hash(self):
        self.assertEqual(models_list()["models"][0]["identityHash"], self.baseline)
        self.assertEqual(introspect()["identityHash"], self.baseline)

    def test_reordering_parameters_moves_the_hash(self):
        """Parameter order IS something PlanDev stores. merlin assigns each parameter an `order` from
        its index in the introspection array (ResponseSerializers.serializeParameters), persists it,
        reads activity types back sorted by it (GetActivityTypesAction), and plandev-ui lays the
        argument form out in that order.

        An earlier version sorted parameters before hashing, so a reordered declaration left the
        stored order stale while the attestation claimed nothing had changed -- the form would render
        in the old sequence with no indication why."""
        pms.MODEL["Charge"] = list(reversed(pms.MODEL["Charge"]))
        self.assertNotEqual(identity_hash(), self.baseline)

    def test_flipping_a_parameter_from_required_to_optional_changes_the_hash(self):
        """requiredParameters is persisted in activity_type and merlin's gate enforces it, so this
        changes what PlanDev believes without changing any schema."""
        pms.MODEL["Charge"] = [("duration", {"type": "duration"}, 60 * S),
                               ("rate", {"type": "real"}, 1.0)]
        self.assertNotEqual(identity_hash(), self.baseline)

    def test_flipping_a_parameter_from_optional_to_required_changes_the_hash(self):
        pms.MODEL["Charge"] = [("duration", {"type": "duration"}, None),
                               ("rate", {"type": "real"}, None)]
        self.assertNotEqual(identity_hash(), self.baseline)

    def test_changing_a_default_value_changes_the_hash(self):
        pms.MODEL["Charge"] = [("duration", {"type": "duration"}, None),
                               ("rate", {"type": "real"}, 2.0)]
        self.assertNotEqual(identity_hash(), self.baseline)

    def test_changing_a_parameter_schema_changes_the_hash(self):
        pms.MODEL["Charge"] = [("duration", {"type": "duration"}, None),
                               ("rate", {"type": "int"}, 1)]
        self.assertNotEqual(identity_hash(), self.baseline)

    def test_renaming_or_adding_a_parameter_changes_the_hash(self):
        pms.MODEL["Charge"] = list(self.saved_model["Charge"]) + [("extra", {"type": "int"}, 0)]
        self.assertNotEqual(identity_hash(), self.baseline)

    def test_adding_or_removing_an_activity_type_changes_the_hash(self):
        pms.MODEL["Trickle"] = [("duration", {"type": "duration"}, None)]
        self.assertNotEqual(identity_hash(), self.baseline)
        del pms.MODEL["Trickle"]
        self.assertEqual(identity_hash(), self.baseline)
        del pms.MODEL["Discharge"]
        self.assertNotEqual(identity_hash(), self.baseline)

    def test_changing_a_configuration_default_changes_the_hash(self):
        pms.CONFIG[:] = [("initialSoC", {"type": "real"}, 99.0),
                         ("initialCycles", {"type": "int"}, 0)]
        self.assertNotEqual(identity_hash(), self.baseline)

    # NOTE: CONFIG entries are hashed in declaration order while activity parameters are sorted, so
    # reordering the CONFIG list DOES move the hash and reordering an activity's parameters does
    # not. Given that merlin persists an `order` for BOTH (activity_type.parameters and
    # mission_model_parameters.parameters, both `{name: {schema, order}}`), the CONFIG side looks
    # right and the activity side looks wrong -- but that is a product decision. The asymmetry is
    # deliberately not asserted here in either direction; it is an open question, not a behaviour.

    def test_restoring_the_declaration_restores_the_hash(self):
        """Guards the fixture itself: if restore() were broken, every later test would be lying."""
        pms.MODEL["Charge"] = [("duration", {"type": "duration"}, 1)]
        self.assertNotEqual(identity_hash(), self.baseline)
        self.restore()
        self.assertEqual(identity_hash(), self.baseline)


# --- error handling ------------------------------------------------------------------------------
class TestSimulateErrors(unittest.TestCase):
    """Caller errors must be BadRequest (a 4xx naming the offending directive), never a 500."""

    def assertBadRequest(self, directives, fragment, duration=4 * H, configuration=None):
        with self.assertRaises(BadRequest) as ctx:
            run(directives, duration=duration, configuration=configuration)
        self.assertIn(fragment, str(ctx.exception))
        return str(ctx.exception)

    def test_unknown_activity_type(self):
        message = self.assertBadRequest([directive(3, "Levitate", 0, duration=1 * H)],
                                        "unknown activity type 'Levitate'")
        self.assertIn("directive 3", message)          # the offending directive is named

    def test_missing_required_parameter(self):
        self.assertBadRequest([directive(1, "Charge", 0, rate=1.0)],
                              "missing required parameter 'duration'")

    def test_an_explicit_null_on_a_required_parameter_is_a_missing_parameter(self):
        self.assertBadRequest([directive(1, "Charge", 0, duration=None)],
                              "missing required parameter 'duration'")

    def test_negative_activity_duration(self):
        self.assertBadRequest([charge(1, 0, -1)], "negative duration -1")

    def test_type_wrong_argument(self):
        self.assertBadRequest([directive(1, "Charge", 0, duration="01:00:00")],
                              "expected a duration as integer microseconds")
        self.assertBadRequest([directive(1, "Charge", 0, duration=1 * H, rate="fast")],
                              "expected a finite real")
        self.assertBadRequest([directive(1, "Charge", 0, duration=1.5)],
                              "expected a duration as integer microseconds")

    def test_a_non_finite_rate_is_refused_before_it_can_poison_the_profile(self):
        """json.dumps would otherwise emit bare Infinity, which is not legal JSON at all."""
        self.assertBadRequest([directive(1, "Charge", 0, duration=1 * H, rate=float("inf"))],
                              "expected a finite real")

    def test_negative_simulation_duration(self):
        self.assertBadRequest([], "simulation duration must be >= 0", duration=-1)

    def test_unknown_configuration_parameter(self):
        self.assertBadRequest([], "unknown configuration parameter 'nope'",
                              configuration={"nope": 1})

    def test_a_bad_directive_fails_the_whole_request_rather_than_being_skipped(self):
        """A silently dropped directive is a plan that simulates green and is simply missing work."""
        self.assertBadRequest([charge(1, 0, 1 * H), directive(2, "Levitate", 1 * H)],
                              "unknown activity type 'Levitate'")

    def test_an_empty_request_is_valid(self):
        result = run([])
        self.assertEqual(result["spans"], [])
        self.assertEqual(total_duration(result["realProfiles"]["SoC"]["segments"]), 4 * H)


# --- introspection ---------------------------------------------------------------------------------
class TestIntrospection(unittest.TestCase):
    def test_every_declared_activity_type_is_introspected(self):
        types = {a["name"]: a for a in introspect()["activityTypes"]}
        self.assertEqual(set(types), set(pms.MODEL))

    def test_required_parameters_are_exactly_those_without_a_default(self):
        for act in introspect()["activityTypes"]:
            expected = [n for n, _s, d in pms.MODEL[act["name"]] if d is None]
            self.assertEqual(act["requiredParameters"], expected, act["name"])

    def test_every_activity_type_declares_the_computed_attributes_schema(self):
        for act in introspect()["activityTypes"]:
            self.assertEqual(act["computedAttributesSchema"], pms.COMPUTED_ATTRIBUTES_SCHEMA)

    def test_resource_and_configuration_types_are_reported(self):
        intro = introspect()
        self.assertEqual({r["name"] for r in intro["resourceTypes"]}, set(pms.RESOURCE_TYPES))
        self.assertEqual([p["name"] for p in intro["parameters"]], [n for n, _s, _d in pms.CONFIG])

    def test_the_simulated_resources_are_exactly_the_introspected_ones(self):
        """A resource that introspects but produces no segments looks like 'the model just didn't
        touch it' rather than a bug."""
        result = run([charge(1, 0, 1 * H)])
        produced = set(result["realProfiles"]) | set(result["discreteProfiles"])
        self.assertEqual(produced, {r["name"] for r in introspect()["resourceTypes"]})
        for name, prof in dict(result["realProfiles"], **result["discreteProfiles"]).items():
            self.assertEqual(prof["schema"], pms.RESOURCE_TYPES[name])
            self.assertTrue(prof["segments"], "%s produced no segments" % name)

    def test_every_discrete_value_conforms_to_its_own_declared_schema(self):
        result = run([charge(1, 0, 1 * H), discharge(2, 1 * H, 1 * H)])
        for name, prof in result["discreteProfiles"].items():
            for seg in prof["segments"]:
                self.assertIsNone(nonconformance(seg["dynamics"], prof["schema"]),
                                  "%s: %r" % (name, seg["dynamics"]))

    def test_the_model_list_advertises_one_model(self):
        models = models_list()["models"]
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["key"], pms.MODEL_KEY)
        self.assertEqual(models[0]["version"], pms.MODEL_VERSION)


class TestModuleIsImportable(unittest.TestCase):
    def test_importing_the_module_does_not_start_a_server(self):
        """Server startup is behind `if __name__ == "__main__"`. If it ever moves to module scope
        this test file would hang on import instead of failing, so the guard is pinned by the
        absence of the names that block only creates."""
        self.assertFalse(hasattr(pms, "srv"))
        self.assertFalse(hasattr(pms, "PORT"))
        with open(os.path.abspath(pms.__file__)) as f:
            source = f.read()
        self.assertIn('if __name__ == "__main__":', source)
        head = source.split('if __name__ == "__main__":')[0]
        self.assertNotIn("serve_forever", head)


if __name__ == "__main__":
    unittest.main()
