# Blackbird external-model backend

A generic, model-agnostic adapter that lets PlanDev run one **or many**
[Blackbird](https://github.com/nasa-jpl/Blackbird) mission models as a *foreign*
(`model_type = 'external'`) backend — no Merlin JAR, no hand-port to `merlin-framework`. PlanDev
owns the plan, directives, and UI; Blackbird does the simulation.

> Status: spike / demonstration. It exercises the real `external` backend seam end-to-end
> (discovery -> registration -> validation -> the native Simulate route -> resource plots, spans,
> constraints), but is not production-hardened.

```
   PlanDev UI ──Simulate──▶ merlin-server ──HTTP POST /simulate──▶ bb_service.py ──▶ Blackbird (JVM)
        ▲                   (model_type='external')                (this adapter)          │
        └──────── resource plots / spans / constraints ◀── native simulation_dataset ◀─────┘
```

## Files

- **`bb_service.py`** — the multi-model HTTP backend PlanDev calls. Stdlib-only. Speaks the four
  wire-contract endpoints (`/models`, `/introspect`, `/simulate`, `/validate`); each addresses a
  model by `?model=<key>`. Configured with `BB_MODELS` (a JSON map of `modelKey -> classpath`).
- **`bb_import.py`** — offline converter that turns an existing Blackbird `.plan.json` into a
  PlanDev `PlanTransfer` file for the stock **Import Plan** button (see below). Stdlib-only;
  needs no PlanDev changes. `test_bb_import.py` covers it.
- **`bb_adapter.py`** — *legacy / optional* one-shot "push" tool that runs Blackbird once and
  pushes type metadata + a run's results straight into PlanDev via Hasura actions
  (`registerModelTypes` / `ingestExternalSimulationResults`). Superseded by the
  discovery+registration flow (`getExternalModelCatalog` / `registerExternalModel`) documented in
  the [top-level README](../README.md). Needs `pip install requests`; not used by the image.
- **`powermodel/`** — the demo Blackbird adaptation the image serves (see below).

## The demo model — `powermodel`

A small Blackbird power/downlink adaptation under `powermodel/src/gov/nasa/jpl/powerModel/`:

| | |
|---|---|
| **Resources** | `BatterySoC` (real %), `DataBuffer` (int Mbit), `SolarPower` (real W), `Mode` (variant) |
| **Activities** | `CollectScience`, `Downlink`, `Recharge`, `SciencePass` (decomposes into collect+downlink), `AutoRecharge` (a forward-dispatch **scheduler** that spawns `Recharge` when `BatterySoC` drops below 30%) |

`SciencePass` exercises **decomposition** (children come back as child spans) and `AutoRecharge`
exercises **Archetype-B forward dispatch** (activities the model places during the sim return as
spans with no `directiveId`).

## Build & run

Blackbird and jplTime are cloned and built at image-build time. JNISpice is a compile-time
dependency of jplTime and is **not** on Maven Central — drop `JNISpice-v2022-05.jar` into
[`vendor/`](vendor/README.md) first.

```bash
# 1. provide the JNISpice jar (see vendor/README.md)
cp /path/to/JNISpice-v2022-05.jar external-model-backends/blackbird/vendor/

# 2. build + run (listens on :5011)
docker build -t plandev/blackbird-adapter external-model-backends/blackbird
docker run --rm -p 5011:5011 plandev/blackbird-adapter
```

On startup it logs, e.g. `Blackbird multi-model backend on :5011  models: powermodel(5 acts/4 res, id=…)`.

### Run without Docker (dev)

```bash
export BB_MODELS='{"powermodel":"<blackbird classes>:<blackbird deps>/*:<powermodel classes>"}'
export JPLTIME_LIB="<dir with libJNISpice.so|.jnilib>"   # only if the model uses SPICE
python3 bb_service.py 5011
```

## Serving your own Blackbird adaptation

Each `BB_MODELS` entry is `modelKey -> classpath`, where the classpath is **Blackbird core + its
deps + exactly one adaptation's compiled classes**. To add a model, compile your adaptation against
the Blackbird/jplTime classpath (see the `javac` step in the `Dockerfile`) and add an entry:

```json
{"powermodel":"/opt/blackbird/classes:/opt/blackbird/lib/*:/opt/blackbird/powermodel",
 "mymodel":"/opt/blackbird/classes:/opt/blackbird/lib/*:/opt/blackbird/mymodel"}
```

Restart the container; the new model shows up in `GET /models` and PlanDev's catalog.

### Caveat: Blackbird's bundled example activities

`/opt/blackbird/classes` (Blackbird's `target/classes`) contains Blackbird's own bundled
**example adaptation** (`ActivityOne`, `ActivityTwo`, …). Blackbird discovers all `Activity`
subclasses on the classpath, so any model whose classpath includes `/opt/blackbird/classes` will
expose those example activities **in addition** to your adaptation's. For the demo this is
harmless. To serve a single clean model, build Blackbird without its example adaptation (or strip
that package from the classes dir) so the classpath carries only the framework + your adaptation.

## Importing an existing Blackbird plan — `bb_import.py`

The adapter above lets PlanDev *simulate* a Blackbird model, but a team that already has Blackbird
`.plan.json` files still needs to get those activities into a plan. `bb_import.py` converts one
into a PlanDev `PlanTransfer` file, which you then feed to the stock **Import Plan** button on the
plans page (or `POST /uploadActivities` on the gateway). No PlanDev-side changes.

```bash
python3 bb_import.py mission.plan.json \
    --introspect-url http://blackbird-adapter:5011 --model powermodel \
    -o mission.plandev.json --report mission.report.json
```

Activity types and parameter schemas have to come from the model, so pick one source:

| flag | how it introspects |
|---|---|
| `--introspect-url URL` | `GET <URL>/introspect` on a running `bb_service` (plus one `/validate?effectiveOnly` call to recover parameter defaults, which `/introspect` does not carry) |
| `--classpath CP` | runs `load_model` locally — needs `java` and the model on disk |

Both produce byte-identical output. `--model` is optional when the backend serves one model.
Other flags: `--plan-name`, `--plan-start`, `--duration-days`, and `-` in place of the input path
to read the plan from stdin.

### You must type the plan window into the import dialog

A Blackbird plan file is exactly `{"activities": [...]}` — **no header**, so no plan start, no
duration, and no model reference. The converter derives a window from the activities and prints it:

```
bb_import: 11 source activities -> 7 directives, 4 dropped, 1 warning(s)
  the plan file has no header, so ENTER THESE IN THE IMPORT DIALOG:
    plan start : 2024-01-01T00:00:00Z
    duration   : 1 days 00:00:00
```

The plan start is the first activity's start **floored to the UTC day**, which keeps every offset
non-negative and leaves headroom ahead of the first activity. The gateway takes the real name,
model, start and duration from the import form, not from the file — the file carries them only
because PlanDev's UI prefills that form from them.

### What it drops, and why that matters

Blackbird stores the **decomposition tree flattened alongside** the top-level activities, marked
only by `parent`. Only `parent == null` activities become PlanDev directives; the rest are spans
that re-simulation regenerates, so importing them would double-count. Nothing downstream catches
that — the plan loads, validates and simulates, just with duplicated activities — and no heuristic
substitutes for the rule: in the reference fixture `ActivityOne` appears both as a directive and as
a decomposition child, and one child starts at the same instant as its parent.

Values are re-encoded to target the model's `ValueSchema` (the inverse of `fmt_param`): a duration
becomes integer microseconds, a `map<k, v>` becomes PlanDev's series of `{key, value}` structs, and
a `time` is carried **verbatim** in Blackbird's day-of-year form — normalizing it to ISO-8601 would
produce something Blackbird itself rejects on the way back in. Every activity keeps its Blackbird
uuid in `metadata.blackbirdId`.

The report — printed to stderr, and written as JSON with `--report` — lists every dropped activity
and warns about anything that survived but changed meaning: an absolute `time` parameter, a
parameter the model no longer declares, one filled in from a default, a value that would not
coerce, a duplicate or dangling uuid, or an activity outside the derived window.

```bash
python3 test_bb_import.py        # offline: no adapter, no JVM, no network
```

The tests run against `fixtures/powermodel-export.plan.json`, a real Blackbird export (see
[`fixtures/README.md`](fixtures/README.md)). A live round-trip test feeds the converted directives
back to `/simulate` and asserts the original 11 spans come out; it skips unless a backend is
reachable at `$BB_ADAPTER_URL` (default `http://localhost:5011`).

## Wire contract & full PlanDev flow

The four endpoints, their JSON shapes, the `EXTERNAL_MODEL_BACKENDS` wiring, and the
discovery/registration flow are documented once in the **[top-level README](../README.md)**.

## Known gaps

- **Absolute `time` params** register as `string`. PlanDev has no absolute-time schema, so the value
  is carried verbatim in Blackbird's UTC day-of-year form -- and it does *not* move if the plan start
  changes, unlike the activity's own start.
- **Custom `ConvertableFromString` params** register as `string` and round-trip as their `toString()`,
  so the UI cannot offer a structured editor.
- **Simulation configuration is a no-op end to end.** The wire carries `configuration` and the adapter
  accepts it, but nothing applies it: Blackbird config lives in `SET_PARAMETER` commands, not the plan
  file, and `/introspect` reports no model parameters.
- Blackbird validation errors are *whole-activity* (no per-parameter attribution), so their
  notices carry `subjects: []` -- which plandev-ui currently drops, making them invisible.
- Determinism is assumed (`(config, directives) -> results`); nondeterministic models are
  unsupported for the edit -> re-sim -> re-ingest round-trip.
- SPICE-based models need the native lib mounted and kernels (`LOAD_KERNELS`) loaded.
