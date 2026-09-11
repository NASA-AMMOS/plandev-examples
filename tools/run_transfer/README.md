# Run transfer — the `.run.json` format

**Normative.** This is the reference a producer implements against. The rationale — why this
exists, why not external events or external datasets, what it costs — is in
`claude-plans/plandev/run-transfer-v0.md`; that document is discussion, this one is the contract.

A **run transfer** is one JSON file holding a simulation somebody else already performed: the model's
type declaration, the plan's directives, and the results (activity spans and resource profiles).
PlanDev imports it as a first-class run — it renders on the timeline and constraints check against
it. There is no live backend and no re-simulation.

The format says nothing about how the simulation was performed. A foreign framework, an offline batch
simulator, a headless PlanDev JAR run, an archived run kept as a regression fixture: all of them are
producers, and **nothing in the format, the importer, or the UI knows what any particular producer
is.** The file carries only PlanDev's own vocabulary — `ValueSchema`, `SerializedValue`,
`RealDynamics`, spans — and where behavior must differ per producer, the producer says so in the file
(see [Capabilities](#capabilities)).

| | |
|---|---|
| Schema | [`run-transfer.v1.schema.json`](run-transfer.v1.schema.json) — JSON Schema **draft-07** |
| Reference producer | [`writer.py`](writer.py) — stdlib only, depends on nothing else in this repo |
| Fixtures | [`fixtures/`](fixtures/) — one valid file, 22 invalid ones, each filed under the layer that should refuse it |
| Tests | [`test_writer.py`](test_writer.py) (stdlib), [`test_run_transfer.py`](test_run_transfer.py) (needs `jsonschema`) |

**This directory is self-contained.** Nothing in it depends on a live model backend, on a running
adapter, or on any other part of this repository — a producer can copy `writer.py` next to their own
code and be done.

---

## 1. The envelope

```jsonc
{
  "version": "1",
  "kind": "plandev-run",

  "model":   { /* §3 — omit to attach to an existing model by id */ },
  "plan":    { /* §4 — required */ },
  "results": { /* §5 — omit for a plain plan import */ }
}
```

### `kind`

MUST be exactly `"plandev-run"`. Any other value is refused outright, not sniffed.

A file with **no `kind` at all** is a legacy `plan.json` (a bare `PlanTransfer`) and is not a run
transfer; it goes down the existing plan-import path unchanged. That is the whole detection rule —
readers MUST NOT guess a run transfer from the presence of `results` or `model`, because then a
truncated run file would be indistinguishable from an old plan export and would import as a silent
partial.

### `version`

A **major only**: `"1"`, `"2"`. A reader MUST refuse a version it does not know, naming the version it
got and the ones it supports. It MUST NOT best-effort parse an unknown version — a half-understood run
lands in the database looking fine, which is worse than a rejected one.

- **Additive optional fields do not bump the version.** Anything that changes the meaning of an
  existing field, or adds a required one, does.
- Readers MUST NOT reject a file for carrying an unrecognized member. They SHOULD report unrecognized
  members of the envelope, `model`, `plan`, `results`, and each activity and span as a **warning**,
  because a typo (`resultss`) that silently downgrades a run to a plan is the failure mode this
  catches. The schema therefore does not set `additionalProperties: false` anywhere.
- **The next bump is already scheduled.** `results` moves to time-major NDJSON with the streaming work
  (see `external-model-streaming-results-plan.md`); that is `version: "2"`, and both should be accepted
  for a transition period. See [§7](#7-the-known-expiry-of-results).

Note the `plan` member carries **its own** `version: "2"`, which is the `PlanTransfer` version and is
independent of the envelope's. A run transfer's `plan` member *is* a plan.json.

---

## 2. Conventions that apply throughout

These are inherited from the formats this one embeds, and a producer that gets them wrong produces a
file that parses and then means something else.

| | |
|---|---|
| **Durations and offsets in `results`** | integer **microseconds**. Never a string, never seconds. |
| **`start_offset` / `duration` in `plan`** | Postgres interval literals — `[-][N day[s] ]HH:MM:SS[.ffffff]` — matching `PlanTransfer` v2. `start_offset` may be negative (an activity anchored before its anchor's end). |
| **`plan.start_time`** | ISO **calendar** date-time with a literal `+00:00` suffix. A `Z` breaks the UI, which strips exactly that suffix. |
| **`results.startTime`** | **DAY-OF-YEAR**: `uuuu-DDDTHH:MM:SS[.ffffff]`, e.g. `2026-001T00:00:00`. This is what `gov.nasa.ammos.plandev.types.Timestamp` parses; a calendar date here is a parse failure. **Yes, the two timestamps in one file use different calendars.** That asymmetry is inherited, not chosen. |
| **`SerializedValue`** | raw untagged JSON. `4`, `"x"`, `true`, `[…]`, `{…}`, `null`. |
| **Profile segments** | lie **consecutively from offset 0**. A segment's `duration` is its extent, not a timestamp. |
| **A segment with no `dynamics`** | a **gap** — "this resource has no value here". Legitimate; not a violation. |
| **`rate` on a real segment** | per **second**. |
| **A span with no `duration`** | was still running when the simulation ended → stored as an **unfinished** activity. Omit the field; do not send `null`. |
| **A span with a `parentId`** | a decomposition or dispatched child, and it carries **no** `directiveLocalId`. |
| **Arrayed resources** | flatten to dotted names (`PositionVector.x`). |
| **Absent vs. null** | `parentId`, `duration`, `directiveLocalId` and `computedAttributes` are **omitted** when they do not apply. An explicit `null` is a parse failure, because merlin reads them with `optionalField` rather than `nullableP`. `anchor_id` is the exception: it is nullable, as in `PlanTransfer`. |

---

## 3. `model` — the type declaration

Omit this member to attach the run to a mission model that already exists (by id, as a form field,
exactly as `importPlan` works today). Include it and the importer creates a new model with
`model_type = 'declared'` and `jar_id = null`: the types are *declared* to PlanDev rather than derived
from a JAR or introspected from a live backend, and there is no simulator behind it.

```jsonc
"model": {
  "mission": "…", "name": "…", "version": "…", "description": "…",

  "activityTypes": [{
    "name": "Observe",
    "parameters": [ { "name": "target", "schema": {"type": "string"} } ],   // ORDER IS LOAD-BEARING
    "requiredParameters": ["target"],
    "computedAttributesSchema": { "type": "struct", "items": {} },         // not optional
    "subsystem": "payload",                                                // optional
    "description": "…"                                                     // optional
  }],

  "resourceTypes": [ { "name": "/battery/soc", "schema": {"type": "real"} } ],
  "parameters":    [ { "name": "initialSoc",   "schema": {"type": "real"} } ],  // sim config; ORDERED

  "capabilities": { "simulation": { "supported": false, "reason": "…" } }
}
```

This is the payload of the `registerModelTypes` Hasura action, unchanged.

**Parameter order is load-bearing** — for activity parameters and for sim-config `parameters` alike.
merlin assigns each parameter an `order` from its index, persists it, reads activity types back sorted
by it, and plandev-ui lays the argument form out in that order. Reordering a declaration is a real
change; sorting the array is a bug.

**`computedAttributesSchema` is required.** A model that computes nothing declares a closed empty
struct, `{"type":"struct","items":{}}`. It is not optional because the gate holds every finished span's
computed attributes to it, and a model that emits attributes it never declared is exactly what that
check exists to catch.

### `ValueSchema`

Recursive and tagged on `type`. The reference implementation is `ValueSchemaJsonParser`.

```jsonc
{"type": "real"} | {"type": "int"} | {"type": "boolean"}
{"type": "string"} | {"type": "duration"} | {"type": "path"}

{"type": "series", "items": <ValueSchema>}
{"type": "struct", "items": {"<field>": <ValueSchema>, …}}
{"type": "variant", "variants": [{"key": "X", "label": "X band"}, …]}
```

Any of them may carry `"metadata": {"<key>": <SerializedValue>}`.

A `duration` value crosses the wire as **whole microseconds** — an integer, not a string.
A `variant` value crosses as a **string** matching a variant's `key` or its `label`.

This is the single most error-prone thing a producer writes, which is why the JSON Schema encodes it
in full. Validate against the schema before writing a file.

### Capabilities

What PlanDev may *do* with this model, as opposed to what the model is. An object keyed by capability
name; each value is an object with at least `supported`, **never a bare boolean** — an unsupported
capability is exactly the case that needs somewhere to put its explanation. **An absent capability
means unsupported.**

| key | meaning |
|---|---|
| `simulation` | PlanDev may run this model. For a declared model this is `false`: nothing exists to run. |
| `plandevScheduling` | PlanDev's scheduler may place activities in plans using this model. |
| `planImport` | a backend can read its framework's native plan format. Not applicable without a live backend. |

An unsupported capability MUST carry a `reason`, and **that string is what the user sees.** It is the
only reason plandev-ui can say "simulation is unavailable for this model because …" without containing
a branch that names a producer. Write a sentence a planner can act on.

---

## 4. `plan` — the directives

A `PlanTransfer` v2 document with two additions:

1. **every activity carries a `localId`**, a string unique within the file;
2. **`anchor_id` refers to a `localId`**, not to a numeric id.

```jsonc
"plan": {
  "version": "2",
  "name": "Recorded run",
  "start_time": "2026-01-01T00:00:00+00:00",
  "duration": "01:00:00",
  "simulation_arguments": { "initialSoc": 0.85 },
  "activities": [{
    "localId": "a1",
    "type": "Observe",
    "start_offset": "00:00:00",
    "arguments": { "target": "Europa" },
    "anchor_id": null,               // or the localId of another activity
    "anchored_to_start": true,
    "name": "Observe Europa",        // optional; defaults to the localId
    "metadata": {},                  // optional; defaults to {}
    "tags": []                       // optional
  }],
  "tags": []
}
```

An `id` member on an activity is permitted, so a plain plan export round-trips, and **ignored**:
`localId` is the keyspace.

### The `localId` contract

This is the one obligation on a producer that has no analogue in the existing formats, and it exists
because of a specific constraint: `ExternalResultsGate` requires every span's `directiveId` to be one
merlin actually knows about, but **Postgres assigns directive ids on insert**. A file cannot know them.

> **Contract on the writer.** Every directive carries a `localId` unique within the file. Every span
> that belongs to a directive references it by that `localId`. Anchors use the same keyspace.

The importer inserts the directives, builds `localId → directive id`, and rewrites span references and
anchors through that map before ingesting results. This also keeps the file self-contained and
re-importable: nothing in it refers to a database that may not exist any more.

Note the existing gateway `/importPlan` remaps anchors **by array position**; `localId` supersedes that
here rather than inheriting its fragility.

---

## 5. `results` — the recorded simulation

Omit for a plain plan import. The shape is **byte-identical** to what
`ingestExternalSimulationResults` parses today — see [§7](#7-the-known-expiry-of-results) for why that
is deliberate and what replaces it.

```jsonc
"results": {
  "startTime": "2026-001T00:00:00",     // DAY-OF-YEAR (§2)
  "duration": 3600000000,               // microseconds

  "profiles": {
    "/battery/soc": {
      "type": "real",
      "schema": {"type": "real"},
      "segments": [ {"duration": 1800000000, "dynamics": {"initial": 0.85, "rate": -0.00002}} ]
    },
    "/comm/mode": {
      "type": "discrete",
      "schema": {"type": "variant", "variants": [{"key": "IDLE", "label": "Idle"}]},
      "segments": [ {"duration": 600000000, "dynamics": "IDLE"},
                    {"duration": 300000000} ]                     // a gap
    }
  },

  "spans": [
    {"spanId": 1, "type": "Observe", "startOffset": 0, "duration": 1800000000,
     "directiveLocalId": "a1", "arguments": {"target": "Europa"},
     "computedAttributes": {"framesCaptured": 12}},
    {"spanId": 2, "parentId": 1, "type": "Slew", "startOffset": 0, "duration": 300000000,
     "arguments": {"angleDeg": 42.5}, "computedAttributes": {}},
    {"spanId": 3, "type": "Downlink", "startOffset": 2100000000,
     "directiveLocalId": "a2", "arguments": {"rateKbps": 512.0}}  // unfinished: no duration
  ]
}
```

`spanId` and `parentId` are the file's own span keyspace — integers, unique within the file, with no
relationship to anything in the database.

**There are no volume caps.** A legitimate run may produce an enormous number of spans and segments.

---

## 6. Two layers: the schema checks shape, the gate decides admissibility

A producer will hit both, and the division is deliberate rather than incidental.

**The JSON Schema owns shape and syntax** — the things merlin's parsers and Postgres consume before
any model is in view: required members, primitive types, the `ValueSchema` tagged union, the two
timestamp formats, interval literals, `null` where a field must be omitted, an unsupported capability
with no `reason`.

**`ExternalResultsGate` owns admissibility against the declared model** — everything that requires
knowing what the model declared. It runs in `reject` mode and it is the authority; nothing downstream
re-checks the content, and profiles and spans otherwise land in Postgres verbatim.

- **Resources** must be registered, with the schema that was registered (schema drift is rejected).
- **Activity types** on spans must be registered.
- **Arguments** must fit the declared parameters, recursively; **computed attributes** must fit the
  declared schema (finished spans only); required parameters must be present.
- **`directiveId`** must resolve to a directive in this plan.
- **Structure** — no duplicate span ids, parents resolve within the result, no parent cycles, timing
  within the simulation window, no non-finite `RealDynamics`, no negative durations.
- **Names** — activity types and parameter names must match `[A-Za-z_$][A-Za-z0-9_$]{0,127}`, because
  they become bare TypeScript identifiers in the generated typings and an illegal character produces
  code that does not compile. Resource names only need to be non-control characters, ≤255: they are
  always emitted quoted, and real adaptations use spaces and dots.

**Name legality is the gate's rule, and the schema deliberately does not duplicate it.** One authority
per rule, and the gate owns the message that explains the consequence.

A third, thinner layer sits between them: the **importer** resolves the file's own cross-references —
an unknown `directiveLocalId`, an anchor pointing at nothing, a duplicated `localId` — and refuses
before anything is written.

The fixtures are labelled by layer for exactly this reason, and
`test_run_transfer.py` asserts that **the schema accepts every gate-layer and
importer-layer fixture.** That assertion is what keeps the division real rather than assumed: if the
schema quietly grows a rule the gate already owns, a gate fixture starts failing there.

---

## 7. The known expiry of `results`

`results` reuses today's **resource-major batch shape verbatim**, so v0 needs no new parsing code:
`HasuraParsers.externalSimulationResultsP` is the reader.

**This shape is slated to be replaced.** Per `external-model-streaming-results-plan.md` it becomes
time-major NDJSON records (`header` / `schema` / `real` / `discrete` / `span` / `end`), because
resource-major forecloses streaming. Accepting it now means producers migrate **once, with the rest of
the wire, in streaming Phase 2** — not that a second format is invented here that diverges
immediately. That will be `version: "2"`.

Recorded here so it is a decision rather than a surprise: anyone writing a producer should know the
migration is coming and is shared with the live adapters.

---

## 8. Writing a producer

The contract is three things, and it says nothing about how the simulation was performed:

1. **Declare the types** — activity types, resource types, sim-config parameters, as `ValueSchema`.
2. **Emit the directives** the run was performed against, each with a `localId`.
3. **Emit the results** — resource profiles and activity spans, spans referencing directives by
   `localId`.

Validate before you ship the file:

```python
import json, jsonschema
schema = json.load(open("run-transfer.v1.schema.json"))
jsonschema.Draft7Validator(schema).validate(json.load(open("my.run.json")))
```

### The writer

[`writer.py`](writer.py) is the reference implementation, and it is **stdlib only and standalone**
— a producer is the party most likely to live outside PlanDev, so the module they copy has to run
where they are. Its inputs are what a simulator already has: a declaration, the directives, and the
profiles and spans it produced.

```python
import writer as run_transfer

document = run_transfer.RunTransfer(
    declaration=declaration,                      # a ModelDeclaration, or anything shaped like one
    mission="Demo",
    plan_name="Recorded run", plan_start=start, plan_duration_us=3600 * 1_000_000,
    directives=[run_transfer.RunDirective("a1", "Observe", arguments={"target": "Europa"})],
    response={"realProfiles": ..., "discreteProfiles": ..., "spans": [...]},
).to_json()

problems = run_transfer.run_problems(document)    # PlanDev's ingest rules, before the upload
run_transfer.write_run(document, "my.run.json")
```

`declaration` is duck-typed: `ModelDeclaration` is here for producers who have nothing else, and any
object carrying the same attributes works instead — a backend that already models its own
declaration passes that rather than rebuilding it.

`run_problems` applies `ExternalResultsGate`'s closed-world rules plus the importer's
cross-references, so a file it says nothing about is one PlanDev will accept — everything left is
about PlanDev's own state (whether that model exists, whether the plan name is taken) and needs a
server to answer. `parse_run` is the inverse of `to_json`, which is what lets the round trip be
tested rather than asserted.

Two things the writer decides on a producer's behalf, both worth knowing:

- **Capabilities are not inherited from a live declaration.** `planImport` and `plandevScheduling`
  describe what a *reachable backend* can do, and there is no backend behind an imported run, so
  carrying them across would publish an offer PlanDev cannot meet. The only capability a run file
  asserts is that the model cannot be simulated. Pass `capabilities=` to say otherwise.
- **The declaration digest covers exactly what the file carries.** `declaration_digest` is what
  PlanDev stores and what decides whether re-importing a run reuses the model it already created.
  It deliberately does NOT match any attestation a live backend publishes about itself: such a hash
  includes each parameter's DEFAULT, and a run file has no field for defaults, so no reader of the
  file could ever reproduce it.

  It has a second implementation, in TypeScript, inside the gateway. The two agree byte for byte,
  and a test on each side pins the same constant against the same fixture — because a disagreement
  does not fail, it quietly creates a second model beside the first.

Two portability notes that cost real time to rediscover:

- **A non-finite value cannot be written as `NaN` or `Infinity`.** Python's `json` emits and accepts
  those tokens; `JSON.parse` and ajv reject them. Use `1e400`, which is valid JSON and parses to
  `+Infinity` as a double in Java, Python and JavaScript alike.

- **An intermediary must forward these bytes, not round-trip them.** Verified the hard way: a
  non-finite value survives only if it reaches merlin as the literal `1e400`. Parse this file and
  re-serialize it and the value is destroyed *before* the gate can object —

  | re-serializer | what `1e400` becomes | what happens |
  |---|---|---|
  | Python `json.dumps` | the token `Infinity` | rejected as malformed JSON by Hasura and by ajv |
  | JS `JSON.stringify` | **`null`** | silently becomes a profile **gap**: a wrong run, stored, with no complaint |

  The second row is the dangerous one, and it is why the gate's non-finite check is not sufficient on
  its own: anything sitting between a producer and merlin has to preserve the number, or the check it
  exists to reach is never reached. Sent as literal bytes, the gate answers
  `resource '/battery/soc' has a non-finite rate (Infinity)`.
- **A NaN cannot be written at all.** `1e400` is an *infinity*, which is a different number, so the
  writer refuses a NaN rather than rounding one to the other. A model that produces NaN has a
  modelling problem the format cannot carry across.

- **Draft-07, not 2020-12.** The gateway's `ajv` is pinned at `^6`, which is draft-07. Authoring
  2020-12 and discovering the mismatch at runtime is a real morning lost.

## 9. Where these files live

The canonical spec, schema, fixtures and reference producer are here, in the examples repo, because
the contract is producer-facing and a producer is the party most likely to be outside PlanDev.

The gateway vendors a copy of the schema — it compiles it with ajv at startup and enforces it at
upload — generated by `scripts/sync-run-transfer-schema.mjs`, whose `--check` mode fails if the copy
has drifted from this one.

Nothing here depends on the external-model-backend work: this directory has no live backend, no
adapter and no HTTP in it, and `writer.py` imports nothing but the standard library. A producer that
*is* a live backend can of course use both, but it does not have to.
