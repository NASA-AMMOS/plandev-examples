#!/usr/bin/env python3
"""Tests for writer.py -- the run-transfer reader and writer.

    python3 test_writer.py            # offline; stdlib only, no jsonschema, no network
    python3 test_writer.py -v

The companion suite, `test_run_transfer.py`, tests the JSON SCHEMA against the same fixtures and
needs `jsonschema`. This one tests the producer, and deliberately needs nothing: a producer is the
party most likely to be outside PlanDev, so the module they copy has to be checkable where they are.

What these pin hardest are the properties that fail SILENTLY:

  * The round trip. A writer nobody can read back is a writer nobody can test -- and a field the
    writer cannot express is a field that simply goes missing from every run it writes.
  * The `1e400` rule. `json.dumps` writes a bare `Infinity`, which is not JSON at all, and
    `JSON.stringify` writes `null`, which is the wire spelling of a profile GAP -- a wrong run,
    stored, with nothing anywhere to complain.
  * The declaration digest. It decides whether a re-imported run reuses the model it already made
    or creates a second one beside it, and it has a second implementation in TypeScript that it has
    to agree with byte for byte.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import writer as rt                                                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1_000_000
VALID_RUN = os.path.join(HERE, "fixtures", "valid", "synthetic.run.json")

#: The digest of the valid fixture's declaration, pinned HERE and in aerie-gateway's
#: `run-transfer.test.ts` against the same file. Two implementations in two languages decide whether
#: a re-imported run reuses the model it already created or makes a second one beside it, so the
#: only useful test of either is that it agrees with the other. Regenerate with:
#:     python3 -c "import writer, json; print(writer.declaration_digest(
#:         json.load(open('fixtures/valid/synthetic.run.json'))['model']))"
SYNTHETIC_DIGEST = "a27d82bfcd1a4579"


class TestRunTransferRoundTrip(unittest.TestCase):
    """Read the frozen fixture, rebuild it from the writer's own types, compare.

    This is the whole argument that the writer models the FORMAT rather than the subset one
    producer happened to need. The fixture was written by hand against the spec and carries every
    awkward case on purpose -- a two-level decomposition, an unfinished span, a profile gap, an
    anchored directive with `anchored_to_start: false`, an optional `subsystem` -- so anything the
    writer cannot express shows up here as a diff rather than as a missing feature nobody notices.
    """

    def setUp(self):
        self.document = rt.read_run(VALID_RUN)

    def test_parse_then_write_reproduces_the_file(self):
        self.assertEqual(rt.parse_run(self.document).to_json(), self.document)

    def test_and_reproduces_it_byte_for_byte(self):
        # Serialized through the same writer on both sides, so this also pins KEY ORDER, which deep
        # equality does not. (Not compared against the fixture's own bytes: that file is indented
        # for a reader, with blank lines between its members, and none of that is data.)
        rebuilt = rt.parse_run(self.document).to_json()
        self.assertEqual(rt.dumps_run(rebuilt), rt.dumps_run(self.document))

    def test_the_fixture_has_no_problems(self):
        # The pre-flight check and the frozen fixture agree: a file the gate accepts is a file this
        # reports nothing about. If a rule here is stricter than the gate's, this is where it shows.
        self.assertEqual(rt.run_problems(self.document), [])

    def test_the_digest_matches_the_gateway(self):
        self.assertEqual(rt.declaration_digest(self.document["model"]), SYNTHETIC_DIGEST)

    def test_declaration_survives_the_round_trip(self):
        declaration = rt.parse_run(self.document).declaration
        self.assertEqual([a.name for a in declaration.activity_types],
                         ["Observe", "Slew", "Downlink"])
        observe = declaration.activity_type("Observe")
        self.assertEqual([p.name for p in observe.parameters], ["target", "priority"])
        self.assertEqual(observe.required_parameters, ["target"])
        self.assertEqual(observe.subsystem, "payload")
        self.assertEqual([r.name for r in declaration.resource_types],
                         ["/battery/soc", "/comm/mode"])


class TestRunTransferWriter(unittest.TestCase):
    """The writer's own decisions, on a model small enough to read."""

    def declaration(self):
        return rt.ModelDeclaration(
            name="demo", version="2.1.0",
            activity_types=[rt.ActivityType(
                "Observe", [rt.Parameter("target", {"type": "string"}),
                            rt.Parameter("priority", {"type": "int"})],
                computed_attributes_schema={"type": "struct", "items": {}},
                required_parameters=["target"])],
            resource_types=[rt.ResourceType("/battery/soc", {"type": "real"})],
            config_parameters=[rt.Parameter("initialSoc", {"type": "real"})])

    def run_transfer(self, **kwargs):
        defaults = dict(declaration=self.declaration(), mission="Demo", plan_name="p",
                        plan_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        plan_duration_us=3600 * S)
        defaults.update(kwargs)
        return rt.RunTransfer(**defaults)

    def test_a_declared_model_says_it_cannot_be_simulated(self):
        model = self.run_transfer().to_json()["model"]
        simulation = model["capabilities"]["simulation"]
        self.assertFalse(simulation["supported"])
        # An unsupported capability without a reason renders as "unavailable" with no explanation,
        # which reads as broken rather than as intended.
        self.assertTrue(simulation["reason"])

    def test_a_live_backend_capability_is_not_carried_into_a_run_file(self):
        # The trap this closes: `planImport` and `plandevScheduling` both describe what a REACHABLE
        # backend can do. There is no backend behind an imported run, so inheriting them would
        # publish an offer PlanDev cannot meet -- a plan-import button that has nothing to call.
        # `run_model` takes the declaration's types and nothing else, so a live backend's
        # capabilities cannot ride along even when the caller hands over an object that has them.
        model = rt.run_model(self.declaration(), "Demo")
        self.assertEqual(list(model["capabilities"]), ["simulation"])

    def test_a_producer_may_still_declare_capabilities_explicitly(self):
        model = self.run_transfer(capabilities={rt.PLANDEV_SCHEDULING: rt.supported()}) \
            .to_json()["model"]
        self.assertEqual(sorted(model["capabilities"]), ["plandevScheduling", "simulation"])

    def test_a_missing_computed_attributes_schema_is_refused_not_guessed(self):
        # Guessing the closed empty struct would turn a missing declaration into a WRONG one, and
        # the model's own spans would then be refused for carrying attributes it does compute.
        declaration = rt.ModelDeclaration(name="d", activity_types=[rt.ActivityType("Observe", [])])
        with self.assertRaises(rt.RunTransferError) as caught:
            rt.run_model(declaration, "Demo")
        self.assertIn("computedAttributesSchema", str(caught.exception))
        self.assertIn('"items": {}', str(caught.exception))

    def test_parameter_order_is_preserved(self):
        # merlin persists each parameter's INDEX as its `order`, reads activity types back sorted by
        # it, and plandev-ui lays the argument form out in that sequence. Sorting here would render
        # every form in the wrong order.
        model = self.run_transfer().to_json()["model"]
        self.assertEqual([p["name"] for p in model["activityTypes"][0]["parameters"]],
                         ["target", "priority"])
        self.assertEqual(model["activityTypes"][0]["requiredParameters"], ["target"])

    def test_the_two_timestamps_use_different_calendars(self):
        document = self.run_transfer(response={"spans": []}).to_json()
        self.assertEqual(document["plan"]["start_time"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(document["results"]["startTime"], "2026-001T00:00:00")

    def test_a_directive_defaults_its_name_to_its_local_id(self):
        plan = self.run_transfer(directives=[rt.RunDirective("a1", "Observe")]).to_json()["plan"]
        self.assertEqual(plan["activities"][0]["name"], "a1")
        self.assertEqual(plan["activities"][0]["start_offset"], "00:00:00")

    def test_a_span_references_its_directive_by_local_id(self):
        # The `localId` contract: a backend echoes back whatever id it was handed, so a producer
        # that passes the local id as the directive id gets the file's keyspace for nothing.
        document = self.run_transfer(
            directives=[rt.RunDirective("a1", "Observe", arguments={"target": "Europa"})],
            response={"spans": [{"spanId": 1, "type": "Observe", "startOffset": 0,
                                 "duration": 10 * S, "directiveId": "a1",
                                 "arguments": {"target": "Europa"}, "computedAttributes": {}}]}
        ).to_json()
        span = document["results"]["spans"][0]
        self.assertEqual(span["directiveLocalId"], "a1")
        self.assertNotIn("directiveId", span)
        self.assertEqual(rt.run_problems(document), [])

    def test_an_unfinished_span_omits_its_fields_rather_than_nulling_them(self):
        # merlin reads these with `optionalField`, so an explicit null is a PARSE FAILURE rather
        # than an omission -- and the pair is how it tells finished from unfinished at all.
        document = self.run_transfer(response={"spans": [
            {"spanId": 1, "type": "Observe", "startOffset": 0, "arguments": {"target": "x"}}]}
        ).to_json()
        span = document["results"]["spans"][0]
        self.assertNotIn("duration", span)
        self.assertNotIn("computedAttributes", span)
        self.assertNotIn("parentId", span)

    def test_a_profile_takes_its_schema_from_the_declaration(self):
        # A model restating a schema it already declared is a second copy free to drift from the
        # first, and the drift is invisible: resources typed one way in the editor, another in the
        # results.
        document = self.run_transfer(response={
            "realProfiles": {"/battery/soc": {"segments": [
                {"duration": 3600 * S, "dynamics": {"initial": 1.0, "rate": 0.0}}]}},
            "spans": []}).to_json()
        self.assertEqual(document["results"]["profiles"]["/battery/soc"],
                         {"type": "real", "schema": {"type": "real"},
                          "segments": [{"duration": 3600 * S,
                                        "dynamics": {"initial": 1.0, "rate": 0.0}}]})

    def test_an_undeclared_resource_with_no_schema_is_refused_by_name(self):
        with self.assertRaises(rt.RunTransferError) as caught:
            self.run_transfer(response={"realProfiles": {"/nope": {"segments": []}},
                                        "spans": []}).to_json()
        self.assertIn("/nope", str(caught.exception))


class TestRunTransferSerialization(unittest.TestCase):
    """The `1e400` rule, which is where a run file quietly becomes a wrong one."""

    def test_an_infinity_is_written_as_the_only_portable_spelling(self):
        text = rt.dumps_run({"rate": float("inf"), "back": float("-inf")})
        self.assertIn("1e400", text)
        self.assertIn("-1e400", text)
        # The two tokens json.dumps would have written. Neither is JSON: ajv and JSON.parse reject
        # the whole file, so the run dies before anything can say which resource produced it.
        self.assertNotIn("Infinity", text)
        self.assertEqual(json.loads(text), {"rate": float("inf"), "back": float("-inf")})

    def test_a_string_that_merely_contains_the_word_is_left_alone(self):
        # Why the substitution goes through a random placeholder rather than a search over the
        # serialized text: a resource called "Infinity" is a legal resource.
        text = rt.dumps_run({"note": "Infinity and 1e400", "rate": float("inf")})
        self.assertEqual(json.loads(text)["note"], "Infinity and 1e400")

    def test_a_nan_is_refused_rather_than_rounded_to_an_infinity(self):
        # JSON has no NaN at ALL. `1e400` is an infinity, which is a different number, and a
        # producer silently shipping one for the other is worse than a file that never leaves.
        with self.assertRaises(rt.RunTransferError) as caught:
            rt.dumps_run({"rate": float("nan")})
        self.assertIn("NaN", str(caught.exception))

    def test_reading_refuses_the_tokens_python_alone_would_accept(self):
        path = os.path.join(tempfile.mkdtemp(), "bad.run.json")
        with open(path, "w") as handle:
            handle.write('{"rate": Infinity}')
        with self.assertRaises(rt.RunTransferError) as caught:
            rt.read_run(path)
        self.assertIn("1e400", str(caught.exception))

    def test_reading_1e400_yields_an_infinity(self):
        path = os.path.join(tempfile.mkdtemp(), "ok.run.json")
        with open(path, "w") as handle:
            handle.write('{"rate": 1e400}')
        self.assertEqual(rt.read_run(path), {"rate": float("inf")})

    def test_intervals_round_trip_including_negatives(self):
        for us in (0, 1, 999_999, S, 90 * S, 3600 * S, 86_400 * S, 90_061_000_001,
                   -S, -86_400 * S - 7_200 * S):
            self.assertEqual(rt.interval_to_us(rt.us_to_interval(us)), us, us)

    def test_a_negative_interval_signs_every_component(self):
        # `-1 days 02:00:00` parses as -22h, not -26h, in Postgres and in the UI's parser alike.
        self.assertEqual(rt.us_to_interval(-(86_400 + 7_200) * S), "-1 days -02:00:00")


class TestRunProblems(unittest.TestCase):
    """The pre-flight check: the gate's rules, applied before the upload instead of after."""

    def setUp(self):
        self.document = rt.read_run(VALID_RUN)

    def problems(self, mutate):
        document = json.loads(json.dumps(self.document))
        mutate(document)
        return rt.run_problems(document)

    def assertComplains(self, mutate, fragment):
        problems = self.problems(mutate)
        self.assertTrue(any(fragment in p for p in problems),
                        "expected %r among %r" % (fragment, problems))

    def test_an_undeclared_span_type(self):
        def mutate(d):
            d["results"]["spans"][1]["type"] = "Ghost"
        self.assertComplains(mutate, "not a registered activity type")

    def test_an_undeclared_span_argument(self):
        def mutate(d):
            d["results"]["spans"][0]["arguments"]["extra"] = 1
        self.assertComplains(mutate, "not a declared parameter")

    def test_a_missing_required_directive_argument(self):
        def mutate(d):
            del d["plan"]["activities"][0]["arguments"]["target"]
        self.assertComplains(mutate, "missing required parameter 'target'")

    def test_a_type_wrong_argument(self):
        def mutate(d):
            d["plan"]["activities"][0]["arguments"]["priority"] = "high"
        self.assertComplains(mutate, "argument 'priority'")

    def test_a_dangling_anchor(self):
        def mutate(d):
            d["plan"]["activities"][1]["anchor_id"] = "nope"
        self.assertComplains(mutate, "not a localId in this file")

    def test_a_duplicate_local_id(self):
        def mutate(d):
            d["plan"]["activities"][1]["localId"] = "a1"
        self.assertComplains(mutate, "duplicate localId")

    def test_a_span_claiming_a_directive_that_is_not_there(self):
        def mutate(d):
            d["results"]["spans"][0]["directiveLocalId"] = "a9"
        self.assertComplains(mutate, "not a directive in this file")

    def test_a_dangling_parent(self):
        def mutate(d):
            d["results"]["spans"][1]["parentId"] = 99
        self.assertComplains(mutate, "not a span in this result")

    def test_a_parent_cycle(self):
        def mutate(d):
            d["results"]["spans"][0]["parentId"] = 4
        self.assertComplains(mutate, "parent cycle")

    def test_a_profile_past_the_simulation(self):
        def mutate(d):
            d["results"]["profiles"]["/battery/soc"]["segments"][0]["duration"] += 1
        self.assertComplains(mutate, "past the simulation duration")

    def test_a_span_past_the_simulation(self):
        def mutate(d):
            d["results"]["spans"][0]["duration"] = d["results"]["duration"] + 1
        self.assertComplains(mutate, "past the simulation")

    def test_a_non_finite_rate(self):
        def mutate(d):
            d["results"]["profiles"]["/battery/soc"]["segments"][0]["dynamics"]["rate"] = \
                float("inf")
        self.assertComplains(mutate, "non-finite rate")

    def test_a_real_segment_whose_rate_arrived_as_null(self):
        # How a Rust model fails: serde_json writes a NaN as `null` and returns Ok, so the non-finite
        # value is gone before this process ever sees it. Only knowing that the position must hold a
        # number turns it back into an error.
        def mutate(d):
            d["results"]["profiles"]["/battery/soc"]["segments"][0]["dynamics"]["rate"] = None
        self.assertComplains(mutate, "non-numeric `rate`")

    def test_a_half_finished_span(self):
        def mutate(d):
            del d["results"]["spans"][0]["computedAttributes"]
        self.assertComplains(mutate, "a finished span carries both")

    def test_an_activity_type_that_is_not_a_typescript_identifier(self):
        def mutate(d):
            d["model"]["activityTypes"][1]["name"] = "Slew-2"
            d["results"]["spans"][1]["type"] = "Slew-2"
            d["results"]["spans"][3]["type"] = "Slew-2"
        self.assertComplains(mutate, "not a legal TypeScript identifier")

    def test_a_profile_gap_is_not_a_problem(self):
        # A segment with no `dynamics` says "this resource has no value here", which is legitimate.
        # The valid fixture already carries one; this pins that it stays legitimate.
        self.assertEqual(rt.run_problems(self.document), [])
        self.assertNotIn("dynamics", self.document["results"]["profiles"]["/comm/mode"]["segments"][2])

    def test_check_run_raises_with_every_problem_at_once(self):
        document = json.loads(json.dumps(self.document))
        document["plan"]["activities"][0]["type"] = "Ghost"
        document["results"]["spans"][0]["parentId"] = 99
        with self.assertRaises(rt.RunTransferError) as caught:
            rt.check_run(document)
        message = str(caught.exception)
        self.assertIn("Ghost", message)
        self.assertIn("99", message)


if __name__ == "__main__":
    unittest.main()
