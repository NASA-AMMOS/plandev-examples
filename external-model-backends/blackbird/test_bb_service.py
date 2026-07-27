#!/usr/bin/env python3
"""Tests for the BLACKBIRD-specific half of bb_service.py.

    python3 test_bb_service.py            # offline; no adapter, no JVM, no network
    python3 test_bb_service.py -v

The generic half now lives in adapter_core and is tested by ../test_adapter_core.py. What is left
here is the translation layer, and the two places it can go wrong silently:

  * `build_declaration`. Blackbird type strings become PlanDev ValueSchemas and Blackbird's TEXTUAL
    defaults become PlanDev values. Get the second one wrong and the default fails its own
    parameter's typecheck the moment adapter_core fills it in.
  * `published_digest_payload`. The identityHash merlin STORES is minted from it, so its layout is
    frozen by deployment, not by taste. Reshaping it re-attests every deployed Blackbird model.
    The shape is pinned here from both directions -- what it contains, and what it deliberately
    does NOT (see the KNOWN GAP below).

Nothing here starts a JVM: `load_model`'s output is a plain dict, so a realistic one is written out
by hand.
"""
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bb_service as S
from adapter_core import Directive

DURATION = {"type": "duration"}
REAL = {"type": "real"}
STRING = {"type": "string"}
STRING_MAP = {"type": "series", "items": {"type": "struct",
                                          "items": {"key": STRING, "value": STRING}}}


def stub_model(**kw):
    """What `load_model` returns, without needing Blackbird to say it.

    Shaped after the real powermodel: one activity with a textual duration default, one with a map
    parameter, a linear real resource and a variant one, and the adaptation globals BbParams reports.
    """
    model = {
        "cp": "/cp", "name": "demo", "version": "1.0.0",
        "param_types": {
            "ActivityThree": [("d", "duration"), ("stringList", "list<string>")],
            "ActivityFour": [("d", "duration"), ("stringMap", "map<string, string>")],
            "ActivityTwo": [("amount", "float")],
        },
        "param_defaults": {"ActivityThree": {"d": "00:01:00"}},
        "res_specs": {"SolarPower": ({"type": "real"}, True),
                      "Mode": ({"type": "variant",
                                "variants": [{"key": "On", "label": "On"}]}, False)},
        "initials": {"SolarPower": 0.0},
        "config_specs": [
            {"name": "AdaptationGlobals.LANDING_EPOCH", "cls": "AdaptationGlobals",
             "field": "LANDING_EPOCH", "bbtype": "Time", "default": "2020-001T00:00:00.000000"},
            {"name": "AdaptationGlobals.NumStarTrackers", "cls": "AdaptationGlobals",
             "field": "NumStarTrackers", "bbtype": "int", "default": "3"},
        ],
    }
    model.update(kw)
    return model


class TestBbtypeToSchema(unittest.TestCase):
    def test_scalars(self):
        for bt, schema in (("double", REAL), ("float", REAL), ("int", {"type": "int"}),
                           ("long", {"type": "int"}), ("duration", DURATION),
                           ("boolean", {"type": "boolean"}), ("string", STRING)):
            self.assertEqual(S.bbtype_to_schema(bt), schema, bt)

    def test_a_time_or_custom_type_is_carried_as_its_string_form(self):
        """PlanDev's ValueSchema has no absolute-time type, and a custom ConvertableFromString has
        no shape we can know."""
        self.assertEqual(S.bbtype_to_schema("Time"), STRING)
        self.assertEqual(S.bbtype_to_schema("SomeAdaptationEnum"), STRING)

    def test_a_map_is_a_series_of_key_value_structs(self):
        """merlin's MapValueMapper convention -- what makes a Blackbird map behave like any other
        Aerie map in constraints, the UI and the generated typings."""
        self.assertEqual(S.bbtype_to_schema("map<string, string>"), STRING_MAP)

    def test_containers_nest(self):
        self.assertEqual(S.bbtype_to_schema("list<list<int>>"),
                         {"type": "series", "items": {"type": "series", "items": {"type": "int"}}})
        self.assertEqual(S.bbtype_to_schema("map<string, list<string>>")["items"]["items"]["value"],
                         {"type": "series", "items": STRING})


class TestCoerceDefault(unittest.TestCase):
    """Blackbird writes every dictionary default as TEXT. It has to reach PlanDev's value space
    before adapter_core fills it in, or the default fails its own parameter's typecheck."""

    def test_a_duration_default_becomes_integer_microseconds(self):
        self.assertEqual(S.coerce_default("duration", "00:01:00"), 60_000_000)
        self.assertEqual(S.coerce_default("duration", "1T00:00:00"), 86_400_000_000)

    def test_numeric_and_boolean_defaults(self):
        self.assertEqual(S.coerce_default("int", "3"), 3)
        self.assertEqual(S.coerce_default("float", "1.5"), 1.5)
        self.assertIs(S.coerce_default("boolean", "true"), True)
        self.assertIs(S.coerce_default("boolean", "TRUE"), True)
        self.assertIs(S.coerce_default("boolean", "no"), False)

    def test_an_unconvertible_default_is_passed_through_rather_than_dropped(self):
        """A default we cannot read is still better information than no default at all."""
        self.assertEqual(S.coerce_default("duration", "whenever"), "whenever")
        self.assertEqual(S.coerce_default("int", "lots"), "lots")
        self.assertEqual(S.coerce_default("Time", "2020-001T00:00:00.000000"),
                         "2020-001T00:00:00.000000")


class TestBuildDeclaration(unittest.TestCase):
    def setUp(self):
        self.decl = S.build_declaration("demo", stub_model())

    def test_parameters_keep_blackbirds_declaration_order(self):
        """Blackbird's .plan.json reader binds parameters POSITIONALLY, and merlin persists an
        `order` from this array's indices, so the order is the contract twice over."""
        act = self.decl.activity_type("ActivityFour")
        self.assertEqual([p.name for p in act.parameters], ["d", "stringMap"])
        self.assertEqual([p.schema for p in act.parameters], [DURATION, STRING_MAP])

    def test_a_textual_default_is_converted_once_at_load_time(self):
        three = self.decl.activity_type("ActivityThree")
        self.assertEqual(three.by_name["d"].default, 60_000_000)
        self.assertEqual(self.decl.effective_args("ActivityThree", {"stringList": ["a"]}),
                         {"d": 60_000_000, "stringList": ["a"]})

    def test_a_converted_default_satisfies_its_own_parameters_schema(self):
        """The point of converting at load time: adapter_core typechecks whatever it fills in."""
        for act in self.decl.activity_types:
            for p in act.parameters:
                if p.default is not None:
                    self.assertIsNone(S.adapter_core.nonconformance(p.default, p.schema),
                                      "%s.%s default %r" % (act.name, p.name, p.default))

    def test_required_parameters_are_exactly_those_blackbird_gave_no_default(self):
        self.assertEqual(self.decl.activity_type("ActivityThree").required_parameters, ["stringList"])
        self.assertEqual(self.decl.activity_type("ActivityFour").required_parameters, ["d", "stringMap"])

    def test_every_activity_type_declares_the_computed_attributes_schema(self):
        """Blackbird attaches its own activity UUID to every finished span; the gate rejects a
        computed attribute that was not declared."""
        for act in self.decl.activity_types:
            self.assertEqual(act.computed_attributes_schema, S.COMPUTED_ATTRIBUTES_SCHEMA)

    def test_resources_carry_their_translated_schema(self):
        self.assertEqual({r.name: r.schema for r in self.decl.resource_types},
                         {"SolarPower": REAL,
                          "Mode": {"type": "variant", "variants": [{"key": "On", "label": "On"}]}})

    def test_configuration_parameters_declare_NO_adapter_side_default(self):
        """The adaptation already holds its own. Saying "unset" is what makes config_script_lines
        emit no SET_PARAMETER line and leave Blackbird's value alone."""
        self.assertEqual([(p.name, p.schema, p.default) for p in self.decl.config_parameters],
                         [("AdaptationGlobals.LANDING_EPOCH", STRING, None),
                          ("AdaptationGlobals.NumStarTrackers", {"type": "int"}, None)])
        self.assertEqual(self.decl.effective_config({}),
                         {"AdaptationGlobals.LANDING_EPOCH": None,
                          "AdaptationGlobals.NumStarTrackers": None})

    def test_introspect_reports_configuration_without_defaults(self):
        """/introspect has no field for a default; PlanDev stores name and schema only."""
        self.assertEqual(self.decl.introspect()["parameters"],
                         [{"name": "AdaptationGlobals.LANDING_EPOCH", "schema": STRING},
                          {"name": "AdaptationGlobals.NumStarTrackers", "schema": {"type": "int"}}])


class TestPublishedDigestPayload(unittest.TestCase):
    """The identityHash merlin stores is minted from this payload, so its LAYOUT is frozen by every
    deployment that has already recorded a hash."""

    def setUp(self):
        self.payload = S.published_digest_payload(stub_model())

    def test_the_payload_has_exactly_the_published_keys(self):
        self.assertEqual(set(self.payload), {"acts", "res", "cfg", "computed"})

    def test_activity_entries_are_name_schema_PAIRS(self):
        """Pairs, not triples: the published layout carries no default. See the KNOWN GAP test."""
        self.assertEqual(self.payload["acts"]["ActivityFour"],
                         [["d", DURATION], ["stringMap", STRING_MAP]])

    def test_it_hashes_the_TRANSLATED_schemas_not_blackbirds_type_strings(self):
        """Hashing the Blackbird-side names missed a whole class of drift: changing how the adapter
        maps map<string,string> leaves every stored parameter schema wrong while the hash claims
        nothing happened."""
        blob = json.dumps(self.payload, sort_keys=True, default=str)
        self.assertNotIn("map<string, string>", blob)
        self.assertIn('"series"', blob)

    def test_configuration_entries_are_name_schema_pairs(self):
        self.assertEqual(self.payload["cfg"],
                         [["AdaptationGlobals.LANDING_EPOCH", STRING],
                          ["AdaptationGlobals.NumStarTrackers", {"type": "int"}]])

    def test_the_computed_attributes_schema_is_in_the_digest(self):
        """Stored in activity_type -- if it drifts, the gate starts rejecting spans against a stale
        schema."""
        self.assertEqual(self.payload["computed"], S.COMPUTED_ATTRIBUTES_SCHEMA)

    def test_reordering_parameters_moves_the_hash(self):
        moved = stub_model(param_types={
            "ActivityThree": [("d", "duration"), ("stringList", "list<string>")],
            "ActivityFour": [("stringMap", "map<string, string>"), ("d", "duration")],
            "ActivityTwo": [("amount", "float")]})
        self.assertNotEqual(S.build_declaration("demo", moved).identity_hash(),
                            S.build_declaration("demo", stub_model()).identity_hash())

    def test_changing_a_parameter_or_resource_or_config_schema_moves_the_hash(self):
        baseline = S.build_declaration("demo", stub_model()).identity_hash()
        variants = {
            "parameter type": stub_model(param_types=dict(
                stub_model()["param_types"], ActivityTwo=[("amount", "int")])),
            "resource type": stub_model(res_specs=dict(
                stub_model()["res_specs"], SolarPower=({"type": "int"}, False))),
            "config type": stub_model(config_specs=[
                dict(stub_model()["config_specs"][0], bbtype="int")]),
            "extra activity": stub_model(param_types=dict(
                stub_model()["param_types"], ActivityNine=[("endTime", "time")])),
        }
        for label, model in variants.items():
            with self.subTest(change=label):
                self.assertNotEqual(S.build_declaration("demo", model).identity_hash(), baseline)

    def test_KNOWN_GAP_changing_a_default_does_NOT_move_the_hash(self):
        """Documented, not endorsed.

        merlin persists requiredParameters in activity_type and its gate enforces them, so flipping
        a Blackbird parameter between required and optional -- or changing what it defaults to --
        changes what PlanDev believes while this hash says nothing happened. The Python adapter's
        payload does cover defaults, and adapter_core's canonical `Declaration.digest_payload`
        covers both; adopting it is the fix, at the cost of a one-time re-attestation of every
        deployed Blackbird model. This test exists so that day is a deliberate decision and not a
        surprise.
        """
        baseline = S.build_declaration("demo", stub_model()).identity_hash()
        changed_default = stub_model(param_defaults={"ActivityThree": {"d": "99:00:00"}})
        dropped_default = stub_model(param_defaults={})
        self.assertEqual(S.build_declaration("demo", changed_default).identity_hash(), baseline)
        self.assertEqual(S.build_declaration("demo", dropped_default).identity_hash(), baseline)
        # ...even though PlanDev's stored requiredParameters genuinely differs:
        self.assertEqual(S.build_declaration("demo", dropped_default)
                         .activity_type("ActivityThree").required_parameters, ["d", "stringList"])

    def test_the_canonical_payload_WOULD_catch_it(self):
        """The migration target, pinned so the fix is known to work when someone takes it."""
        base = S.build_declaration("demo", stub_model())
        dropped = S.build_declaration("demo", stub_model(param_defaults={}))
        self.assertNotEqual(base.digest_payload(), dropped.digest_payload())


class TestConfigScriptLines(unittest.TestCase):
    def setUp(self):
        self.specs = stub_model()["config_specs"]

    def test_an_unset_parameter_gets_no_line_so_blackbirds_own_default_stands(self):
        self.assertEqual(S.config_script_lines({}, self.specs), "")
        self.assertEqual(S.config_script_lines(
            {"AdaptationGlobals.LANDING_EPOCH": None,
             "AdaptationGlobals.NumStarTrackers": None}, self.specs), "")

    def test_a_supplied_parameter_becomes_a_SET_PARAMETER_line(self):
        self.assertEqual(S.config_script_lines({"AdaptationGlobals.NumStarTrackers": 5}, self.specs),
                         "SET_PARAMETER AdaptationGlobals.NumStarTrackers 5\n")

    def test_lines_follow_the_declared_order_not_the_requests(self):
        """Independent assignments, so order does not change the outcome -- but it does make the
        generated script reproducible from one request to the next."""
        out = S.config_script_lines({"AdaptationGlobals.NumStarTrackers": 5,
                                     "AdaptationGlobals.LANDING_EPOCH": "2024-001T00:00:00"},
                                    self.specs)
        self.assertEqual(out.splitlines(),
                         ["SET_PARAMETER AdaptationGlobals.LANDING_EPOCH 2024-001T00:00:00",
                          "SET_PARAMETER AdaptationGlobals.NumStarTrackers 5"])

    def test_a_duration_arrives_in_blackbirds_own_notation(self):
        specs = [{"name": "G.Pad", "bbtype": "duration"}]
        self.assertEqual(S.config_script_lines({"G.Pad": 90_000_000}, specs),
                         "SET_PARAMETER G.Pad 00:01:30.000000\n")

    def test_a_container_is_refused_because_SET_PARAMETER_cannot_express_one(self):
        specs = [{"name": "G.Names", "bbtype": "list<string>"}]
        self.assertEqual(S.config_script_lines({"G.Names": ["a", "b"]}, specs), "")


class TestBuildPlanJson(unittest.TestCase):
    def build(self, typ, arguments, tmpdir):
        path, by_uuid = S.build_plan_json(
            S.VALIDATE_PLAN_START,
            [Directive(id=1, type=typ, start_offset=0, arguments=arguments)],
            tmpdir, stub_model()["param_types"])
        with open(path) as f:
            return json.load(f)["activities"][0], by_uuid

    def test_parameters_are_emitted_in_declared_order_with_native_values(self):
        import tempfile
        with tempfile.TemporaryDirectory() as wd:
            act, _ = self.build("ActivityFour",
                                {"stringMap": [{"key": "k1", "value": "v1"}], "d": 600_000_000}, wd)
        # Blackbird binds POSITIONALLY and ignores `name`, so the order IS the binding.
        self.assertEqual([p["name"] for p in act["parameters"]], ["d", "stringMap"])
        # A duration goes back to Blackbird's notation; a map goes back to a native JSON object.
        self.assertEqual(act["parameters"][0]["value"], "00:10:00.000000")
        self.assertEqual(act["parameters"][1]["value"], {"k1": "v1"})

    def test_a_directive_id_maps_to_a_stable_blackbird_uuid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as wd:
            act, by_uuid = self.build("ActivityTwo", {"amount": 1.0}, wd)
            act2, _ = self.build("ActivityTwo", {"amount": 1.0}, wd)
        self.assertEqual(act["id"], act2["id"])        # uuid5, so the same directive maps the same way
        self.assertEqual(by_uuid[act["id"]], 1)


TOL = """<?xml version="1.0"?>
<TOL>
 <TOLrecord type="ACT_START">
  <Instance>
   <ID>%(uuid)s</ID><Type>ActivityTwo</Type><Parent></Parent>
   <Attributes>
    <Attribute><Name>start</Name><TimeValue>2024-001T00:00:00.000000</TimeValue></Attribute>
    <Attribute><Name>span</Name><DurationValue>%(span)s</DurationValue></Attribute>
   </Attributes>
   <Parameters><Parameter><Name>amount</Name><DoubleValue>42.5</DoubleValue></Parameter></Parameters>
  </Instance>
 </TOLrecord>
</TOL>
"""


class TestParseOutputSpanRule(unittest.TestCase):
    """A finished span carries BOTH `duration` and `computedAttributes`; an unfinished one carries
    NEITHER. merlin uses that pairing to tell them apart (PostgresResultsCellRepository), and
    adapter_core's check_response now refuses to serialize anything else."""

    def parse(self, span_len, window):
        import tempfile
        with tempfile.TemporaryDirectory() as wd:
            path = os.path.join(wd, "out.xml")
            with open(path, "w") as f:
                f.write(TOL % {"uuid": "abc-123", "span": span_len})
            _, _, spans = S.parse_output(path, S.VALIDATE_PLAN_START.replace(year=2024), window, {})
        return spans[0]

    def test_a_finished_span_carries_both(self):
        span = self.parse("01:00:00", 4 * 3600 * 1_000_000)
        self.assertEqual(span["duration"], 3600 * 1_000_000)
        self.assertEqual(span["computedAttributes"], {"blackbirdId": "abc-123"})

    def test_a_span_outliving_the_window_carries_NEITHER(self):
        """This adapter used to attach computed attributes unconditionally, so every unfinished
        Blackbird span read to merlin as finished-with-no-end."""
        span = self.parse("09:00:00", 4 * 3600 * 1_000_000)
        self.assertNotIn("duration", span)
        self.assertNotIn("computedAttributes", span)
        self.assertEqual(set(span),
                         {"spanId", "type", "startOffset", "arguments", "parentId", "directiveId"})

    def test_a_span_ending_exactly_at_the_window_edge_counts_as_finished(self):
        span = self.parse("04:00:00", 4 * 3600 * 1_000_000)
        self.assertIn("duration", span)
        self.assertIn("computedAttributes", span)

    def test_arguments_come_back_through_the_shared_value_reader(self):
        self.assertEqual(self.parse("01:00:00", 4 * 3600 * 1_000_000)["arguments"], {"amount": 42.5})

    def test_the_result_satisfies_the_generic_response_check(self):
        for span_len in ("01:00:00", "09:00:00"):
            with self.subTest(span=span_len):
                S.adapter_core.check_response(
                    {"realProfiles": {}, "discreteProfiles": {},
                     "spans": [self.parse(span_len, 4 * 3600 * 1_000_000)]})


class TestReadResValue(unittest.TestCase):
    def read(self, xml):
        return S.read_res_value(ET.fromstring(xml))

    def test_scalars(self):
        self.assertEqual(self.read("<R><DoubleValue>1.5</DoubleValue></R>"), 1.5)
        self.assertEqual(self.read("<R><IntegerValue>7</IntegerValue></R>"), 7)
        self.assertIs(self.read("<R><BooleanValue>true</BooleanValue></R>"), True)
        self.assertEqual(self.read("<R><DurationValue>00:00:01</DurationValue></R>"), 1_000_000)

    def test_a_struct_value_becomes_a_key_value_series(self):
        """Blackbird's StructValue IS a map; a bare {k: v} object would contradict the declared
        schema and the ingest gate would flag it."""
        self.assertEqual(
            self.read('<R><StructValue><Element index="k"><StringValue>v</StringValue></Element>'
                      '</StructValue></R>'),
            [{"key": "k", "value": "v"}])

    def test_a_list_value_recurses(self):
        self.assertEqual(
            self.read('<R><ListValue><Element index="0"><IntegerValue>1</IntegerValue></Element>'
                      '<Element index="1"><IntegerValue>2</IntegerValue></Element></ListValue></R>'),
            [1, 2])

    def test_a_custom_comparable_type_is_carried_as_its_text(self):
        """Beats dropping the value silently, and matches the "string" schema parse_res_specs gives it."""
        self.assertEqual(self.read("<R><MyEnumValue>RED</MyEnumValue></R>"), "RED")


class TestCleanBbError(unittest.TestCase):
    def test_a_root_cause_wins(self):
        self.assertEqual(
            S.clean_bb_error("Exception in thread \"main\"\nRoot cause:\n"
                             "Error: Cannot cast value \"lots\" from JSON to type: java.lang.Double\n"
                             "\tat gov.nasa.jpl.Blackbird.main(Blackbird.java:35)"),
            'Error: Cannot cast value "lots" from JSON to type: java.lang.Double')

    def test_stack_frames_are_dropped(self):
        self.assertNotIn("at gov.nasa", S.clean_bb_error("Cannot convert null\n\tat gov.nasa.jpl.X"))

    def test_an_empty_stderr_still_says_something(self):
        self.assertEqual(S.clean_bb_error(""), "invalid arguments")


class TestModuleIsImportable(unittest.TestCase):
    def test_importing_the_module_does_not_start_a_server_or_a_jvm(self):
        """Server startup and model loading are behind `if __name__ == "__main__"`. bb_import.py
        imports this module as a library, so anything at module scope runs on every import."""
        self.assertFalse(hasattr(S, "BACKENDS"))
        self.assertFalse(hasattr(S, "PORT"))
        with open(os.path.abspath(S.__file__)) as f:
            head = f.read().split('if __name__ == "__main__":')[0]
        self.assertNotIn("adapter_core.serve", head)
        self.assertNotIn("load_model(", head.split("def load_model")[0])


if __name__ == "__main__":
    unittest.main()
