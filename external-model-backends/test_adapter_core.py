#!/usr/bin/env python3
"""Tests for adapter_core.py -- the shared half of the PlanDev external-model contract.

    python3 test_adapter_core.py            # offline; no Docker, no JVM, no outside network
    python3 test_adapter_core.py -v

The HTTP tests bind a real server on 127.0.0.1:0 (an ephemeral loopback port). That is deliberate:
routing, status codes and the JSON error envelope are the contract, and a hand-driven handler stub
would test a paraphrase of the thing merlin actually talks to. Nothing leaves the machine.

What these tests are FOR. This module exists because two adapters implemented the same contract
independently and DRIFTED -- one grew a ValueSchema typechecker and the other never did, so an
audit that found a missing typecheck in `/validate` fixed it in exactly one of them. The properties
pinned hardest here are the ones that were, or could silently become, different in two places:

  * `nonconformance`. Merlin DELEGATES authoritative validation to the backend for external models,
    so if this does not catch a type-wrong argument, nothing does.
  * The identity hash. It is an attestation merlin STORES; a spurious change refuses simulations
    and invalidates the cache, a missed change lets PlanDev's beliefs drift from the model.
  * Defaults and effective arguments -- an explicit null means "absent", an undeclared name is
    dropped rather than echoed onto a span where merlin's ingest gate would flag it.
  * The finished/unfinished span rule. Merlin tells the two apart by the presence of BOTH
    `duration` and `computedAttributes`, so that pairing is load-bearing.
"""
import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adapter_core as ac
from adapter_core import (ActivityType, BadRequest, Declaration, Directive, ExecBackend,
                          ModelError, NotFound, Parameter, Registry, ResourceType,
                          check_response, digest, make_handler, nonconformance)

HERE = os.path.dirname(os.path.abspath(__file__))
TANK = os.path.join(HERE, "exec_example", "tank_model.py")

S = 1_000_000
H = 3600 * S

REAL = {"type": "real"}
INT = {"type": "int"}
DURATION = {"type": "duration"}
BOOLEAN = {"type": "boolean"}
STRING = {"type": "string"}
VARIANT = {"type": "variant", "variants": [{"key": "Idle", "label": "Idle"},
                                           {"key": "Busy", "label": "Busy"}]}
COMPUTED = {"type": "struct", "items": {"moved": REAL}}


def sample_declaration(**kw):
    """A small model with one required parameter, one defaulted one, and a configuration."""
    opts = dict(
        key="widget", name="widget", version="1.0.0",
        activity_types=[
            ActivityType("Spin", [Parameter("duration", DURATION),
                                  Parameter("speed", REAL, 1.5)], COMPUTED),
            ActivityType("Idle", [Parameter("duration", DURATION)], COMPUTED),
        ],
        resource_types=[ResourceType("Rpm", REAL), ResourceType("State", VARIANT)],
        config_parameters=[Parameter("initialRpm", REAL, 0.0), Parameter("cap", INT, 10)])
    opts.update(kw)
    return Declaration(**opts)


class StubBackend(ac.Backend):
    """A backend that records what the generic layer handed it."""

    def __init__(self, declaration=None, result=None, deep=None):
        self._declaration = declaration or sample_declaration()
        self._result = result
        self.seen = None
        self.deep_calls = []
        self._deep = deep

    def declaration(self):
        return self._declaration

    def simulate(self, request):
        self.seen = request
        if self._result is not None:
            return self._result
        return {"realProfiles": {}, "discreteProfiles": {}, "spans": []}

    def deep_validate(self, subjects):
        self.deep_calls.append(list(subjects))
        return self._deep(subjects) if self._deep else None


# --- ValueSchema conformance ------------------------------------------------------------------------
class TestNonconformance(unittest.TestCase):
    def assertConforms(self, value, schema):
        self.assertIsNone(nonconformance(value, schema), "%r should satisfy %r" % (value, schema))

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

    def test_a_bool_does_not_satisfy_int_or_real(self):
        """bool is an int subclass in Python; PlanDev's int schema does not accept one, and a
        `True` silently stored as 1 is a type error that only surfaces much later."""
        for schema in (INT, REAL, DURATION):
            self.assertRejects(True, schema)
            self.assertRejects(False, schema)

    def test_duration_is_whole_integer_microseconds(self):
        self.assertConforms(0, DURATION)
        self.assertConforms(-1_000, DURATION)
        self.assertConforms(3_600_000_000, DURATION)
        self.assertRejects(1.5, DURATION)
        self.assertRejects(1.0, DURATION)              # float, even though integral
        self.assertRejects("01:00:00", DURATION)       # a model's own notation is not the contract's

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
        self.assertRejects("Spinning", VARIANT)        # not among this schema's variants
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
        """ValueSchema structs are CLOSED: merlin's gate rejects a span carrying a field the schema
        never declared, so accepting one here would just move the failure downstream."""
        self.assertIn("unexpected field 'z'", nonconformance({"a": 1, "z": 2}, {"type": "struct",
                                                                                "items": {"a": INT}}))

    def test_a_map_shaped_series_of_key_value_structs(self):
        """merlin's MapValueMapper convention, which is how every Map parameter crosses the wire."""
        schema = {"type": "series", "items": {"type": "struct",
                                              "items": {"key": STRING, "value": STRING}}}
        self.assertConforms([{"key": "k", "value": "v"}], schema)
        self.assertRejects([{"k": "v"}], schema)
        self.assertRejects({"k": "v"}, schema)

    def test_null_is_accepted_against_any_schema(self):
        """A schema says nothing about nullability; absence is handled by default resolution."""
        for schema in (REAL, INT, DURATION, BOOLEAN, STRING, VARIANT,
                       {"type": "series", "items": INT}, {"type": "struct", "items": {"a": INT}}):
            self.assertConforms(None, schema)

    def test_an_unknown_schema_type_is_not_rejected(self):
        """Forward compatibility: a ValueSchema this adapter has never heard of must not turn every
        value of that type into a validation error."""
        self.assertConforms("anything", {"type": "quaternion"})


# --- declaration / introspection -----------------------------------------------------------------
class TestIntrospect(unittest.TestCase):
    def setUp(self):
        self.decl = sample_declaration()
        self.intro = self.decl.introspect()

    def test_activity_types_keep_declaration_order(self):
        self.assertEqual([a["name"] for a in self.intro["activityTypes"]], ["Spin", "Idle"])
        self.assertEqual([p["name"] for p in self.intro["activityTypes"][0]["parameters"]],
                         ["duration", "speed"])

    def test_required_parameters_are_exactly_those_without_a_default(self):
        self.assertEqual(self.intro["activityTypes"][0]["requiredParameters"], ["duration"])

    def test_required_can_be_declared_independently_of_the_default(self):
        act = ActivityType("X", [Parameter("p", INT, 3, required=True),
                                 Parameter("q", INT, required=False)])
        self.assertEqual(act.required_parameters, ["p"])

    def test_computed_attributes_schema_is_reported_per_activity_type(self):
        for a in self.intro["activityTypes"]:
            self.assertEqual(a["computedAttributesSchema"], COMPUTED)

    def test_resources_and_configuration_are_reported_without_defaults(self):
        self.assertEqual([r["name"] for r in self.intro["resourceTypes"]], ["Rpm", "State"])
        self.assertEqual(self.intro["parameters"],
                         [{"name": "initialRpm", "schema": REAL}, {"name": "cap", "schema": INT}])

    def test_introspect_carries_the_identity_hash(self):
        self.assertEqual(self.intro["identityHash"], self.decl.identity_hash())


# --- identity hash --------------------------------------------------------------------------------
class TestIdentityHash(unittest.TestCase):
    """The attestation merlin stores. A spurious change refuses simulations and invalidates the
    cache; a missed change lets PlanDev's stored beliefs drift from the model silently."""

    def setUp(self):
        self.baseline = sample_declaration().identity_hash()

    def test_the_hash_is_sixteen_hex_characters_and_stable_across_calls(self):
        self.assertEqual(len(self.baseline), 16)
        self.assertEqual(sample_declaration().identity_hash(), self.baseline)

    def test_the_hash_is_stable_across_PROCESSES(self):
        """"Stable across restarts" is the actual requirement, and the way to break it is to let a
        salted dict iteration order or an object id into the payload. Interpreters started with
        different hash seeds must agree."""
        script = ("import sys; sys.path.insert(0, %r); import test_adapter_core as t; "
                  "print(t.sample_declaration().identity_hash())" % (HERE,))
        seen = set()
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                                 env=env, cwd=HERE)
            self.assertEqual(out.returncode, 0, out.stderr)
            seen.add(out.stdout.strip())
        self.assertEqual(seen, {self.baseline})

    def test_reordering_parameters_moves_the_hash(self):
        """Parameter order IS something PlanDev stores: merlin assigns each parameter an `order`
        from its index in the introspection array, persists it, reads activity types back sorted by
        it, and plandev-ui lays the argument form out in that order."""
        moved = sample_declaration(activity_types=[
            ActivityType("Spin", [Parameter("speed", REAL, 1.5),
                                  Parameter("duration", DURATION)], COMPUTED),
            ActivityType("Idle", [Parameter("duration", DURATION)], COMPUTED)])
        self.assertNotEqual(moved.identity_hash(), self.baseline)

    def test_reordering_activity_types_does_not_move_the_hash(self):
        """PlanDev stores activity types by NAME, not by position, so their order is genuinely
        cosmetic -- unlike a parameter's."""
        acts = sample_declaration().activity_types
        self.assertEqual(sample_declaration(activity_types=list(reversed(acts))).identity_hash(),
                         self.baseline)

    def test_changing_a_default_changes_the_hash(self):
        changed = sample_declaration(activity_types=[
            ActivityType("Spin", [Parameter("duration", DURATION),
                                  Parameter("speed", REAL, 2.0)], COMPUTED),
            ActivityType("Idle", [Parameter("duration", DURATION)], COMPUTED)])
        self.assertNotEqual(changed.identity_hash(), self.baseline)

    def test_flipping_required_changes_the_hash_even_with_the_same_schemas(self):
        """requiredParameters is persisted in activity_type and merlin's gate enforces it, so this
        changes what PlanDev believes without changing a single schema."""
        changed = sample_declaration(activity_types=[
            ActivityType("Spin", [Parameter("duration", DURATION),
                                  Parameter("speed", REAL, 1.5, required=True)], COMPUTED),
            ActivityType("Idle", [Parameter("duration", DURATION)], COMPUTED)])
        self.assertNotEqual(changed.identity_hash(), self.baseline)

    def test_changing_a_parameter_schema_changes_the_hash(self):
        changed = sample_declaration(activity_types=[
            ActivityType("Spin", [Parameter("duration", DURATION),
                                  Parameter("speed", INT, 1)], COMPUTED),
            ActivityType("Idle", [Parameter("duration", DURATION)], COMPUTED)])
        self.assertNotEqual(changed.identity_hash(), self.baseline)

    def test_adding_or_removing_an_activity_type_changes_the_hash(self):
        acts = sample_declaration().activity_types
        more = sample_declaration(activity_types=acts + [ActivityType("Halt", [], COMPUTED)])
        self.assertNotEqual(more.identity_hash(), self.baseline)
        self.assertNotEqual(sample_declaration(activity_types=acts[:1]).identity_hash(),
                            self.baseline)

    def test_changing_a_resource_schema_changes_the_hash(self):
        changed = sample_declaration(resource_types=[ResourceType("Rpm", INT),
                                                     ResourceType("State", VARIANT)])
        self.assertNotEqual(changed.identity_hash(), self.baseline)

    def test_changing_a_configuration_parameter_or_default_changes_the_hash(self):
        for cfg in ([Parameter("initialRpm", REAL, 99.0), Parameter("cap", INT, 10)],
                    [Parameter("initialRpm", REAL, 0.0), Parameter("cap", INT, 10),
                     Parameter("extra", INT, 1)],
                    [Parameter("initialRpm", REAL, 0.0)]):
            with self.subTest(cfg=[p.name for p in cfg]):
                self.assertNotEqual(sample_declaration(config_parameters=cfg).identity_hash(),
                                    self.baseline)

    def test_changing_a_computed_attributes_schema_changes_the_hash(self):
        """Stored in activity_type too -- if it drifts, the gate starts rejecting spans against a
        stale schema."""
        changed = sample_declaration(activity_types=[
            ActivityType("Spin", [Parameter("duration", DURATION),
                                  Parameter("speed", REAL, 1.5)],
                         {"type": "struct", "items": {"moved": INT}}),
            ActivityType("Idle", [Parameter("duration", DURATION)], COMPUTED)])
        self.assertNotEqual(changed.identity_hash(), self.baseline)

    def test_renaming_the_model_does_not_move_the_hash(self):
        """The hash attests to the model's SHAPE. A key or version is metadata PlanDev carries
        alongside it, not something the declaration drift check is about."""
        self.assertEqual(sample_declaration(key="other", name="other", version="9.9").identity_hash(),
                         self.baseline)

    def test_a_published_model_can_pin_its_payload(self):
        """A model that has already shipped keeps the bytes its stored attestation was minted
        from, rather than re-hashing under a newer canonical layout."""
        pinned = sample_declaration(digest_payload=lambda d: {"frozen": d.key})
        self.assertEqual(pinned.identity_hash(), digest({"frozen": "widget"}))
        self.assertNotEqual(pinned.identity_hash(), self.baseline)

    def test_digest_is_insensitive_to_mapping_insertion_order(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))

    def test_digest_survives_a_value_json_cannot_serialize(self):
        """`default=str` keeps a stray non-JSON value (a Blackbird type object, say) from turning
        an attestation into a crash."""
        self.assertEqual(len(digest({"x": object()})), 16)


# --- effective arguments ----------------------------------------------------------------------------
class TestEffectiveArgs(unittest.TestCase):
    def setUp(self):
        self.decl = sample_declaration()

    def test_defaults_fill_in_for_absent_optional_parameters(self):
        self.assertEqual(self.decl.effective_args("Spin", {"duration": 5}),
                         {"duration": 5, "speed": 1.5})

    def test_a_supplied_value_wins_over_the_default(self):
        self.assertEqual(self.decl.effective_args("Spin", {"duration": 5, "speed": 9.0}),
                         {"duration": 5, "speed": 9.0})

    def test_an_explicit_null_counts_as_absent_so_the_default_applies(self):
        """Otherwise a null sails past default resolution and reaches the model's arithmetic."""
        self.assertEqual(self.decl.effective_args("Spin", {"duration": 5, "speed": None}),
                         {"duration": 5, "speed": 1.5})

    def test_an_explicit_null_on_a_required_parameter_leaves_it_absent(self):
        self.assertEqual(self.decl.effective_args("Spin", {"duration": None}), {"speed": 1.5})

    def test_undeclared_arguments_are_dropped_not_echoed(self):
        """They would otherwise ride through onto the span, where merlin's ingest gate flags every
        span carrying an argument the model never declared."""
        self.assertEqual(self.decl.effective_args("Spin", {"duration": 5, "bogus": 1}),
                         {"duration": 5, "speed": 1.5})

    def test_effective_arguments_come_out_in_declaration_order(self):
        self.assertEqual(list(self.decl.effective_args("Spin", {"speed": 2.0, "duration": 5})),
                         ["duration", "speed"])

    def test_an_unknown_activity_type_yields_nothing(self):
        self.assertEqual(self.decl.effective_args("Nope", {"duration": 5}), {})

    def test_none_and_empty_arguments_are_both_accepted(self):
        self.assertEqual(self.decl.effective_args("Spin", None), {"speed": 1.5})
        self.assertEqual(self.decl.effective_args("Spin", {}), {"speed": 1.5})

    def test_undeclared_lists_exactly_the_unknown_names(self):
        self.assertEqual(self.decl.undeclared("Spin", {"duration": 1, "x": 3, "y": 4}), ["x", "y"])
        self.assertEqual(self.decl.undeclared("Spin", {}), [])
        self.assertEqual(self.decl.undeclared("Spin", None), [])
        self.assertEqual(self.decl.undeclared("Nope", {"a": 1}), ["a"])


class TestEffectiveConfig(unittest.TestCase):
    def setUp(self):
        self.decl = sample_declaration()

    def test_defaults_fill_in(self):
        self.assertEqual(self.decl.effective_config(None), {"initialRpm": 0.0, "cap": 10})
        self.assertEqual(self.decl.effective_config({}), {"initialRpm": 0.0, "cap": 10})

    def test_supplied_values_win_and_a_null_means_use_the_default(self):
        self.assertEqual(self.decl.effective_config({"initialRpm": 7.5}),
                         {"initialRpm": 7.5, "cap": 10})
        self.assertEqual(self.decl.effective_config({"initialRpm": None})["initialRpm"], 0.0)

    def test_only_declared_keys_come_out(self):
        self.assertEqual(set(self.decl.effective_config({})), {"initialRpm", "cap"})

    def test_an_unknown_key_is_refused_rather_than_silently_honoured(self):
        """A casing typo would otherwise simulate green with the parameter at its default, which
        looks exactly like the model ignoring it."""
        with self.assertRaises(BadRequest) as ctx:
            self.decl.effective_config({"initialRPM": 1.0})
        self.assertIn("unknown configuration parameter 'initialRPM'", str(ctx.exception))

    def test_values_are_typechecked(self):
        for key, bad in (("cap", 1.5), ("cap", True), ("initialRpm", "50"), ("initialRpm", [])):
            with self.subTest(key=key, value=bad):
                with self.assertRaises(BadRequest):
                    self.decl.effective_config({key: bad})

    def test_a_parameter_with_no_adapter_side_default_comes_out_as_none(self):
        """How a backend says "I was not told, so leave whatever the model itself defaults to"."""
        decl = sample_declaration(config_parameters=[Parameter("epoch", STRING)])
        self.assertEqual(decl.effective_config({}), {"epoch": None})


# --- generic validation ----------------------------------------------------------------------------
class TestValidateOne(unittest.TestCase):
    def setUp(self):
        self.decl = sample_declaration()

    @staticmethod
    def messages(result):
        return [n["message"] for n in result["notices"]]

    @staticmethod
    def subjects(result):
        return [n["subjects"] for n in result["notices"]]

    def test_a_well_formed_activity_validates_green(self):
        r = self.decl.validate_one("Spin", {"duration": 1 * H, "speed": 2.0})
        self.assertTrue(r["valid"])
        self.assertEqual(r["notices"], [])
        self.assertEqual(r["effectiveArguments"], {"duration": 1 * H, "speed": 2.0})

    def test_an_unknown_activity_type_is_reported_without_effective_arguments(self):
        r = self.decl.validate_one("Nope", {})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["effectiveArguments"])
        self.assertEqual(self.subjects(r), [[]])       # not attributable to a parameter

    def test_a_missing_required_parameter_is_attributed_to_that_parameter(self):
        r = self.decl.validate_one("Spin", {})
        self.assertEqual(self.messages(r), ["missing required parameter 'duration'"])
        self.assertEqual(self.subjects(r), [["duration"]])

    def test_an_explicit_null_counts_as_missing(self):
        self.assertIn("missing required parameter 'duration'",
                      self.messages(self.decl.validate_one("Spin", {"duration": None})))

    def test_an_unrecognized_parameter_is_reported(self):
        r = self.decl.validate_one("Spin", {"duration": 1 * H, "bogus": 1})
        self.assertIn("unrecognized parameter 'bogus'", self.messages(r))
        self.assertEqual(self.subjects(r), [["bogus"]])

    def test_a_type_wrong_argument_is_reported(self):
        """merlin delegates authoritative validation here, so this is the only typecheck there is."""
        r = self.decl.validate_one("Spin", {"duration": "01:00:00"})
        self.assertFalse(r["valid"])
        self.assertTrue(any("expected a duration as integer microseconds" in m
                            for m in self.messages(r)), self.messages(r))
        self.assertEqual(self.subjects(r), [["duration"]])

    def test_several_problems_are_all_reported_at_once(self):
        r = self.decl.validate_one("Spin", {"speed": "fast", "bogus": 1})
        self.assertEqual(sorted(self.messages(r)),
                         sorted(["missing required parameter 'duration'",
                                 "unrecognized parameter 'bogus'",
                                 "parameter 'speed' expected a finite real, got 'fast'"]))

    def test_effective_only_short_circuits_every_check(self):
        """The editor asks for effective arguments while a form is still half-filled; that is not
        the moment to paint it red."""
        r = self.decl.validate_one("Spin", {}, effective_only=True)
        self.assertTrue(r["valid"])
        self.assertEqual(r["notices"], [])
        self.assertEqual(r["effectiveArguments"], {"speed": 1.5})

    def test_effective_only_still_refuses_an_unknown_type(self):
        self.assertFalse(self.decl.validate_one("Nope", {}, effective_only=True)["valid"])

    def test_effective_arguments_are_returned_even_when_invalid(self):
        r = self.decl.validate_one("Spin", {"bogus": 1})
        self.assertFalse(r["valid"])
        self.assertEqual(r["effectiveArguments"], {"speed": 1.5})


class TestDeepValidateHook(unittest.TestCase):
    """The optional hook, and the layering rule: it runs ON TOP of the generic typecheck."""

    def test_extra_notices_are_appended_and_flip_valid(self):
        backend = StubBackend(deep=lambda subs: [[{"subjects": ["speed"], "message": "too fast"}]
                                                 for _ in subs])
        out = ac.run_validate(backend, {"activities": [{"type": "Spin",
                                                        "arguments": {"duration": 1, "speed": 99.0}}]})
        result = out["results"][0]
        self.assertFalse(result["valid"])
        self.assertEqual([n["message"] for n in result["notices"]], ["too fast"])

    def test_generic_notices_come_first(self):
        backend = StubBackend(deep=lambda subs: [[{"subjects": [], "message": "deep"}] for _ in subs])
        result = ac.run_validate(
            backend, {"activities": [{"type": "Spin", "arguments": {"bogus": 1}}]})["results"][0]
        self.assertEqual([n["message"] for n in result["notices"]],
                         ["missing required parameter 'duration'",
                          "unrecognized parameter 'bogus'", "deep"])

    def test_the_hook_sees_what_the_generic_layer_already_found(self):
        """So a backend whose deep check is expensive -- or whose model would crash on input this
        layer already rejected -- can skip it."""
        backend = StubBackend(deep=lambda subs: [[] for _ in subs])
        ac.run_validate(backend, {"activities": [{"type": "Spin", "arguments": {}},
                                                 {"type": "Spin", "arguments": {"duration": 1}}]})
        subjects = backend.deep_calls[0]
        self.assertEqual([bool(s.notices) for s in subjects], [True, False])
        self.assertEqual([s.effective_arguments for s in subjects],
                         [{"speed": 1.5}, {"duration": 1, "speed": 1.5}])

    def test_the_hook_receives_raw_and_effective_arguments(self):
        backend = StubBackend(deep=lambda subs: None)
        ac.run_validate(backend, {"activities": [{"type": "Spin", "arguments": {"duration": 1}}]})
        subject = backend.deep_calls[0][0]
        self.assertEqual(subject.arguments, {"duration": 1})
        self.assertEqual(subject.effective_arguments, {"duration": 1, "speed": 1.5})
        self.assertEqual(subject.index, 0)

    def test_an_unknown_activity_type_never_reaches_the_hook(self):
        """There is nothing a deep check could add for a type with no declaration, and plenty it
        could crash on. The indices still line up with the results."""
        backend = StubBackend(deep=lambda subs: [[{"subjects": [], "message": "deep"}] for _ in subs])
        out = ac.run_validate(backend, {"activities": [{"type": "Nope", "arguments": {}},
                                                       {"type": "Spin", "arguments": {"duration": 1}}]})
        self.assertEqual([s.index for s in backend.deep_calls[0]], [1])
        self.assertNotIn("deep", [n["message"] for n in out["results"][0]["notices"]])
        self.assertEqual([n["message"] for n in out["results"][1]["notices"]], ["deep"])

    def test_effective_only_skips_the_hook_entirely(self):
        backend = StubBackend(deep=lambda subs: [[{"subjects": [], "message": "deep"}] for _ in subs])
        ac.run_validate(backend, {"effectiveOnly": True,
                                  "activities": [{"type": "Spin", "arguments": {}}]})
        self.assertEqual(backend.deep_calls, [])

    def test_a_backend_with_no_hook_is_fine(self):
        out = ac.run_validate(StubBackend(), {"activities": [{"type": "Spin", "arguments": {"duration": 1}}]})
        self.assertTrue(out["results"][0]["valid"])


# --- request normalization --------------------------------------------------------------------------
class TestNormalize(unittest.TestCase):
    def setUp(self):
        self.decl = sample_declaration()

    def request(self, directives=(), duration=4 * H, configuration=None, **kw):
        req = {"duration": duration, "configuration": configuration or {},
               "directives": list(directives)}
        req.update(kw)
        return self.decl.normalize(req)

    def directive(self, did=1, typ="Spin", start=0, **arguments):
        return {"id": did, "type": typ, "startOffset": start, "arguments": arguments}

    def assertBadRequest(self, fragment, **kw):
        with self.assertRaises(BadRequest) as ctx:
            self.request(**kw)
        self.assertIn(fragment, str(ctx.exception))

    def test_arguments_arrive_defaulted_filtered_and_typechecked(self):
        req = self.request([self.directive(duration=5, bogus="x")])
        self.assertEqual(req.directives[0].arguments, {"duration": 5, "speed": 1.5})
        self.assertEqual(req.directives[0].id, 1)
        self.assertEqual(req.directives[0].type, "Spin")
        self.assertEqual(req.directives[0].start_offset, 0)

    def test_the_configuration_arrives_resolved(self):
        self.assertEqual(self.request().configuration, {"initialRpm": 0.0, "cap": 10})

    def test_a_negative_simulation_duration_is_refused(self):
        self.assertBadRequest("simulation duration must be >= 0", duration=-1)

    def test_a_missing_or_unparseable_duration_is_a_400_not_a_500(self):
        with self.assertRaises(BadRequest):
            self.decl.normalize({})
        with self.assertRaises(BadRequest):
            self.decl.normalize({"duration": "an hour"})

    def test_an_unknown_activity_type_names_the_directive(self):
        self.assertBadRequest("directive 3 has unknown activity type 'Levitate'",
                              directives=[self.directive(3, "Levitate")])

    def test_a_missing_required_parameter_names_the_directive(self):
        self.assertBadRequest("directive 1 (Spin) is missing required parameter 'duration'",
                              directives=[self.directive(speed=1.0)])

    def test_a_type_wrong_argument_names_the_directive_and_the_parameter(self):
        self.assertBadRequest("directive 1 (Spin) parameter 'duration' expected a duration",
                              directives=[self.directive(duration="01:00:00")])
        self.assertBadRequest("expected a finite real",
                              directives=[self.directive(duration=1, speed=float("inf"))])

    def test_a_missing_start_offset_is_refused(self):
        with self.assertRaises(BadRequest) as ctx:
            self.decl.normalize({"duration": 1, "directives": [{"id": 1, "type": "Spin",
                                                                "arguments": {"duration": 1}}]})
        self.assertIn("has no startOffset", str(ctx.exception))

    def test_a_bad_directive_fails_the_whole_request_rather_than_being_skipped(self):
        """A silently dropped directive is a plan that simulates green and is simply missing work."""
        self.assertBadRequest("Levitate", directives=[self.directive(1, duration=1),
                                                      self.directive(2, "Levitate")])

    def test_plan_start_is_parsed_when_present(self):
        req = self.request(planStart="2024-01-01T00:00:00Z")
        self.assertEqual(req.plan_start.year, 2024)
        self.assertEqual(req.plan_start_iso, "2024-01-01T00:00:00Z")

    def test_plan_start_is_optional_but_asking_for_a_missing_one_is_a_400(self):
        """A model whose spans are all relative offsets never needs it; one that does gets a
        message naming the missing field rather than a NoneType TypeError five frames deep."""
        req = self.request()
        self.assertIsNone(req.plan_start_iso)
        with self.assertRaises(BadRequest) as ctx:
            req.plan_start
        self.assertIn("planStart", str(ctx.exception))

    def test_an_unparseable_plan_start_is_a_400(self):
        self.assertBadRequest("not an ISO-8601 instant", planStart="tuesday")


# --- response validation -----------------------------------------------------------------------------
class TestCheckResponse(unittest.TestCase):
    def span(self, **kw):
        base = {"spanId": 1, "type": "Spin", "startOffset": 0, "arguments": {},
                "parentId": None, "directiveId": 1}
        base.update(kw)
        return {"realProfiles": {}, "discreteProfiles": {}, "spans": [base]}

    def test_a_finished_span_carries_both_duration_and_computed_attributes(self):
        check_response(self.span(duration=5, computedAttributes={"moved": 1.0}))

    def test_an_unfinished_span_carries_neither(self):
        check_response(self.span())

    def test_computed_attributes_without_a_duration_are_refused(self):
        """merlin reads that as finished-with-no-end."""
        with self.assertRaises(ModelError) as ctx:
            check_response(self.span(computedAttributes={"moved": 1.0}))
        self.assertIn("computedAttributes", str(ctx.exception))

    def test_a_duration_without_computed_attributes_is_refused(self):
        with self.assertRaises(ModelError):
            check_response(self.span(duration=5))

    def test_a_non_integer_span_duration_or_offset_is_refused(self):
        with self.assertRaises(ModelError):
            check_response(self.span(duration=5.0, computedAttributes={}))
        with self.assertRaises(ModelError):
            check_response(self.span(startOffset=1.5))

    def test_a_non_finite_value_in_a_profile_is_refused_and_says_where(self):
        """json.dumps would emit a bare Infinity, which is not legal JSON at all: merlin's parser
        rejects the WHOLE response, so the ingest dies before anything useful is reported."""
        for bad in (float("inf"), float("nan"), float("-inf")):
            with self.subTest(value=bad):
                with self.assertRaises(ModelError) as ctx:
                    check_response({"realProfiles": {"Rpm": {"schema": REAL, "segments": [
                        {"duration": 1, "dynamics": {"initial": 0.0, "rate": bad}}]}},
                        "discreteProfiles": {}, "spans": []})
                self.assertIn("Rpm", str(ctx.exception))
                self.assertIn("rate", str(ctx.exception))

    def test_a_non_finite_value_in_a_discrete_profile_is_refused(self):
        with self.assertRaises(ModelError):
            check_response({"realProfiles": {}, "spans": [], "discreteProfiles": {
                "X": {"schema": REAL, "segments": [{"duration": 1, "dynamics": float("nan")}]}}})

    def test_a_non_finite_value_nested_in_a_span_is_refused(self):
        with self.assertRaises(ModelError) as ctx:
            check_response(self.span(duration=1,
                                     computedAttributes={"moved": [1.0, float("inf")]}))
        self.assertIn("computedAttributes", str(ctx.exception))

    def test_a_non_integer_segment_duration_is_refused(self):
        with self.assertRaises(ModelError):
            check_response({"realProfiles": {}, "spans": [], "discreteProfiles": {
                "X": {"schema": INT, "segments": [{"duration": 1.5, "dynamics": 0}]}}})

    def test_an_empty_response_is_fine(self):
        check_response({"realProfiles": {}, "discreteProfiles": {}, "spans": []})
        check_response({})


# --- registry ----------------------------------------------------------------------------------------
class TestRegistry(unittest.TestCase):
    def test_a_single_model_may_be_addressed_without_a_key(self):
        backend = StubBackend()
        self.assertIs(Registry({"widget": backend}).resolve(None), backend)

    def test_an_unknown_key_is_a_not_found_even_when_only_one_model_exists(self):
        """Serving some other model would make the identityHash merlin stores a lie: it attests
        that merlin introspected the model it is about to simulate."""
        with self.assertRaises(NotFound) as ctx:
            Registry({"widget": StubBackend()}).resolve("other")
        self.assertIn("unknown model 'other'; available: ['widget']", str(ctx.exception))

    def test_no_key_with_several_models_is_a_bad_request(self):
        reg = Registry({"a": StubBackend(), "b": StubBackend()})
        with self.assertRaises(BadRequest) as ctx:
            reg.resolve(None)
        self.assertNotIsInstance(ctx.exception, NotFound)
        self.assertIn("no model specified", str(ctx.exception))

    def test_models_list_reports_each_key_with_its_hash(self):
        reg = Registry({"a": StubBackend(), "b": StubBackend(sample_declaration(key="b"))})
        models = reg.models_list()["models"]
        self.assertEqual([m["key"] for m in models], ["a", "b"])
        self.assertEqual(set(models[0]), {"key", "name", "version", "identityHash"})


# --- HTTP -----------------------------------------------------------------------------------------
class HttpTestCase(unittest.TestCase):
    """A real loopback server, because routing and status codes ARE the contract."""

    backends = None

    @classmethod
    def setUpClass(cls):
        cls.registry = Registry(cls.make_backends())
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.registry))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    @classmethod
    def make_backends(cls):
        return {"widget": StubBackend()}

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read().decode())


class TestHttpRouting(HttpTestCase):
    @classmethod
    def make_backends(cls):
        cls.widget = StubBackend()
        cls.gadget = StubBackend(sample_declaration(key="gadget", name="gadget"))
        return {"widget": cls.widget, "gadget": cls.gadget}

    def test_models_is_never_model_scoped(self):
        code, out = self.call("GET", "/models")
        self.assertEqual(code, 200)
        self.assertEqual([m["key"] for m in out["models"]], ["widget", "gadget"])

    def test_introspect_by_key(self):
        code, out = self.call("GET", "/introspect?model=gadget")
        self.assertEqual(code, 200)
        self.assertEqual(out["identityHash"], self.gadget.declaration().identity_hash())

    def test_introspect_over_post_too(self):
        self.assertEqual(self.call("POST", "/introspect?model=widget", {})[0], 200)
        # ...and with the key in the body, for a caller that prefers it there.
        self.assertEqual(self.call("POST", "/introspect", {"model": "widget"})[0], 200)

    def test_an_unknown_model_key_is_404(self):
        code, out = self.call("GET", "/introspect?model=nope")
        self.assertEqual(code, 404)
        self.assertIn("unknown model 'nope'", out["error"])

    def test_no_model_key_with_two_models_is_400(self):
        code, out = self.call("GET", "/introspect")
        self.assertEqual(code, 400)
        self.assertIn("no model specified", out["error"])

    def test_an_unknown_path_is_404_before_the_model_is_even_resolved(self):
        self.assertEqual(self.call("GET", "/bogus?model=nope"), (404, {"error": "not found"}))
        code, out = self.call("POST", "/bogus", {})
        self.assertEqual((code, out), (404, {"error": "not found: /bogus"}))

    def test_a_path_prefix_still_routes(self):
        """So an adapter can live behind a reverse proxy without the routing knowing."""
        self.assertEqual(self.call("GET", "/backends/v1/models")[0], 200)

    def test_a_trailing_slash_is_ignored(self):
        self.assertEqual(self.call("GET", "/models/")[0], 200)

    def test_simulate_reaches_the_backend_with_a_normalized_request(self):
        code, out = self.call("POST", "/simulate?model=widget", {
            "planStart": "2024-01-01T00:00:00Z", "duration": 4 * H, "configuration": {},
            "directives": [{"id": 1, "type": "Spin", "startOffset": 0,
                            "arguments": {"duration": 1 * H, "junk": 2}}]})
        self.assertEqual(code, 200)
        self.assertEqual(out, {"realProfiles": {}, "discreteProfiles": {}, "spans": []})
        self.assertEqual(self.widget.seen.directives[0].arguments, {"duration": 1 * H, "speed": 1.5})
        self.assertEqual(self.widget.seen.configuration, {"initialRpm": 0.0, "cap": 10})

    def test_a_caller_error_is_400_with_a_json_envelope(self):
        code, out = self.call("POST", "/simulate?model=widget",
                              {"duration": 4 * H, "directives": [{"id": 9, "type": "Levitate",
                                                                  "startOffset": 0}]})
        self.assertEqual(code, 400)
        self.assertIn("directive 9 has unknown activity type 'Levitate'", out["error"])

    def test_validate_answers_one_result_per_activity(self):
        code, out = self.call("POST", "/validate?model=widget", {"activities": [
            {"type": "Spin", "arguments": {"duration": 1}},
            {"type": "Spin", "arguments": {"duration": "nope"}}]})
        self.assertEqual(code, 200)
        self.assertEqual([r["valid"] for r in out["results"]], [True, False])

    def test_a_malformed_json_body_is_400_not_500(self):
        req = urllib.request.Request(self.base + "/simulate?model=widget", data=b"{oops",
                                     method="POST", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=30)
        with ctx.exception as e:
            self.assertEqual(e.code, 400)
            self.assertIn("malformed JSON body", json.loads(e.read().decode())["error"])

    def test_a_non_object_body_is_400(self):
        code, out = self.call("POST", "/simulate?model=widget", [1, 2, 3])
        self.assertEqual(code, 400)
        self.assertIn("must be a JSON object", out["error"])


class TestHttpErrorSurfaces(HttpTestCase):
    @classmethod
    def make_backends(cls):
        class Exploding(StubBackend):
            def simulate(self, request):
                raise RuntimeError("the model fell over")

        class NonFinite(StubBackend):
            def simulate(self, request):
                # Sneaks past check_response, which does not walk a profile's `schema`.
                return {"realProfiles": {"Rpm": {"schema": {"type": "real", "x": float("inf")},
                                                 "segments": []}},
                        "discreteProfiles": {}, "spans": []}

        class HalfFinished(StubBackend):
            def simulate(self, request):
                return {"realProfiles": {}, "discreteProfiles": {},
                        "spans": [{"spanId": 1, "type": "Spin", "startOffset": 0, "arguments": {},
                                   "computedAttributes": {"moved": 1.0}}]}

        return {"boom": Exploding(), "nonfinite": NonFinite(), "half": HalfFinished()}

    def simulate(self, key):
        return self.call("POST", "/simulate?model=%s" % key,
                         {"duration": 1, "configuration": {}, "directives": []})

    def test_an_unexpected_model_failure_is_500_carrying_its_message(self):
        code, out = self.simulate("boom")
        self.assertEqual(code, 500)
        self.assertEqual(out["error"], "the model fell over")

    def test_a_half_finished_span_is_a_500_that_says_so(self):
        code, out = self.simulate("half")
        self.assertEqual(code, 500)
        self.assertIn("finished span carries both", out["error"])

    def test_a_stray_non_finite_still_cannot_reach_the_wire_as_bare_nan(self):
        """The serializer backstop: whatever check_response does not walk, allow_nan=False will."""
        code, out = self.simulate("nonfinite")
        self.assertEqual(code, 500)
        self.assertIn("non-finite", out["error"])


# --- ExecBackend --------------------------------------------------------------------------------------
class TestExecBackend(unittest.TestCase):
    def backend(self, **kw):
        return ExecBackend("tank", [sys.executable, TANK], **kw)

    def test_describe_produces_a_usable_declaration(self):
        decl = self.backend().declaration()
        self.assertEqual(decl.key, "tank")
        self.assertEqual([a.name for a in decl.activity_types], ["Fill"])
        self.assertEqual([p.name for p in decl.activity_types[0].parameters], ["duration", "rate"])
        self.assertEqual(decl.activity_types[0].required_parameters, ["duration"])
        self.assertEqual([r.name for r in decl.resource_types], ["Level", "Filling"])
        self.assertEqual([p.name for p in decl.config_parameters], ["initialLevel"])
        self.assertEqual(len(decl.identity_hash()), 16)

    def test_the_declaration_is_described_once_and_cached(self):
        """The identity hash has to be stable for the life of the process; re-describing on every
        /models poll would let a not-quite-deterministic model hand merlin a new attestation each
        time it looks."""
        backend = self.backend()
        calls = []
        real_run = backend._run
        backend._run = lambda verb, stdin_text=None: (calls.append(verb), real_run(verb, stdin_text))[1]
        first, second = backend.declaration(), backend.declaration()
        self.assertIs(first, second)
        self.assertEqual(calls, ["describe"])

    def test_an_explicit_required_parameters_list_wins_over_the_default_convention(self):
        decl = ac.declaration_from_json({"activityTypes": [
            {"name": "X", "parameters": [{"name": "p", "schema": INT, "default": 3},
                                         {"name": "q", "schema": INT}],
             "requiredParameters": ["p"]}]})
        self.assertEqual(decl.activity_types[0].required_parameters, ["p"])

    def test_a_round_trip_through_the_generic_layer(self):
        backend = self.backend()
        decl = backend.declaration()
        # `rate` omitted, an undeclared name supplied: the model sees neither problem, because the
        # generic layer resolves both before the process is ever started.
        request = decl.normalize({"planStart": "2024-01-01T00:00:00Z", "duration": 4 * S,
                                  "configuration": {"initialLevel": 5.0},
                                  "directives": [{"id": 7, "type": "Fill", "startOffset": 1 * S,
                                                  "arguments": {"duration": 2 * S, "junk": "x"}}]})
        out = check_response(backend.simulate(request))
        self.assertEqual([s["duration"] for s in out["realProfiles"]["Level"]["segments"]],
                         [1 * S, 2 * S, 1 * S])
        self.assertEqual([s["dynamics"]["rate"] for s in out["realProfiles"]["Level"]["segments"]],
                         [0.0, 1.0, 0.0])
        self.assertEqual([s["dynamics"] for s in out["discreteProfiles"]["Filling"]["segments"]],
                         [False, True, False])
        span = out["spans"][0]
        self.assertEqual(span["directiveId"], 7)
        self.assertEqual(span["arguments"], {"duration": 2 * S, "rate": 1.0})   # default filled in
        self.assertEqual(span["computedAttributes"], {"added": 2.0})

    def test_an_activity_outliving_the_window_comes_back_unfinished(self):
        backend = self.backend()
        request = backend.declaration().normalize(
            {"duration": 2 * S, "configuration": {},
             "directives": [{"id": 1, "type": "Fill", "startOffset": 1 * S,
                             "arguments": {"duration": 9 * S}}]})
        span = check_response(backend.simulate(request))["spans"][0]
        self.assertNotIn("duration", span)
        self.assertNotIn("computedAttributes", span)

    def test_the_typechecker_stops_a_bad_argument_before_the_process_starts(self):
        """The whole point of the split: the model never has to implement `nonconformance`."""
        decl = self.backend().declaration()
        with self.assertRaises(BadRequest) as ctx:
            decl.normalize({"duration": 1, "directives": [
                {"id": 1, "type": "Fill", "startOffset": 0, "arguments": {"duration": "2s"}}]})
        self.assertIn("expected a duration as integer microseconds", str(ctx.exception))

    def test_a_nonzero_exit_becomes_an_error_carrying_stderr(self):
        backend = self.backend()
        request = backend.declaration().normalize(
            {"duration": 10 * S, "configuration": {},
             "directives": [{"id": 4, "type": "Fill", "startOffset": 0,
                             "arguments": {"duration": -5}}]})
        with self.assertRaises(ModelError) as ctx:
            backend.simulate(request)
        self.assertIn("exited 1", str(ctx.exception))
        self.assertIn("directive 4: a Fill cannot last -5 microseconds", str(ctx.exception))

    def test_an_unknown_verb_or_missing_executable_is_a_clear_error(self):
        with self.assertRaises(ModelError) as ctx:
            ExecBackend("gone", ["/nonexistent/model-binary"]).declaration()
        self.assertIn("not found", str(ctx.exception))

    def test_unparseable_stdout_is_reported_with_what_was_written(self):
        backend = ExecBackend("noisy", [sys.executable, "-c",
                                        "import sys; sys.stdout.write('not json at all')"])
        with self.assertRaises(ModelError) as ctx:
            backend.declaration()
        self.assertIn("unparseable JSON", str(ctx.exception))
        self.assertIn("not json at all", str(ctx.exception))

    def test_a_hung_model_times_out_rather_than_wedging_the_adapter(self):
        backend = ExecBackend("slow", [sys.executable, "-c", "import time; time.sleep(30)"],
                              timeout=0.5)
        with self.assertRaises(ModelError) as ctx:
            backend.declaration()
        self.assertIn("did not answer", str(ctx.exception))

    def test_stderr_from_a_SUCCESSFUL_run_is_a_log_not_a_failure(self):
        backend = ExecBackend("chatty", [sys.executable, "-c",
                                         "import sys; sys.stderr.write('loading kernels\\n'); "
                                         "sys.stdout.write('{\"activityTypes\": []}')"])
        self.assertEqual(backend.declaration().activity_types, [])

    def test_exec_backends_from_env(self):
        os.environ["TEST_EXEC_MODELS"] = json.dumps({"tank": [sys.executable, TANK]})
        try:
            backends = ac.exec_backends_from_env("TEST_EXEC_MODELS")
            self.assertEqual(list(backends), ["tank"])
            self.assertEqual(backends["tank"].declaration().key, "tank")
        finally:
            del os.environ["TEST_EXEC_MODELS"]
        self.assertEqual(ac.exec_backends_from_env("TEST_EXEC_MODELS"), {})


class TestExecBackendOverHttp(HttpTestCase):
    """The whole point: a model that implements two stdio verbs gets the entire contract."""

    @classmethod
    def make_backends(cls):
        return {"tank": ExecBackend("tank", [sys.executable, TANK])}

    def test_models(self):
        code, out = self.call("GET", "/models")
        self.assertEqual(code, 200)
        self.assertEqual(out["models"][0]["key"], "tank")
        self.assertEqual(len(out["models"][0]["identityHash"]), 16)

    def test_introspect_reports_required_parameters_it_never_declared_itself(self):
        code, out = self.call("GET", "/introspect?model=tank")
        self.assertEqual(code, 200)
        self.assertEqual(out["activityTypes"][0]["requiredParameters"], ["duration"])

    def test_validate_typechecks_a_model_that_has_no_typechecker(self):
        code, out = self.call("POST", "/validate?model=tank", {"activities": [
            {"type": "Fill", "arguments": {"duration": "an hour"}},
            {"type": "Fill", "arguments": {}},
            {"type": "Fill", "arguments": {"duration": 1, "bogus": 2}}]})
        self.assertEqual(code, 200)
        self.assertEqual([r["valid"] for r in out["results"]], [False, False, False])
        self.assertIn("expected a duration", out["results"][0]["notices"][0]["message"])
        self.assertEqual(out["results"][1]["notices"][0]["message"],
                         "missing required parameter 'duration'")
        self.assertEqual(out["results"][2]["notices"][0]["message"],
                         "unrecognized parameter 'bogus'")
        self.assertEqual(out["results"][2]["effectiveArguments"], {"duration": 1, "rate": 1.0})

    def test_simulate_end_to_end(self):
        code, out = self.call("POST", "/simulate?model=tank", {
            "planStart": "2024-01-01T00:00:00Z", "duration": 4 * S,
            "configuration": {"initialLevel": 2.0},
            "directives": [{"id": 1, "type": "Fill", "startOffset": 0,
                            "arguments": {"duration": 2 * S, "rate": 3.0}}]})
        self.assertEqual(code, 200)
        self.assertEqual(out["realProfiles"]["Level"]["segments"][0],
                         {"duration": 2 * S, "dynamics": {"initial": 2.0, "rate": 3.0}})
        self.assertEqual(out["spans"][0]["computedAttributes"], {"added": 6.0})

    def test_a_model_that_dies_surfaces_its_stderr_as_a_500(self):
        code, out = self.call("POST", "/simulate?model=tank", {
            "duration": 10 * S, "configuration": {},
            "directives": [{"id": 2, "type": "Fill", "startOffset": 0,
                            "arguments": {"duration": -1}}]})
        self.assertEqual(code, 500)
        self.assertIn("a Fill cannot last -1 microseconds", out["error"])


if __name__ == "__main__":
    unittest.main()
