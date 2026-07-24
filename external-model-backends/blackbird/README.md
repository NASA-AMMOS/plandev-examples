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

## Wire contract & full PlanDev flow

The four endpoints, their JSON shapes, the `EXTERNAL_MODEL_BACKENDS` wiring, and the
discovery/registration flow are documented once in the **[top-level README](../README.md)**.

## Known gaps

- **`map<string,comparable>` params** don't map cleanly onto `ValueSchema`; they register as
  `string`, so the UI can't offer the right editor.
- Blackbird validation errors are *whole-activity* (no per-parameter attribution), so their
  notices carry `subjects: []`.
- Determinism is assumed (`(config, directives) -> results`); nondeterministic models are
  unsupported for the edit -> re-sim -> re-ingest round-trip.
- SPICE-based models need the native lib mounted and kernels (`LOAD_KERNELS`) loaded.
