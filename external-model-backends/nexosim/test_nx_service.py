#!/usr/bin/env python3
"""Tests for the NeXosim backend at the HOST boundary.

    cargo build --release            # or set NX_MODEL_BIN
    python3 test_nx_service.py -v

The model itself is tested in Rust (`cargo test`, 34 tests) and the generic half of the contract in
`../test_adapter_core.py`. What is left is everything that only exists once the Python host and the
Rust binary are both in the picture, and it is not a small set:

  * ACROSS-PROCESS STABILITY. Rust randomizes `HashMap` iteration PER PROCESS, so a map anywhere on
    the declaration path is invisible to a Rust unit test -- which runs in one process -- and shows
    up as an identity hash that changes every time the adapter restarts. Merlin STORES that hash as
    an attestation, so a moving one means a model that reports itself as drifted on every deploy.
    The only way to see it is to run `describe` twice, in two processes, and diff.
  * THE HOST'S OWN READING OF THE DECLARATION. `declaration_from_json` decides what is required,
    what the defaults are, and what goes into the hash. A declaration that is right in Rust and
    wrong once parsed is still wrong.
  * `check_response`. The adapter refuses to serialize a malformed result; a real run has to get
    past it, and the int-vs-float hazard has to be checked HERE, on the parsed Python values, since
    that is the shape merlin's `asInt()` will see.
  * THE TWO GAPS. Capabilities and deep validation are worked around in nx_service.py rather than
    in the host, so they need tests that would fail if either workaround were dropped.

Every test skips when the binary is absent rather than failing: it is a compiled artefact, and a
checkout that has not run `cargo build` should not look broken.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter_core                                                            # noqa: E402
import nx_service                                                              # noqa: E402
from adapter_core import BadRequest, ModelError, Registry, run_simulate, run_validate  # noqa: E402

US = 1_000_000
BINARY = nx_service.MODEL_BIN


def binary_present():
    return os.path.exists(BINARY) and os.access(BINARY, os.X_OK)


@unittest.skipUnless(binary_present(), "nx-model is not built; run `cargo build --release`")
class NexosimTestCase(unittest.TestCase):
    """One backend per test. Deliberately not shared: `ExecBackend` caches the declaration after the
    first `describe`, and a test that mutated it would leak into the next."""

    def setUp(self):
        self.backend = nx_service.backend()
        self.registry = Registry({nx_service.MODEL_KEY: self.backend})

    def simulate(self, duration_us, directives=(), **configuration):
        return run_simulate(self.backend, {"planStart": "2026-07-27T00:00:00Z",
                                           "duration": duration_us,
                                           "configuration": configuration,
                                           "directives": list(directives)})

    def validate(self, *activities, effective_only=False):
        return run_validate(self.backend, {"activities": list(activities),
                                           "effectiveOnly": effective_only})["results"]


def directive(id_, typ, start_us, **arguments):
    return {"id": id_, "type": typ, "startOffset": start_us, "arguments": arguments}


def describe():
    """One `describe`, in its own process. The point of shelling out rather than reusing a backend
    is that the process is the unit of interest."""
    return subprocess.run([BINARY, "describe"], capture_output=True, text=True, check=True).stdout


# --- across-process stability ------------------------------------------------------------------------
@unittest.skipUnless(binary_present(), "nx-model is not built; run `cargo build --release`")
class TestTheDeclarationDoesNotMoveBetweenProcesses(unittest.TestCase):
    def test_two_separate_describes_produce_byte_identical_documents(self):
        # A Rust HashMap iterates in a different order in every process. Inside one process it is
        # perfectly stable, so no Rust unit test can see this; the symptom is a declaration whose
        # parameter or resource order changes across a restart.
        self.assertEqual(describe(), describe())

    def test_the_identity_hash_survives_a_restart(self):
        # Merlin STORES this hash as an attestation that it introspected the model it is about to
        # simulate, and compares it later. One that moves on restart reports every redeployment as
        # model drift, which trains everyone to ignore the only signal that would catch real drift.
        first = adapter_core.declaration_from_json(json.loads(describe()), key="cryo")
        second = adapter_core.declaration_from_json(json.loads(describe()), key="cryo")
        self.assertEqual(first.identity_hash(), second.identity_hash())

    def test_reordering_the_parameters_does_move_the_hash(self):
        # The other half of the same property: an attestation that never moves attests to nothing.
        # Parameter order is persisted by merlin and lays out the argument form, so it has to be in.
        document = json.loads(describe())
        baseline = adapter_core.declaration_from_json(document, key="cryo").identity_hash()
        observe = document["activityTypes"][0]
        observe["parameters"] = [observe["parameters"][1], observe["parameters"][0],
                                 *observe["parameters"][2:]]
        self.assertNotEqual(
            adapter_core.declaration_from_json(document, key="cryo").identity_hash(), baseline)


# --- the declaration, as the host reads it -------------------------------------------------------------
class TestDeclaration(NexosimTestCase):
    def test_introspection_reports_the_parameters_in_the_order_rust_emitted_them(self):
        # Order survives Rust -> JSON -> declaration_from_json -> introspect, which is four places
        # it could be sorted or bucketed. Merlin assigns each parameter an `order` from its index in
        # this array and plandev-ui renders the form in it.
        introspection = self.backend.declaration().introspect()
        self.assertEqual([a["name"] for a in introspection["activityTypes"]],
                         ["Observe", "Downlink", "SetCoolerSetpoint"])
        self.assertEqual([p["name"] for p in introspection["activityTypes"][0]["parameters"]],
                         ["duration", "targetName", "framePeriod", "powerWatts"])

    def test_only_the_parameters_without_defaults_are_required(self):
        # `declaration_from_json` reads "no default key" as "required". A default that crept onto
        # `duration` would make the activity optional-everything and simulate as zero-length instead
        # of being refused in the editor.
        required = {a["name"]: a["requiredParameters"]
                    for a in self.backend.declaration().introspect()["activityTypes"]}
        self.assertEqual(required, {"Observe": ["duration"], "Downlink": ["duration"],
                                    "SetCoolerSetpoint": ["setpointKelvin"]})

    def test_the_defaults_the_host_fills_in_are_the_ones_rust_declared(self):
        # /introspect has no field for a default, so this is the only place the two can be compared.
        # A default the host does not know about is one `effectiveArguments` cannot report.
        effective = self.backend.declaration().effective_args("Observe", {"duration": 60 * US})
        self.assertEqual(effective, {"duration": 60 * US, "targetName": "unnamed",
                                     "framePeriod": 30 * US, "powerWatts": 45.0})

    def test_the_configuration_resolves_to_every_declared_parameter(self):
        # Merlin sends only what the planner overrode, so an unsupplied configuration still has to
        # produce a complete one -- and the Rust side treats a missing key as a broken host.
        resolved = self.backend.declaration().effective_config({})
        self.assertEqual(len(resolved), 9)
        self.assertEqual(resolved["setpointKelvin"], 90.0)
        # int, not 2000.0: the schema says int and adapter_core's own typechecker enforces it.
        self.assertIsInstance(resolved["recorderCapacityFrames"], int)

    def test_the_capability_survives_a_host_that_does_not_parse_capabilities(self):
        # `declaration_from_json` has no branch for `capabilities`, so without the workaround in
        # nx_service.py this comes back empty -- and an ABSENT capability means unsupported, so a
        # pure simulator would be published as one PlanDev's scheduler must not drive.
        self.assertEqual(self.backend.declaration().introspect()["capabilities"],
                         {"plandevScheduling": {"supported": True}})

    def test_every_declared_resource_is_actually_emitted_by_a_run(self):
        # A resource that is declared and never emitted is stored by merlin as one that is
        # permanently absent -- it appears in the timeline picker and charts nothing.
        declared = {r["name"] for r in self.backend.declaration().introspect()["resourceTypes"]}
        response = self.simulate(600 * US)
        self.assertEqual(declared, set(response["realProfiles"]) | set(response["discreteProfiles"]))

    def test_every_computed_attribute_a_span_carries_is_declared(self):
        # Merlin's ingest gate rejects a span carrying an attribute the schema never declared,
        # exactly as it rejects an undeclared argument.
        schemas = {a["name"]: a["computedAttributesSchema"]
                   for a in self.backend.declaration().introspect()["activityTypes"]}
        response = self.simulate(600 * US, [
            directive(1, "Observe", 0, duration=100 * US),
            directive(2, "Downlink", 200 * US, duration=100 * US),
            directive(3, "SetCoolerSetpoint", 400 * US, setpointKelvin=85.0)])
        for span in response["spans"]:
            self.assertEqual(set(span["computedAttributes"]),
                             set(schemas[span["type"]]["items"]), span["type"])
            for name, value in span["computedAttributes"].items():
                self.assertIsNone(
                    adapter_core.nonconformance(value, schemas[span["type"]]["items"][name]),
                    (span["type"], name, value))


# --- a real run, through the host --------------------------------------------------------------------
class TestSimulate(NexosimTestCase):
    def test_a_real_run_gets_past_check_response(self):
        # run_simulate normalizes, runs and then calls check_response, so this exercises the whole
        # path a merlin worker takes. It is the test that would have caught a non-integer duration,
        # a half-finished span or an unsendable value.
        response = self.simulate(4 * 3600 * US + 123, [
            directive(11, "Observe", 1800 * US, duration=3600 * US, targetName="M31",
                      framePeriod=300 * US),
            directive(12, "Downlink", 7200 * US, duration=1200 * US, framePeriod=120 * US)])
        self.assertEqual(len(response["spans"]), 2)
        self.assertTrue(all(s["duration"] is not None for s in response["spans"]))

    def test_an_int_resource_arrives_as_a_python_int_and_not_a_float(self):
        # Merlin's asInt() rejects 2.0 against an int schema. Checked on the PARSED value rather
        # than in Rust, because Python is where the widening would first become visible to anything
        # that behaves like merlin -- and `isinstance(2.0, int)` is False, which is the whole point.
        response = self.simulate(200 * US, [
            directive(1, "Observe", 0, duration=100 * US, framePeriod=10 * US)])
        for segment in response["discreteProfiles"]["/recorder/framesStored"]["segments"]:
            self.assertIsInstance(segment["dynamics"], int)
            self.assertNotIsInstance(segment["dynamics"], bool)
        for segment in response["discreteProfiles"]["/recorder/newestFrame"]["segments"]:
            self.assertIsInstance(segment["dynamics"]["frameId"], int)
        self.assertIsInstance(response["spans"][0]["computedAttributes"]["framesWritten"], int)

    def test_the_struct_resource_matches_its_declared_schema_field_for_field(self):
        # PlanDev structs are CLOSED: merlin's gate rejects a value with a field the schema does not
        # declare AND one missing a field it does. There is no null to fall back on either, which is
        # why the pre-first-frame value is frameId 0 rather than nothing.
        schema = next(r["schema"] for r in self.backend.declaration().introspect()["resourceTypes"]
                      if r["name"] == "/recorder/newestFrame")
        response = self.simulate(200 * US, [
            directive(1, "Observe", 0, duration=100 * US, framePeriod=10 * US, targetName="M31")])
        segments = response["discreteProfiles"]["/recorder/newestFrame"]["segments"]
        for segment in segments:
            self.assertIsNone(adapter_core.nonconformance(segment["dynamics"], schema),
                              segment["dynamics"])
        self.assertEqual(segments[0]["dynamics"]["frameId"], 0)
        self.assertEqual(segments[-1]["dynamics"]["target"], "M31")

    def test_the_host_rejects_a_bad_argument_before_the_model_is_ever_started(self):
        # The reason a model in another process does not need its own typechecker. If this ever
        # reached the binary it would be a 500 out of a subprocess instead of a 400 naming the
        # directive.
        with self.assertRaises(BadRequest) as raised:
            self.simulate(600 * US, [directive(1, "Observe", 0, duration=1.5)])
        self.assertIn("duration", str(raised.exception))

    def test_an_unknown_configuration_key_is_a_400_and_not_a_silent_default(self):
        # A casing typo would otherwise simulate green with the parameter at its default, which
        # looks exactly like the model ignoring it.
        with self.assertRaises(BadRequest):
            self.simulate(600 * US, [], setPointKelvin=80.0)

    def test_a_model_level_refusal_reaches_the_planner_as_a_bad_request(self):
        # Two overlapping observations is the PLANNER's mistake, not the model's failure. The binary
        # exits 2 to say so and the host turns that into a BadRequest carrying the model's own
        # sentence, so the message names what is wrong with the plan instead of blaming a process
        # that worked. This used to be a ModelError -- a 500 sending someone to read the logs of a
        # healthy adapter -- which is one of the gaps building this model found.
        with self.assertRaises(BadRequest) as raised:
            self.simulate(600 * US, [directive(7, "Observe", 0, duration=500 * US),
                                     directive(9, "Observe", 400 * US, duration=100 * US)])
        self.assertNotIsInstance(raised.exception, ModelError)
        self.assertIn("overlapping", str(raised.exception))

    def test_the_same_plan_twice_produces_the_same_answer(self):
        # Two SEPARATE child processes. A model whose answer depends on process-local randomness --
        # a map order, a thread interleaving, an address -- would differ here and nowhere else.
        plan = [directive(1, "Observe", 600 * US, duration=1800 * US, framePeriod=60 * US),
                directive(2, "Downlink", 3000 * US, duration=600 * US)]
        self.assertEqual(json.dumps(self.simulate(4 * 3600 * US, plan), sort_keys=True),
                         json.dumps(nx_service.backend().simulate(
                             self.backend.declaration().normalize(
                                 {"planStart": "2026-07-27T00:00:00Z",
                                  "duration": 4 * 3600 * US,
                                  "configuration": {},
                                  "directives": plan})), sort_keys=True))


# --- validation ----------------------------------------------------------------------------------------
class TestValidate(NexosimTestCase):
    def test_the_generic_layer_still_reports_what_it_always_did(self):
        # The deep checks are layered ON TOP of adapter_core's, not instead of them. A missing
        # required parameter is still a missing required parameter.
        result = self.validate({"type": "Observe", "arguments": {}})[0]
        self.assertFalse(result["valid"])
        self.assertIn("duration", str(result["notices"]))

    def test_a_frame_period_that_could_never_run_is_reported_on_the_field(self):
        # The gap the third verb fills. Without it this passes validation and then fails at
        # simulate, which is the one moment nobody is looking at the form that caused it.
        result = self.validate({"type": "Observe",
                                "arguments": {"duration": 3600 * US, "framePeriod": 1}})[0]
        self.assertFalse(result["valid"])
        # Attributed to the two fields that caused it, so plandev-ui renders it inline rather than
        # as an anonymous banner.
        self.assertEqual(result["notices"][0]["subjects"], ["duration", "framePeriod"])

    def test_a_setpoint_below_absolute_zero_is_reported(self):
        result = self.validate({"type": "SetCoolerSetpoint",
                                "arguments": {"setpointKelvin": -5.0}})[0]
        self.assertFalse(result["valid"])
        self.assertEqual(result["notices"][0]["subjects"], ["setpointKelvin"])

    def test_a_valid_activity_gets_no_notices_at_all(self):
        # A deep check that fires on a good activity paints the editor red for no reason, which is
        # worse than having no deep check.
        result = self.validate({"type": "Observe", "arguments": {"duration": 600 * US}})[0]
        self.assertTrue(result["valid"], result["notices"])
        self.assertEqual(result["notices"], [])

    def test_an_unknown_activity_type_never_reaches_the_binary(self):
        # adapter_core drops unknown types before deep validation, so the model is not asked to
        # validate something it has no declaration for.
        result = self.validate({"type": "Nonexistent", "arguments": {}})[0]
        self.assertFalse(result["valid"])
        self.assertIsNone(result["effectiveArguments"])

    def test_asking_for_effective_arguments_only_skips_the_deep_check_entirely(self):
        # The editor asks for these while a form is still half-filled. Spawning a subprocess per
        # keystroke to say "this is not finished yet" would be both slow and wrong.
        result = self.validate({"type": "Observe", "arguments": {"framePeriod": 1}},
                               effective_only=True)[0]
        self.assertTrue(result["valid"])
        self.assertEqual(result["notices"], [])


# --- routing -------------------------------------------------------------------------------------------
class TestRegistry(NexosimTestCase):
    def test_models_lists_the_one_model_with_its_hash(self):
        listed = self.registry.models_list()["models"]
        self.assertEqual([m["key"] for m in listed], ["cryo"])
        self.assertEqual(listed[0]["identityHash"],
                         self.backend.declaration().identity_hash())

    def test_a_wrong_model_key_is_a_404_and_not_the_only_model_there_is(self):
        # Serving the wrong model would also serve its identityHash, which merlin stores as an
        # attestation that it introspected the model it asked for.
        with self.assertRaises(adapter_core.NotFound):
            self.registry.resolve("orbiter")


if __name__ == "__main__":
    if not binary_present():
        sys.stderr.write("nx-model not found at %s -- build it with `cargo build --release`\n"
                         % BINARY)
    unittest.main()
