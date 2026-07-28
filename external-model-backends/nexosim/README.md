# NeXosim backend — a Rust discrete-event model as a PlanDev mission model

[NeXosim](https://github.com/asynchronics/nexosim) (Asynchronics; MIT/Apache-2.0) is a Rust
discrete-event simulation framework. This adapter serves one model, **`cryo`**: a cryocooled
infrared imager — a detector on a thermal node, a bang-bang cryocooler that switches itself, and a
solid-state recorder that fills during an observation and drains during a downlink.

It is the fourth backend on the [external-model wire contract](../README.md), and the first real
user of `adapter_core.ExecBackend` — the escape hatch for a model in another process, which until
now had only the toy in [`../exec_example/`](../exec_example/). Blackbird proved the contract
carries a foreign discrete-event engine; the Python battery proved it is language-neutral;
Basilisk proved it survives a clock that disagrees with PlanDev's. This one is about the SEAM: how
much of an adapter is left once the host owns the contract.

Not much. Blackbird also drives its model in a child process, but with its own plumbing, and its
Python half is 739 lines. [`nx_service.py`](nx_service.py) is 100, half of them prose, and the only
code in it is two overrides for things `ExecBackend` does not carry.

```
GET  /models      -> the cryo model, with its identity hash
GET  /introspect  -> 3 activity types, 6 resources, 9 configuration parameters
POST /simulate    -> real + discrete profiles, spans with computed attributes
POST /validate    -> per-parameter notices, including the model's own
```

The Rust binary implements three verbs on stdin/stdout — `describe`, `simulate` and a `validate`
that `ExecBackend` does not define — and nothing else. It contains no HTTP, no `?model=`
resolution, no default filling, no ValueSchema typechecker, no identity hash and no response
validation, because `adapter_core` does all of that in Python. That is the argument: the contract
is implemented once and a model in any language gets it, without a line of that language knowing
what an identity hash is.

## What it models

| Activity | Arguments | Computed attributes |
|---|---|---|
| `Observe` | `duration`, `targetName` (`"unnamed"`), `framePeriod` (30 s), `powerWatts` (45 W) | `framesWritten`, `framesDropped`, `peakDetectorKelvin` |
| `Downlink` | `duration`, `framePeriod` (5 s), `powerWatts` (30 W) | `framesSent`, `framesRemaining` |
| `SetCoolerSetpoint` | `setpointKelvin` | `previousSetpointKelvin` |

| Resource | Kind | From |
|---|---|---|
| `/thermal/detectorKelvin` | real | integrated heat balance, piecewise linear |
| `/thermal/cryocooler` | `Off \| Cooling` | the controller, not the plan |
| `/power/loadWatts` | real, stepped | bus + payload + transmitter + the cooler's draw |
| `/recorder/framesStored` | **int** | frames written minus frames sent |
| `/recorder/newestFrame` | **struct** `{frameId: int, target: string, detectorKelvin: real}` | the last frame actually stored |
| `/instrument/target` | **string** | what the plan is pointing at, `""` when idle |

`/recorder/newestFrame` and `/instrument/target` are the shapes worth having: no other adapter
declares a **struct**- or **string**-valued resource, and a struct is the one PlanDev treats
specially — structs are CLOSED, so merlin's gate rejects a value carrying a field the schema does
not declare and one missing a field it does. There is no null to fall back on either, which is why
the pre-first-frame value is `frameId: 0` rather than nothing. `targetName` is a string argument the
model CARRIES rather than echoes — it ends up inside that struct, so a plan can be read back off the
recorder.

`/recorder/framesStored` is not a new schema type — the Python battery has an `int` resource too —
but it is the first integer channel that MOVES, and integer channels are where the float-widening
hazard below bites. So are `framesWritten`, `framesDropped`, `framesSent`, `framesRemaining` and the
`recorderCapacityFrames` configuration parameter.

`SetCoolerSetpoint` has **no `duration` parameter at all** and comes back as a span of duration 0.
It is there because an adapter that assumes every activity has a duration only finds out otherwise
on a real mission model.

### The cryocooler is the point

Nothing in the plan turns the cooler on. It switches when the detector crosses
`setpoint ± deadband`, at an instant computed from the heat balance in force at the time, and it
**cancels and re-times itself** whenever an activity changes that balance. A model that scheduled
the crossing once and left it alone passes every single-activity test and then switches at a time
nothing in the plan explains, on a profile self-consistent enough that nothing flags it.

The cooler is sized so it beats the parasitic leak comfortably and the payload by a hair:
`12 + 45 − 55` is `+2 W`, so the detector drifts *up* while observing at about 8 K/hour and recovers
in a few minutes afterwards. In the 4-hour plan below, an hour-long `Observe` reports
`peakDetectorKelvin` of **99.9 K** against a 90 K setpoint. That turns "how long can I integrate
before the detector is out of spec" into a question about a resource, which is a question PlanDev
can answer without knowing what NeXosim is:

```typescript
export default (): Constraint => {
  // A Windows expression states when the rule HOLDS; .violations() reports the complement.
  const coldEnough = Real.Resource("/thermal/detectorKelvin").lessThan(95.0);
  const idle = Discrete.Resource("/instrument/target").equal("");
  return coldEnough.or(idle).violations();
}
```

**Two observations at once are refused.** Not a rule about activities in general — an `Observe` and
a `Downlink` overlapping is ordinary and their loads add — but a rule about shared hardware. Two
observations would have to pick one of two names for `/instrument/target`, and whichever the model
picked would be recorded as though the plan had said so.

Two bounds are refused rather than attempted: a plan that would write or send more than 50 000
frames (a `framePeriod` of 1 µs over a day is 86 billion events, and the count is exact before the
run starts, so the refusal is instant), and one in which the cooler would switch more than 20 000
times — a chattering controller with too small a deadband, or, at the defaults, a plan longer than
about 44 days. Both messages name the parameter to change.

## The easy part, for once: there is no step size

Basilisk's [hard part](../basilisk/README.md#the-hard-part-a-fixed-step-integrator-on-a-microsecond-timeline)
is quantization: its clock only exists on multiples of a task step, so activity edges get snapped,
sub-step activities have no honest answer, and profiles fall short of the window. NeXosim has no
step. `Simulation::step_until` advances to the next scheduled event and lands **exactly** on the
deadline it is given, so:

* An `Observe` requested at `00:00:01.234567` starts at `00:00:01.234567`, and the segment boundary
  is at that microsecond. Nothing is snapped and nothing is refused for being too short.
* The whole run is: schedule every edge at its absolute microsecond, call `step_until` once, read
  the histories back. There is no sampling cadence to choose, and so no cadence to get wrong.
* Every model writes one history row per event it *processes*, so segment boundaries are exactly the
  instants something happened — including the cooler switches, which are not in the plan.

Two things still need care. **Rates are secants**, computed as `(v₁ − v₀)/Δt` rather than from the
heat balance, for the reason `adapter_core.real_segments` gives: PlanDev evaluates a real profile as
`initial + rate × elapsed`, so a segment's computed end must land on the next segment's `initial`.
Here the two agree, because the balance is constant between events — but writing the derivative
would put that agreement at the mercy of the model, and the first saturating channel added later
would break it in silence. **The final segment is extended** to close the window, held flat, because
the last event is never the end of the plan and merlin's gate rejects a profile that does not cover
the simulation.

The cooler's own switches are the one place a microsecond grid does bite: the crossing time is real,
not integral, so it is rounded **up** to the next whole microsecond. Ceil, not nearest — the same
reason `snap_up` is ceil. Rounding down would report the cooler coming on before it did.

> `adapter_core` has `snap_up`, `real_segments` and `discrete_segments` for exactly this work, and
> this adapter cannot reach them: `ExecBackend` passes the child's `{realProfiles, discreteProfiles,
> spans}` through verbatim, so a child must emit SEGMENTS. The conversion is therefore reimplemented
> in `run.rs` — deliberately mirroring the Python, comment for comment, so the two can be diffed.

## Three ways Rust can be wrong here that Python cannot

**`serde_json` writes `NaN` and `Infinity` as `null`, and returns `Ok`.** Python is protected by
`json.dumps(..., allow_nan=False)`, which raises. Rust has no equivalent, and the damage is worse
than a crash: `check_response` walks a response looking for non-finite *numbers*, and by the time it
looks there is no number left to object to — `null` is legal JSON. PlanDev stores a profile segment
whose `initial` is null and the first anyone hears of it is a chart with a hole in it. So `wire.rs`
makes `real()` the only route from an `f64` to a JSON number, built on
`serde_json::Number::from_f64`, which returns `None` for precisely those two cases, and the message
names the resource and the microsecond. `no_resource_value_or_computed_attribute_is_ever_null`
checks the whole response — scoped to values, because `parentId` is legitimately null on every root
span.

**`HashMap` iteration order is randomized per process.** Parameter order is load-bearing: merlin
assigns each parameter an `order` from its index, persists it, and plandev-ui lays the argument form
out in it. `adapter_core` re-canonicalizes the declaration before hashing, but it hashes parameters
as a *list*, so array order still reaches the identity hash — and that hash is the attestation
merlin stores. A `HashMap` anywhere on this path is invisible to a Rust unit test, because within
one process it is perfectly stable. The declaration is built from JSON arrays and the response from
`BTreeMap`s, and `test_nx_service.py` runs `describe` in **two separate processes** and diffs the
bytes.

**An `int`-schema resource emitted as `f64` serializes as `1.0`,** and merlin's `asInt()` rejects it
at ingest with nothing pointing back at the cast that widened it. Counts are `i64` end to end and
leave through `wire::int`. Checked twice: in Rust on the serialized value, and in Python on the
parsed one, because `isinstance(2.0, int)` is `False` and that is the shape merlin will see.

## What `ExecBackend` did not carry

It was enough to run the model, and two things had to be worked around in
[`nx_service.py`](nx_service.py) rather than in the host:

* **Capabilities.** `declaration_from_json` has no branch for `capabilities`, and an *absent*
  capability means unsupported — so a pure simulator would be published as one PlanDev's own
  scheduler must not drive. The value is lifted out of the describe document by hand.
* **Deep validation.** `ExecBackend` defines `describe` and `simulate`, and `/validate` is not one
  of them, so an out-of-process model can only be validated against its own declaration. Every
  semantic mistake — a frame period that would flood the recorder, a setpoint below absolute zero —
  goes unreported until someone runs the plan, which is the one moment the planner is not looking at
  the form that caused it. `nx-model` answers a third verb, `validate`, and `NexosimBackend`
  overrides `deep_validate` to call it.

A third has no workaround here. **A child cannot say "this is a 400".** `ExecBackend` maps every
nonzero exit to a `ModelError`, which is a 500, so a planner who overlaps two observations is told
the adapter failed rather than that their plan is wrong. `nx-model` exits **2** for a caller error
and **1** for its own, so the convention is available the day the host wants it.

## What the image actually weighs

The binary is 987 KB, statically linked against musl, and genuinely runs `FROM scratch` — a
scratch image containing nothing but it is **1.48 MB**. That is not what ships, because
`ExecBackend` means the **Python host spawns the Rust model**, so the runtime needs an interpreter
too:

| | |
|---|---|
| `plandev/nexosim-adapter` | **80.4 MB** |
| — `python:3.12-alpine` | 79.5 MB |
| — `nx-model` | 1.0 MB |
| — `adapter_core.py` + `nx_service.py` | 94 KB |
| cold build, `--no-cache`, base images already pulled | **~17 s** (15.8 s of it cargo) |

For comparison: 203 MB python, 447 MB blackbird, 1.29 GB basilisk. It is the smallest of the four,
including the pure-Python one — but by choosing Alpine over Debian, not by being written in Rust.
Almost all of it is CPython. Dropping to `alpine:3.21` + `apk add python3` saves 5 MB and loses pip;
not worth it.

A 7-day plan with 14 activities takes **0.1 s** end to end over HTTP, including spawning the child,
and comes back as 646 KB — about 3 000 segments each on the two continuous resources, most of them
cryocooler duty cycles.

## Run it

This service is not in `docker-compose.yml` yet. The stanza is the same shape as the others, with
the build context at `external-model-backends/` so `adapter_core.py` is reachable:

```yaml
  nexosim:
    build: {context: ., dockerfile: nexosim/Dockerfile}
    image: plandev/nexosim-adapter
    container_name: nexosim-adapter
    networks: [plandev]
    restart: unless-stopped
```

```bash
export PLANDEV_NETWORK=plandev-dupe-1_default          # docker network ls
docker compose up --build nexosim                      # from external-model-backends/
```

Or without compose, which is how everything above was measured:

```bash
docker build -f nexosim/Dockerfile -t plandev/nexosim-adapter .   # from external-model-backends/
docker run --rm -p 5031:5031 plandev/nexosim-adapter
```

Then add it to `EXTERNAL_MODEL_BACKENDS` on merlin **and every merlin worker**:

```json
{"name":"nexosim-lab","url":"http://nexosim-adapter:5031"}
```

## Tests

```bash
cargo test                                             # 34, the model and the timeline
cargo build --release && python3 test_nx_service.py -v # 25, the host boundary
```

The Rust tests cover window closure, secant continuity, microsecond placement, frame attribution,
the shared-hardware refusals and the three hazards above. The Python tests cover everything that
only exists once the host and the binary are both in the picture: across-process declaration
stability, the host's own reading of the declaration, a real run through `check_response`, and the
two workarounds — each would fail if its workaround were dropped. They skip themselves when the
binary is not built, since it is a compiled artefact and a fresh checkout should not look broken.

The generic half of the adapter is covered by [`../test_adapter_core.py`](../test_adapter_core.py).
