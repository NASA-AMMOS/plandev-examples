# External model backends

**Run a mission model PlanDev never compiled** — a foreign simulator that plugs in over HTTP as an
`external` backend. PlanDev owns the plan, directives, validation, scheduling UI, and
visualization; the backend owns the simulation. This directory has three runnable, plug-and-play
example backends:

| Backend | Dir | Port | What it is | Language |
|---|---|---|---|---|
| **Blackbird** | [`blackbird/`](blackbird/) | **5011** | Fronts the [Blackbird](https://github.com/nasa-jpl/Blackbird) Java simulator; serves the `powermodel` demo adaptation (multi-model capable) | Python + JVM |
| **Python** | [`python/`](python/) | **5002** | A small pure-Python toy spacecraft battery — proof the contract is language-neutral | Python (stdlib) |
| **Basilisk** | [`basilisk/`](basilisk/) | **5021** | A LEO spacecraft in [Basilisk](https://github.com/AVSLab/basilisk): SPICE ephemerides, eclipse geometry, solar array, battery, recorder, ground-station downlink | Python + C++ |

All three speak the **same language-neutral wire contract** (four HTTP endpoints, below). PlanDev/Merlin
needs zero per-framework code: a backend is just an adapter that conforms to the contract.

They are deliberately different in kind. Blackbird is a discrete-event engine in another JVM; the
Python model is a toy with no dependencies; Basilisk is a **fixed-step numerical integrator**, which
is the one that stresses a different part of the contract — see
[`basilisk/README.md`](basilisk/README.md). The half of each adapter that is not about its simulator
lives in one shared [`adapter_core.py`](adapter_core.py).

> These are demonstration/spike backends, not published/production components. They are **not**
> part of the Gradle mission-modeling learning path — the demo Blackbird `powermodel` is a Blackbird
> adaptation (built by its Dockerfile with `javac`), not a Merlin subproject, so this directory is
> intentionally decoupled from the repo's `settings.gradle` build.

## The plug-and-play flow

```
  1. run the backend container(s)          docker compose up --build
                    │  (in-cluster, on PlanDev's network; no host ports)
                    ▼
  2. point PlanDev at them                 merlin + workers env:
                    │                        EXTERNAL_MODEL_BACKENDS=[{name,url}, …]
                    │                        url = http://blackbird-adapter:5011
                    │
                    ▼
  3. discover models                       getExternalModelCatalog  → polls each backend GET /models
                    │
                    ▼
  4. register one in the UI                registerExternalModel(backend, modelKey, name, version)
                    │
                    ▼
  5. use it like any model                 build a plan → validate → Simulate → resource plots + spans
```

### 1. Run the backend container(s)

Adapters run **in-cluster**, joining PlanDev's own Docker network as peers of `aerie_merlin` and
`aerie_sequencing`. They are reached by **service name** and are deliberately **not published to the
host** — an adapter is an operator-run component inside the trust boundary, not a third-party
endpoint PlanDev calls out to. Plan data never leaves the cluster.

```bash
cd external-model-backends

# Point at your PlanDev deployment's network (find it with `docker network ls`):
export PLANDEV_NETWORK=plandev-dupe-1_default

# The Blackbird image needs a JNISpice jar in ./blackbird/vendor first — see blackbird/vendor/README.md.
# If your jar isn't the pinned v2022-05, override ONLY the filename:
#   export JNISPICE_JAR=JNISpice-N0067.jar
docker compose up --build            # all three backends
docker compose up --build python     # just the pure-Python one (no jar needed)
docker compose up --build basilisk   # real astrodynamics (no jar either; 1.3 GB image)
```

Building the Basilisk image needs egress to `naif.jpl.nasa.gov` **once**, to bake in ~128 MB of SPICE
kernels. After that it runs with no network of its own.

Or run any of them on its own — see [`blackbird/README.md`](blackbird/README.md),
[`python/README.md`](python/README.md) and [`basilisk/README.md`](basilisk/README.md). The Python
backend also runs with **no Docker and no
dependencies**: `python3 python/py_model_server.py 5002` — handy for hacking on an adapter, though
merlin must then reach it via `host.docker.internal`, which puts the adapter outside the cluster.
Prefer the in-cluster containers for anything but local development.

### 2. Point PlanDev at the backends

An **operator** declares a fixed set of *trusted* backends via merlin-server's
`EXTERNAL_MODEL_BACKENDS` environment variable — a JSON array of `{name, url}`, where `url` is the
backend's **base** URL (merlin appends `/models`, `/introspect`, `/simulate`, `/validate`). This is
the SSRF/trust boundary: **users never type URLs**; they pick a configured backend and a model it
discovers.

In PlanDev's `docker-compose.yml`, on the `aerie_merlin` service **and on every merlin worker**:

```yaml
environment:
  EXTERNAL_MODEL_BACKENDS: '[{"name":"blackbird-lab","url":"http://blackbird-adapter:5011"},{"name":"python-lab","url":"http://python-adapter:5002"},{"name":"basilisk-lab","url":"http://basilisk-adapter:5021"}]'
```

Because the adapters are on the same network, merlin reaches them by service name — no host
exposure, exactly like `http://aerie_sequencing:27184`.

> ⚠️ **Set this identically on merlin AND every `aerie_merlin_worker_*`.** merlin introspects
> (registration) while the *workers* simulate. If only merlin has the config, a model registers and
> shows its types correctly, then every simulation fails.

### 3. Discover models

With merlin restarted, the `getExternalModelCatalog` GraphQL query polls each configured backend's
`GET /models` and returns what's reachable:

```graphql
query { getExternalModelCatalog { backend reachable error models { key name version identityHash } } }
```

```jsonc
[ { "backend": "blackbird-lab", "reachable": true,
    "models": [ { "key": "powermodel", "name": "powermodel", "version": "1.0.0", "identityHash": "…" } ] },
  { "backend": "python-lab", "reachable": true,
    "models": [ { "key": "battery", "name": "battery", "version": "1.0.0", "identityHash": "…" } ] } ]
```

### 4. Register a discovered model

`registerExternalModel` creates a `mission_model` row (`model_type='external'`) that references the
trusted backend name + the discovered model key — no URL, no JAR upload:

```graphql
mutation {
  registerExternalModel(backend: "python-lab", modelKey: "battery", name: "Battery", version: "1.0.0") { modelId }
}
```

The model now appears in PlanDev's model list. Create a plan against it and the UI behaves exactly
like a JAR model: author directives, validate (delegated to the backend's `/validate`), hit
**Simulate** (drives the backend's `/simulate`), and results land as a first-class
`simulation_dataset` — resource plots, activity spans, constraints, scheduling surfaces.

## Wire contract

Four HTTP endpoints. Each addresses a model by `?model=<key>` (optional when a backend serves a
single model). Durations and offsets are **microsecond integers**; profile segments are laid
consecutively from offset 0; `SerializedValue` is raw JSON (untagged).

| Endpoint | Purpose |
|---|---|
| `GET /models` | **Discovery.** `{ models: [{key, name, version, identityHash}] }` |
| `GET\|POST /introspect?model=<key>` | Types. `{ activityTypes, resourceTypes, parameters, capabilities, identityHash }` |
| `POST /simulate?model=<key>` | Run. `{planStart, duration, configuration, directives[]}` → `{realProfiles, discreteProfiles, spans}` |
| `POST /validate?model=<key>` | Validate / effective args. `{activities[], effectiveOnly}` → `{results:[{valid, notices[], effectiveArguments}]}` |

**`POST /simulate`**

```jsonc
// request
{ "planStart": "2020-01-01T00:00:00Z", "duration": 7200000000,          // µs
  "configuration": { },
  "directives": [ { "id": 6, "type": "Charge", "startOffset": 0, "arguments": {"duration": 120000000} } ] }

// response — real profiles carry {initial, rate} dynamics (rate per second); discrete carry a raw value
{ "realProfiles":     { "<name>": { "schema": {"type":"real"}, "segments": [ {"duration": µs, "dynamics": {"initial": n, "rate": n}} ] } },
  "discreteProfiles": { "<name>": { "schema": {..}, "segments": [ {"duration": µs, "dynamics": <SerializedValue>} ] } },
  "spans": [ { "spanId": 1, "type": "..", "startOffset": µs, "duration": µs,
               "arguments": {..}, "parentId": <spanId|null>, "directiveId": <id|null> } ] }
```

- **Decomposition/dispatched** children carry `parentId` (their parent span) and `directiveId: null`.
- **`directiveId`** links a top-level span back to the PlanDev directive that produced it.
- **Arrayed resources** (Blackbird) flatten to dotted names (`PositionVector.x`).

**`capabilities`** — what PlanDev may *do* with this model, which its declared types cannot say.
Nothing in a list of activity types reveals whether the model places activities of its own during
simulation, so PlanDev cannot infer it and the backend has to state it.

```jsonc
{ "plandevScheduling": { "supported": false,
                         "reason": "This model schedules its own activities: ..." },
  "planImport":        { "supported": true,
                         "formats": [{"key":"blackbird-plan-json","label":"Blackbird plan",
                                      "extensions":[".plan.json"]}] } }
```

Every capability is an **object, never a bare boolean**, so an unsupported one has somewhere to carry
the backend's own explanation — which is what keeps plandev-ui free of any branch naming a particular
framework: it renders "unavailable because *&lt;the backend's sentence&gt;*". An **absent capability
means unsupported**, so a backend that declares nothing keeps today's behavior rather than silently
opting into a feature nobody verified. Merlin stores the object verbatim in
`mission_model.external_capabilities`, including names it has never heard of, so a backend can declare
something a newer UI understands and an older server will still carry it through.

`plandevScheduling` is the distinction between the two archetypes: a **pure simulator** (the Python
battery, Basilisk) maps directives to results and places nothing, so PlanDev's scheduler can drive it;
a **forward-dispatch framework** (Blackbird) places activities during its own run, so its schedule is
an output and running PlanDev's scheduler too would put two schedulers on one plan.

**`POST /validate`** — each activity yields `{valid, notices:[{subjects, message}], effectiveArguments}`.
`subjects` names the offending parameter(s) so the UI can render the error inline on that field
(the Python model does this; Blackbird's errors are whole-activity, so `subjects: []`).

The [`python/py_model_server.py`](python/py_model_server.py) file (~180 lines, stdlib-only) is the
readable reference implementation of all four endpoints.

## Add your own model

- **In any language** — stand up a service that implements the four endpoints above, add it to
  `EXTERNAL_MODEL_BACKENDS`, and register the models it discovers. Copy the Python backend as a
  starting template (edit its `MODEL` / `RESOURCE_TYPES` tables and `simulate()` body).
- **A Blackbird adaptation** — compile it against the Blackbird/jplTime classpath and add a
  `BB_MODELS` entry; see [`blackbird/README.md`](blackbird/README.md).

Every backend must honor the **determinism contract** (`(config, directives) -> results`, required
for the edit -> re-sim -> re-ingest loop) and the **type-fidelity limits** of `ValueSchema`.

## A note on jars

The Blackbird image builds Blackbird + jplTime **from source at build time** rather than committing
fat jars. The one artifact you must supply is **JNISpice** (a compile-time dependency of jplTime,
not on Maven Central and not redistributable here) — drop it into
[`blackbird/vendor/`](blackbird/vendor/README.md), which is git-ignored. No adapter jars are
committed to this repo.
