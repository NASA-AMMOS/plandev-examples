"""The Phase 0 assertion: the JSON Schema and the gate divide the work, and the division is real.

Three claims, and the third is the one that matters:

  1. the schema accepts the valid fixture
  2. the schema rejects every `schema`-layer fixture, naming the field
  3. the schema ACCEPTS every `importer`- and `gate`-layer fixture

(3) is what makes the split more than an assertion in a document. If the schema quietly grew a
rule the gate already owns, a gate fixture would start failing here and this test would say so.
"""

import json
import os
import re

import pytest

jsonschema = pytest.importorskip(
    "jsonschema", reason="pip install jsonschema to check the run-transfer schema")

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "run-transfer.v1.schema.json")
FIXTURES = os.path.join(HERE, "fixtures")


def load(path):
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def validator():
    schema = load(SCHEMA)
    # Draft-07 explicitly, matching the ajv ^6 pinned in aerie-gateway. Authoring 2020-12 and
    # discovering the mismatch at runtime is the failure this pins down.
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


@pytest.fixture(scope="module")
def manifest():
    return load(os.path.join(FIXTURES, "invalid", "MANIFEST.json"))


def errors(validator, doc):
    return sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))


def by_layer(manifest, layer):
    return [entry for entry in manifest if entry["layer"] == layer]


# ---- 1. the valid fixture ----------------------------------------------------------------------

def test_valid_fixture_conforms(validator):
    doc = load(os.path.join(FIXTURES, "valid", "synthetic.run.json"))
    assert errors(validator, doc) == []


def test_valid_fixture_exercises_the_hard_cases(validator):
    """A fixture that drifted into being trivial would still pass the schema, so pin what it covers."""
    doc = load(os.path.join(FIXTURES, "valid", "synthetic.run.json"))
    spans = doc["results"]["spans"]
    profiles = doc["results"]["profiles"]

    assert len(doc["model"]["activityTypes"]) >= 2
    assert {p["type"] for p in profiles.values()} == {"real", "discrete"}

    # a two-level decomposition: some span's parent is itself parented
    parents = {s["spanId"]: s.get("parentId") for s in spans}
    assert any(parents.get(parents[sid]) is not None for sid in parents if parents.get(sid)), \
        "no grandchild span: the decomposition is only one level deep"

    # one unfinished span, and it carries no computed attributes
    unfinished = [s for s in spans if "duration" not in s]
    assert len(unfinished) == 1
    assert "computedAttributes" not in unfinished[0]

    # decomposition children never claim a directive
    assert all("directiveLocalId" not in s for s in spans if "parentId" in s)

    # one anchored directive, anchored by localId
    localIds = {a["localId"] for a in doc["plan"]["activities"]}
    anchored = [a for a in doc["plan"]["activities"] if a.get("anchor_id")]
    assert len(anchored) == 1 and anchored[0]["anchor_id"] in localIds

    # a discrete gap -- a segment with no dynamics at all
    assert any("dynamics" not in seg
               for p in profiles.values() if p["type"] == "discrete"
               for seg in p["segments"])

    # profiles lie consecutively from 0 and do not overrun the simulation
    for name, profile in profiles.items():
        assert sum(s["duration"] for s in profile["segments"]) <= doc["results"]["duration"], name


# ---- 2. the schema layer -----------------------------------------------------------------------

def test_every_schema_fixture_is_rejected(validator, manifest):
    accepted = []
    for entry in by_layer(manifest, "schema"):
        doc = load(os.path.join(FIXTURES, "invalid", entry["fixture"]))
        if not errors(validator, doc):
            accepted.append(entry["fixture"])
    assert accepted == [], "schema-layer fixtures the schema does not catch"


def test_schema_rejections_name_the_field(validator, manifest):
    """A rejection whose message cannot point at a field is not usable by a producer."""
    for entry in by_layer(manifest, "schema"):
        doc = load(os.path.join(FIXTURES, "invalid", entry["fixture"]))
        found = errors(validator, doc)
        assert found, entry["fixture"]
        # Either the error is anchored at a path, or it is a top-level keyword failure whose
        # message names the member (`kind`, `version`).
        anchored = any(e.absolute_path for e in found)
        names_member = any(re.search(r"\b(kind|version)\b", e.message) for e in found)
        assert anchored or names_member, "%s: %r" % (entry["fixture"], [e.message for e in found])


# ---- 3. the division ---------------------------------------------------------------------------

def test_schema_accepts_every_gate_and_importer_fixture(validator, manifest):
    """The point of the split. A failure here means the schema took over a rule the gate owns."""
    rejected = {}
    for entry in by_layer(manifest, "gate") + by_layer(manifest, "importer"):
        doc = load(os.path.join(FIXTURES, "invalid", entry["fixture"]))
        found = errors(validator, doc)
        if found:
            rejected[entry["fixture"]] = [e.message for e in found]
    assert rejected == {}, "the schema is enforcing rules that belong to the gate"


def test_every_fixture_is_in_the_manifest(manifest):
    on_disk = set()
    for layer in ("schema", "importer", "gate"):
        directory = os.path.join(FIXTURES, "invalid", layer)
        for name in os.listdir(directory):
            if name.endswith(".run.json"):
                on_disk.add("%s/%s" % (layer, name))
    assert on_disk == {entry["fixture"] for entry in manifest}


def test_every_fixture_states_the_message_its_layer_should_produce(manifest):
    """'Done when' for Phase 0: a reviewer can state which layer rejects each file and what it says."""
    for entry in manifest:
        assert entry["layer"] in ("schema", "importer", "gate"), entry
        assert entry["what"], entry
        # Gate messages are quoted verbatim from ExternalResultsGate, and the shortest real one
        # ("duplicate spanId 3") is 18 characters. The bar is "a reviewer can act on it", not length.
        assert len(entry["message"]) >= 18, entry


def test_committed_fixtures_match_the_generator():
    """Consumers in other repos read the committed JSON, so a stale file is a silently wrong test."""
    import subprocess
    import sys
    result = subprocess.run([sys.executable, os.path.join(HERE, "make_fixtures.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
