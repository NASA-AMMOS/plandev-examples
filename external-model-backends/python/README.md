# Python external-model backend (battery demo)

A minimal **pure-Python** external-model backend for PlanDev — proof that the `external` wire
contract is language-neutral (it speaks exactly the same protocol as the Blackbird adapter, and
PlanDev/Merlin needs zero new code to drive it).

It is an **Archetype-A "pure simulator"**: `simulate(directives) -> profiles + spans`, with no
internal scheduling. `py_model_server.py` is **stdlib-only** — no dependencies.

## The model — a toy spacecraft battery

| | |
|---|---|
| **Resources** | `SoC` (real, **linear** — a genuine rate-based profile), `Mode` (variant: `Idle`/`Charging`/`Discharging`), `Cycles` (int) |
| **Activities** | `Charge(duration, rate=1.0/s)`, `Discharge(duration, load=2.0/s)` |

`SoC` demonstrates real **piecewise-linear** dynamics (`{initial, rate}` per second), and `validate`
shows per-parameter error attribution (`subjects: ["rate"]`) that renders inline on the field in the
UI — something Blackbird cannot do, since its validation errors are whole-activity.

Concurrent activities **superpose**: a `Charge` overlapping a `Discharge` yields one segment at the
summed rate for the overlap. Profiles are built from a breakpoint timeline of absolute offsets rather
than a running cursor, so cumulative segment offsets always equal wall-clock offsets, and the result
does not depend on the order directives arrive in.

Everything is **clamped to the simulation window**: a directive starting past the end contributes
nothing, one extending past the end is truncated in its profile, and the emitted segments always sum
to exactly the simulation duration. Its span is reported **unfinished** rather than clamped — both
`duration` and `computedAttributes` are omitted, which is how merlin tells a still-running activity
from a completed one. Clamping the span instead would claim it ended at the window edge, which is a
different and false statement.

`validate` is **authoritative**: merlin delegates argument checking to the backend for external
models, so this typechecks every argument against its declared `ValueSchema`. Anything it passes is
something `simulate` accepts and the ingest gate will accept back.

## Build & run

```bash
docker build -t plandev/python-adapter external-model-backends/python
docker run --rm -p 5002:5002 plandev/python-adapter
```

Or run it directly (no Docker, no dependencies):

```bash
python3 external-model-backends/python/py_model_server.py 5002
```

Then it serves the four wire-contract endpoints on `:5002`:

```bash
curl -s localhost:5002/models
curl -s localhost:5002/introspect
curl -s -X POST localhost:5002/simulate \
  -d '{"planStart":"2020-01-01T00:00:00Z","duration":600000000,"configuration":{},
       "directives":[{"id":1,"type":"Charge","startOffset":0,"arguments":{"duration":120000000}}]}'
curl -s -X POST localhost:5002/validate \
  -d '{"activities":[{"type":"Charge","arguments":{"rate":-1}}]}'
```

See the top-level [external-model-backends/README.md](../README.md) for the full plug-and-play
flow (wiring PlanDev's `EXTERNAL_MODEL_BACKENDS`, discovery, registration) and the wire contract.

## Tests

```bash
cd external-model-backends/python
python3 test_py_model_server.py        # offline: no server, no Docker, no network
python3 test_py_model_server.py -v
```

`test_py_model_server.py` calls the module's functions directly — server startup is behind
`if __name__ == "__main__"`, so importing it binds no socket. The suite pins the behaviours that
break *silently*: superposition and order-independence, agreement between a span's `startOffset` and
where its rate change lands in the profile, window clamping, the finished/unfinished span
distinction, and the `ValueSchema` typechecker. CI runs it on every push and pull request
(`.github/workflows/external-model-backends.yml`).

## Use it as a template for your own model

This ~180-line file is the reference for writing a backend in **any** language. Implement the four
endpoints (`GET /models`, `GET /introspect`, `POST /simulate`, `POST /validate`) with the JSON
shapes documented in the top-level README, then point an `EXTERNAL_MODEL_BACKENDS` entry at it.
Edit the `MODEL` / `RESOURCE_TYPES` tables and the `simulate()` body to change the physics.
