# Parakeet backend — a candidate engine, evaluated through the contract

[Parakeet](https://github.com/DavidLegg/Parakeet) is a Kotlin modeling and simulation system "based
on Aerie" — cells, tasks, conditions and effects, rebuilt with different engineering priorities. It
is not a foreign simulator someone needs to plan with. It is a **candidate replacement for merlin's
own engine**, and this adapter exists so it can be tried against real PlanDev plans without touching
merlin at all.

That is a use for the external-model contract that was not the reason it was built: **an evaluation
harness for a new engine.** Write an adapter, register the model, run real plans, compare against a
JAR model on the same plan. No engine surgery, no commitment, no merlin changes.

## Why Parakeet is interesting

Merlin's tasks are threads, and threads cannot be snapshotted — which is why merlin's checkpointing
is limited and `CheckpointSimulationDriver` is as awkward as it is. Parakeet's tasks are **Kotlin
coroutines**, compiler-split into continuations, which *can* be serialized. Save/restore then falls
out of the execution model rather than being bolted on, and it is stated as a law:

> running `S` to `T` ≡ running `S` to `T'`, saving a fincon, restoring, running to `T`, concatenating

with honest preconditions: all mutable state in cells, tasks deterministic, results reported only
through the results channel. It also keeps **constant memory with respect to plan length** — no
history retained.

Those two properties are exactly the ones whose absence made scheduling against an external model
expensive: a scheduler that can restore a checkpoint does not pay a full re-simulation per placement.

## The model: `recorder`

Small on purpose. A solid-state recorder and its downlink.

| Activity | Arguments | Span duration |
|---|---|---|
| `Collect` | `duration`, `rateMbps` (120) | as given |
| `Downlink` | **none** | **emergent — computed by simulating** |

`Downlink` is the whole reason this backend exists. It has **no duration parameter**, and how long
it takes is a function of how full the recorder was, which is a function of every `Collect` before
it and of whether an earlier downlink already drained some. Every other adapter here is handed a
duration and hands the same number back. The original architecture research flagged this shape
(risk **M3**) as the case a plan cannot be pre-flattened around.

Resources: `/recorder/levelMb`, `/recorder/droppedMb` (real values), `/recorder/collections` (int),
`/recorder/mode` (`Idle | Recording | Downlinking`).

## Two things building it taught, both the hard way

**Every profile here is a staircase, including the numeric ones.** A Parakeet discrete cell holds a
constant between writes. The first version reported the recorder level as a *real* profile and
PlanDev drew a straight line between samples — so the stored level sloped gently downward for twenty
minutes before a downlink had started, at a rate belonging to no part of the model. The endpoints
were right and everything between them was invented. Adding a sample at the drain's start does not
help: writing a cell its own value is not an effect, so Parakeet reports nothing. The fix is to say
what is true — declared with a `real` **schema** (the values are reals), emitted as **discrete** (the
shape is a staircase). Blackbird's constant reals reach PlanDev the same way.

**Concurrent tasks need effects, not read-modify-write.** Parakeet runs everything scheduled at the
same instant as one batch, and within a batch no task observes another's effects. Two collections
ending together each read the same level, each computed an absolute total, and the second `set`
erased the first — and both looked like they had worked. `increase`/`decrease` are effects the cell
merges, which is the entire reason a cell-based engine has effects rather than setters. A test pins
it: the *same* downlink directive must take longer when more was collected before it.

## What it needed from the host

`pk_service.py` is 60 lines with no subclass and no protocol code — third language through
`ExecBackend`, after Rust. Two things had to change in `adapter_core` to get there, and both were
gaps rather than preferences:

- **`ExecBackend` now accepts `samples`, not just `segments`.** A simulator naturally produces a
  value at a time; segments are PlanDev's shape. That conversion is generic and the host already
  owned it — NeXosim had to reimplement it in Rust because this hook did not exist.
- **A profile's `schema` is filled from the declaration when the model omits one.** A model
  restating a schema it already declared is a second copy free to drift, and merlin dies on a
  missing one with a `NullPointerException` naming neither resource nor model.

## Run it

```bash
export PLANDEV_NETWORK=plandev-dupe-1_default      # docker network ls
docker compose up --build parakeet                 # from external-model-backends/
```

Then add it to `EXTERNAL_MODEL_BACKENDS` on merlin **and every merlin worker**:

```json
{"name":"parakeet-lab","url":"http://parakeet-adapter:5041"}
```

Parakeet publishes no Maven artifact and has no releases, so the Dockerfile clones it and **pins a
commit**. A floating clone would let the identity hash merlin attests change with someone else's
push — the exact drift the attestation exists to catch.

## Tests

```bash
gradle installDist && python3 test_pk_service.py -v
```

13 tests, driving the real Kotlin binary over the real stdio protocol. They skip cleanly when the
model has not been built.

## Verified live

Registered against a running PlanDev and simulated with `EXTERNAL_INGEST_GATE=reject`:

```
Collect   start=00:10:00  dur=00:05:00    {}
Collect   start=00:30:00  dur=00:10:00    {}
Downlink  start=01:00:00  dur=00:03:24.8  {"drainSeconds": 204.8}
Downlink  start=02:00:00  dur=00:00:00    {"drainSeconds": 0.0}
```

204.8 s is 8192 Mb drained at 40 Mbps. Nothing in the plan says it. The second downlink finds the
recorder already empty and produces a zero-duration span — a different thing from an unfinished one.

## What this does NOT tell you

It exercises Parakeet through PlanDev's contract. It does **not** exercise the two properties that
make Parakeet interesting in the first place: **nothing here saves or restores a fincon, and nothing
runs long enough to test constant memory.** The contract has no checkpointing seam to plug them
into — which is itself the finding, and the thing that would have to change before an external
backend could be scheduled cheaply.
