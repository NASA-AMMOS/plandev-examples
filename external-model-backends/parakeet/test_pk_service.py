#!/usr/bin/env python3
"""Tests for the Parakeet backend.

    gradle installDist && python3 test_pk_service.py -v

The model is a Kotlin binary, so the tests that exercise it skip cleanly when it has not been
built. The ones that do run drive the REAL binary over the real stdio protocol -- there is no stub,
because the thing most worth testing here is the boundary between a JVM engine's output and
PlanDev's contract, and a stub would be a second opinion about it rather than a check on it.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adapter_core                                                             # noqa: E402
import pk_service                                                              # noqa: E402

US = 1_000_000
PLAN_START = "2026-08-13T00:00:00Z"


def model_built():
    return os.path.exists(pk_service.MODEL_BIN)


@unittest.skipUnless(model_built(), "the Kotlin model is not built (gradle installDist)")
class TestParakeetBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = pk_service.backend()
        cls.declaration = cls.backend.declaration()

    def simulate(self, duration_us, directives, **configuration):
        return adapter_core.run_simulate(self.backend, {
            "planStart": PLAN_START, "duration": duration_us,
            "configuration": configuration, "directives": list(directives)})

    def collect(self, id_, start_us, duration_us, rate=20.0):
        return {"id": id_, "type": "Collect", "startOffset": start_us,
                "arguments": {"duration": duration_us, "rateMbps": rate}}

    def downlink(self, id_, start_us):
        return {"id": id_, "type": "Downlink", "startOffset": start_us, "arguments": {}}

    # -- the declaration ---------------------------------------------------------------------------
    def test_downlink_declares_no_duration_parameter(self):
        """The whole point of this backend. Every other adapter here is handed a duration and hands
        the same number back; this one has an activity whose length nothing in the plan states."""
        downlink = self.declaration.activity_type("Downlink")
        self.assertEqual([p.name for p in downlink.parameters], [])
        self.assertEqual(downlink.required_parameters, [])

    def test_capabilities_survive_the_stdio_declaration(self):
        # ExecBackend dropped these until a real user found it. A pure simulator that says nothing
        # gets published as one PlanDev's scheduler must not drive.
        self.assertTrue(self.declaration.capabilities["plandevScheduling"]["supported"])

    def test_the_identity_hash_is_stable_across_separate_child_processes(self):
        # Two JVMs, two `describe` calls. A declaration built by iterating a HashMap would differ
        # here and nowhere else -- and would re-attest the model on every restart.
        self.assertEqual(self.declaration.identity_hash(),
                         pk_service.backend().declaration().identity_hash())

    # -- the emergent duration ----------------------------------------------------------------------
    def test_a_downlinks_duration_is_computed_by_simulating(self):
        # 300s at 20 Mbps = 6000 Mb, drained at the default 40 Mbps = 150s. Nothing in the plan
        # says 150s, and no reading of the directives alone produces it.
        out = self.simulate(2 * 3600 * US, [self.collect(1, 600 * US, 300 * US),
                                            self.downlink(2, 1800 * US)])
        span = next(s for s in out["spans"] if s["type"] == "Downlink")
        self.assertEqual(span["duration"], 150 * US)
        self.assertAlmostEqual(span["computedAttributes"]["drainSeconds"], 150.0)

    def test_the_same_downlink_takes_longer_when_more_was_collected(self):
        """The claim that makes it emergent rather than merely computed: the SAME directive, at the
        same time, with the same arguments, produces a different span because of what came before
        it."""
        plan = [self.collect(1, 600 * US, 300 * US), self.downlink(9, 1800 * US)]
        short = self.simulate(2 * 3600 * US, plan)
        longer = self.simulate(2 * 3600 * US, [self.collect(2, 900 * US, 300 * US)] + plan)

        def drain(out):
            return next(s["duration"] for s in out["spans"] if s["directiveId"] == 9)
        self.assertGreater(drain(longer), drain(short))

    def test_downlinking_an_empty_recorder_is_a_zero_duration_span(self):
        # Distinct from an unfinished one, which carries no duration at all.
        out = self.simulate(3600 * US, [self.downlink(1, 600 * US)])
        span = out["spans"][0]
        self.assertEqual(span["duration"], 0)
        self.assertIsNotNone(span["computedAttributes"])

    # -- profiles ------------------------------------------------------------------------------------
    def test_every_profile_covers_the_plan_exactly(self):
        duration = 2 * 3600 * US + 7      # deliberately not a round number
        out = self.simulate(duration, [self.collect(1, 600 * US, 300 * US),
                                       self.downlink(2, 1800 * US)])
        for kind in ("realProfiles", "discreteProfiles"):
            for name, profile in out[kind].items():
                self.assertEqual(sum(s["duration"] for s in profile["segments"]), duration, name)

    def test_piecewise_constant_cells_are_discrete_even_when_their_values_are_real(self):
        """A Parakeet discrete cell holds a constant between writes, so its profile is a staircase.

        Reporting it as a real profile made PlanDev interpolate, and the stored level then sloped
        downward for twenty minutes before a downlink had started, at a rate belonging to no part of
        the model. The values are reals; the SHAPE is a staircase; those are separate questions.
        """
        out = self.simulate(2 * 3600 * US, [self.collect(1, 600 * US, 300 * US),
                                            self.downlink(2, 1800 * US)])
        self.assertEqual(out["realProfiles"], {})
        level = out["discreteProfiles"]["/recorder/levelMb"]
        self.assertEqual(level["schema"], {"type": "real"})
        self.assertTrue(all(isinstance(s["dynamics"], float) for s in level["segments"]))

    def test_a_profile_schema_comes_from_the_declaration_when_the_child_omits_it(self):
        # The child sends samples and no schema. merlin requires one, and dies in ValueSchemaJsonParser
        # with a NullPointerException naming neither resource nor model when it is missing.
        out = self.simulate(3600 * US, [])
        for profile in out["discreteProfiles"].values():
            self.assertIsNotNone(profile.get("schema"))

    def test_an_int_resource_stays_an_int(self):
        # Parakeet reports its DYNAMICS -- a discrete cell arrives wrapped as Discrete(1). Serializing
        # that naively yields the string "1", which the gate rejects against an int schema.
        out = self.simulate(2 * 3600 * US, [self.collect(1, 600 * US, 300 * US)])
        values = [s["dynamics"] for s in out["discreteProfiles"]["/recorder/collections"]["segments"]]
        self.assertTrue(all(isinstance(v, int) and not isinstance(v, bool) for v in values), values)

    # -- refusals ------------------------------------------------------------------------------------
    def test_a_model_level_refusal_reaches_the_caller_as_a_bad_request(self):
        # The binary exits 2 to say the REQUEST was wrong. Without that every model-level refusal is
        # a 500 sending someone to read the logs of a process that worked.
        with self.assertRaises(adapter_core.BadRequest) as caught:
            self.simulate(3600 * US, [], capacityMb=-1.0)
        self.assertNotIsInstance(caught.exception, adapter_core.ModelError)
        self.assertIn("capacityMb", str(caught.exception))

    def test_a_wrongly_typed_argument_never_reaches_the_model(self):
        result = adapter_core.run_validate(self.backend, {
            "activities": [{"type": "Collect", "arguments": {"duration": "not-a-duration"}}]})
        self.assertFalse(result["results"][0]["valid"])
        self.assertEqual(result["results"][0]["notices"][0]["subjects"], ["duration"])

    def test_the_same_plan_twice_gives_the_same_answer(self):
        # Two separate JVMs. Determinism is what lets merlin cache a simulation against a revision.
        plan = [self.collect(1, 600 * US, 300 * US), self.downlink(2, 1800 * US)]
        self.assertEqual(json.dumps(self.simulate(2 * 3600 * US, plan), sort_keys=True),
                         json.dumps(self.simulate(2 * 3600 * US, plan), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
