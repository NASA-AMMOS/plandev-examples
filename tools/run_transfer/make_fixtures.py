#!/usr/bin/env python3
"""Generate the invalid run-transfer fixtures as named mutations of the valid one.

Committed outputs live under `fixtures/invalid/`, so consumers in other repos (the gateway's
ajv tests, plandev's e2e suite) just read the JSON and never run this. The mutations are here
so a reviewer can see what each fixture changes -- an 18-way diff of near-identical 200-line
files tells you nothing.

Each fixture declares the LAYER expected to refuse it, and that claim is what
`test_run_transfer.py` checks:

  schema    -- the JSON Schema refuses it (shape or syntax)
  importer  -- the gateway refuses it while resolving the file's own cross-references
               (localId -> directive id), before anything is written
  gate      -- ExternalResultsGate refuses it: admissible shape, inadmissible against the
               declared model

`importer` and `gate` are both "the schema must ACCEPT this", which is the assertion that
proves the division is real rather than assumed.

    ./make_fixtures.py           # write fixtures
    ./make_fixtures.py --check   # fail if the committed ones are stale
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VALID = os.path.join(HERE, "fixtures", "valid", "synthetic.run.json")
OUT = os.path.join(HERE, "fixtures", "invalid")

# A JSON number that parses to +Infinity as a double in Java, Python and JS alike. Literal `NaN`
# and `Infinity` are NOT usable: Python's json accepts them, JSON.parse and ajv do not, so a
# fixture written that way would fail at parse rather than at the gate, in some readers only.
INF = 1e400


def at(doc, *path):
    """The container holding path[-1], plus that last key."""
    node = doc
    for key in path[:-1]:
        node = node[key]
    return node, path[-1]


def resolve(doc, *path):
    """The container AT path, for a mutation that adds rather than replaces."""
    for key in path:
        doc = doc[key]
    return doc


def set_(*path):
    def apply(doc, value):
        node, key = at(doc, *path)
        node[key] = value
    return apply


def append(*path):
    def apply(doc, value):
        resolve(doc, *path).append(value)
    return apply


def delete(*path):
    def apply(doc, _):
        node, key = at(doc, *path)
        del node[key]
    return apply


# (filename, layer, what it does, mutation, value, the message the refusal should carry)
FIXTURES = [
    # ---- schema layer: shape and syntax -----------------------------------------------------
    ("missing-required-field", "schema",
     "an activity with no localId",
     delete("plan", "activities", 0, "localId"),
     None,
     "plan.activities[0] is missing required property 'localId'"),

    ("wrong-kind", "schema",
     "kind is not plandev-run",
     set_("kind"), "plandev-plan",
     "kind must be 'plandev-run'; refused outright rather than sniffed"),

    ("unknown-version", "schema",
     "a major version this reader does not know",
     set_("version"), "3",
     "version '3' is not supported; this reader accepts version 1"),

    ("malformed-value-schema", "schema",
     "a series ValueSchema with no items",
     set_("model", "resourceTypes", 0, "schema"), {"type": "series"},
     "model.resourceTypes[0].schema is missing required property 'items'"),

    ("wrong-primitive-type", "schema",
     "results.duration as a string",
     set_("results", "duration"), "3600000000",
     "results.duration must be an integer (microseconds)"),

    ("calendar-date-start-time", "schema",
     "results.startTime as a calendar date instead of day-of-year",
     set_("results", "startTime"), "2026-01-01T00:00:00",
     "results.startTime must be uuuu-DDDTHH:MM:SS -- day of year, not a calendar date"),

    ("null-span-duration", "schema",
     "an unfinished span written as duration: null rather than omitting the field",
     set_("results", "spans", 4, "duration"), None,
     "results.spans[4].duration must be an integer; omit the field for an unfinished span"),

    ("unsupported-capability-without-reason", "schema",
     "a capability declared unsupported with no sentence to show",
     set_("model", "capabilities", "simulation"), {"supported": False},
     "model.capabilities.simulation is missing required property 'reason'"),

    # ---- importer layer: the file's own cross-references --------------------------------------
    ("unknown-directive-local-id", "importer",
     "a span claiming a directive localId no activity declares",
     set_("results", "spans", 0, "directiveLocalId"), "a99",
     "span 1 references directiveLocalId 'a99', which no activity in this file declares"),

    ("unknown-anchor-local-id", "importer",
     "an activity anchored to a localId no activity declares",
     set_("plan", "activities", 1, "anchor_id"), "a99",
     "activity 'a2' is anchored to 'a99', which no activity in this file declares"),

    ("duplicate-local-id", "importer",
     "two activities sharing one localId",
     set_("plan", "activities", 1, "localId"), "a1",
     "localId 'a1' is declared by more than one activity; it must be unique within the file"),

    # ---- gate layer: admissible shape, inadmissible content -----------------------------------
    ("unregistered-resource", "gate",
     "a profile for a resource the model never declared",
     set_("results", "profiles", "/thermal/tempC"),
     {"type": "real", "schema": {"type": "real"},
      "segments": [{"duration": 3600000000, "dynamics": {"initial": 20.0, "rate": 0.0}}]},
     "resource '/thermal/tempC' is not a registered resource type of this model"),

    ("resource-schema-drift", "gate",
     "a resource declared int whose profile is real",
     set_("model", "resourceTypes", 0, "schema"), {"type": "int"},
     "resource '/battery/soc' has schema RealSchema[] but is registered as IntSchema[]"),

    ("unregistered-activity-type", "gate",
     "a span whose type the model never declared",
     set_("results", "spans", 1, "type"), "Rewind",
     "span 2 has type 'Rewind', which is not a registered activity type"),

    ("argument-type-mismatch", "gate",
     "a string where the declared parameter is an int",
     set_("results", "spans", 0, "arguments", "priority"), "high",
     "span 1 (Observe) argument 'priority' is \"high\" where the schema says int"),

    ("duplicate-span-id", "gate",
     "two spans sharing one spanId",
     set_("results", "spans", 4, "spanId"), 1,
     "duplicate spanId 1"),

    ("unresolvable-parent", "gate",
     "a parentId that is not a span in this result",
     set_("results", "spans", 1, "parentId"), 99,
     "span 2 has parentId 99, which is not a span in this result"),

    ("parent-cycle", "gate",
     "1 -> 4 -> 3 -> 1",
     set_("results", "spans", 0, "parentId"), 4,
     "span 1 is part of a parent cycle"),

    # VERIFIED against a live gate, and only by sending the file's literal bytes. Anything that parses
    # this file and RE-SERIALIZES it first destroys the value before the gate can see it: Python emits
    # the non-standard token `Infinity` (which aeson and ajv reject), and JSON.stringify emits `null`
    # (which would silently become a profile GAP). So an intermediary must forward these bytes rather
    # than round-trip them -- see README.md, "Writing a producer".
    ("non-finite-real-dynamics", "gate",
     "a rate that parses to Infinity as a double",
     set_("results", "profiles", "/battery/soc", "segments", 0, "dynamics", "rate"), INF,
     "resource '/battery/soc' has a non-finite rate (Infinity)"),

    ("negative-duration", "gate",
     "a span of negative duration",
     set_("results", "spans", 2, "duration"), -900000000,
     "span 3 has negative duration (-900000000us)"),

    ("span-outside-window", "gate",
     "a span that starts inside the simulation and ends after it",
     set_("results", "spans", 2, "startOffset"), 3500000000,
     "span 3 runs to 4400000000us, past the simulation duration of 3600000000us; "
     "report it as unfinished (omit `duration`) instead of claiming an end the simulation never reached"),

    ("activity-type-name-not-ts-identifier", "gate",
     "a declared activity type whose name cannot be a bare TypeScript identifier",
     append("model", "activityTypes"),
     {"name": "2Slew", "parameters": [], "requiredParameters": [],
      "computedAttributesSchema": {"type": "struct", "items": {}}},
     "activity type '2Slew' is not a legal TypeScript identifier, so the generated constraint "
     "and scheduling typings for this model will not compile"),
]


def build():
    with open(VALID) as f:
        valid = json.load(f)

    manifest = []
    files = {}
    for name, layer, what, mutate, value, message in FIXTURES:
        doc = copy.deepcopy(valid)
        mutate(doc, value)
        files["%s/%s.run.json" % (layer, name)] = doc
        manifest.append({"fixture": "%s/%s.run.json" % (layer, name), "layer": layer,
                         "what": what, "message": message})
    return files, manifest


LAYER_BLURB = {
    "schema": "The JSON Schema refuses these: shape and syntax, before any model is in view.",
    "importer": "The importer refuses these while resolving the file's own cross-references, "
                "before anything is written.",
    "gate": "`ExternalResultsGate` refuses these: admissible shape, inadmissible against the "
            "declared model. **The schema must ACCEPT every one of them** -- that is the "
            "assertion that keeps the two layers genuinely separate.",
}


def readme(manifest):
    """Generated, so the table cannot drift from the fixtures it describes."""
    out = ["<!-- Generated by make_fixtures.py. Do not edit. -->",
           "# Invalid run-transfer fixtures",
           "",
           "Each fixture is the valid fixture (`../valid/synthetic.run.json`) with exactly one thing",
           "wrong, and it is filed under the layer expected to refuse it. `MANIFEST.json` is the",
           "machine-readable form; the mutations themselves are in `../../make_fixtures.py`.",
           ""]
    for layer in ("schema", "importer", "gate"):
        entries = [e for e in manifest if e["layer"] == layer]
        out += ["## `%s/` — %d fixtures" % (layer, len(entries)), "", LAYER_BLURB[layer], "",
                "| fixture | what is wrong | the refusal should say |", "|---|---|---|"]
        for e in entries:
            out.append("| `%s` | %s | %s |" % (
                e["fixture"].split("/", 1)[1], e["what"], e["message"].replace("|", "\\|")))
        out.append("")
    return "\n".join(out)


def main():
    check = "--check" in sys.argv
    files, manifest = build()
    files["MANIFEST.json"] = manifest
    files["README.md"] = readme(manifest)

    stale = []
    for rel, doc in files.items():
        path = os.path.join(OUT, rel)
        if rel.endswith(".md"):
            text = doc
        else:
            # json.dumps would write +Infinity as the non-standard token `Infinity`, which
            # JSON.parse and ajv reject. Rewrite it to 1e400, which every reader accepts and
            # every reader parses back to +Infinity as a double.
            text = json.dumps(doc, indent=2).replace("Infinity", "1e400") + "\n"
        if check:
            if not os.path.exists(path) or open(path).read() != text:
                stale.append(rel)
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    if check:
        if stale:
            print("stale fixtures (run make_fixtures.py):\n  " + "\n  ".join(sorted(stale)))
            return 1
        print("%d fixtures up to date" % (len(files) - 2))
        return 0

    print("wrote %d fixtures + MANIFEST.json + README.md to %s" % (len(files) - 2, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
