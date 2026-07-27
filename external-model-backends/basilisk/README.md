# Basilisk backend — a real astrodynamics simulator as a PlanDev mission model

[Basilisk](https://github.com/AVSLab/basilisk) (AVS Lab, University of Colorado Boulder; ISC) is a
flight-quality spacecraft simulation framework. This adapter serves one model, **`orbiter`**: a
spacecraft in low Earth orbit with SPICE ephemerides, Earth-shadow eclipse geometry, a sun-tracking
solar array, a battery, an instrument filling a solid-state recorder, and a transmitter that only
moves bits while a ground station is above the horizon.

It is the third backend on the [external-model wire contract](../README.md), and the point of it is
not "another example". Blackbird proved the contract carries a foreign discrete-event **engine**;
the Python battery proved it is language-neutral. Basilisk is the first backend whose **clock
disagrees with PlanDev's**, and that turns out to be where all the interesting work is.

```
GET  /models      -> the orbiter, with its identity hash
GET  /introspect  -> 2 activity types, 11 resources, 17 configuration parameters
POST /simulate    -> real + discrete profiles, spans with computed attributes
POST /validate    -> per-parameter notices
```

## What it models

| Activity | Arguments | Computed attributes (derived from telemetry) |
|---|---|---|
| `Observe` | `duration`, `baudRate` (12 Mbps), `powerWatts` (55 W) | `minStateOfCharge`, `meanSunlightFraction`, `storedBitsAtEnd` |
| `Downlink` | `duration`, `baudRate` (8 Mbps), `powerWatts` (78 W) | `accessFraction`, `netStoredBitsChange`, `minStateOfCharge` |

| Resource | Kind | From |
|---|---|---|
| `/power/solarArrayWatts` | real | sun angle × eclipse, via a gimballed array |
| `/power/netWatts` | real | array minus every load |
| `/power/battery/wattHours`, `/power/battery/stateOfCharge` | real | integrated net power, saturating at capacity |
| `/data/storedBits` | real | instrument fill minus transmitter drain |
| `/geometry/sunlightFraction`, `/geometry/altitudeKm` | real | SPICE geometry and the propagated orbit |
| `/geometry/eclipse` | `Sunlight \| Penumbra \| Umbra` | shadow factor |
| `/comm/groundStationInView` | boolean | ground-station access, with a minimum elevation |
| `/instrument/mode`, `/comm/transmitterMode` | variants | what the plan **commanded** |

Configuration covers the integration step, six classical orbital elements, the array, the battery,
the bus load, the recorder, and the ground station (defaults: Goldstone DSS-14).

### Why two of the resources are "commanded" rather than measured

`/comm/transmitterMode` says `Transmitting` whether or not the station is up. Pairing it with the
measured `/comm/groundStationInView` is what lets a PlanDev constraint state the rule over two
resources, with no span query and no knowledge of Basilisk:

```typescript
export default (): Constraint => {
  // A Windows expression states when the rule HOLDS; .violations() reports the complement.
  const transmitting = Discrete.Resource("/comm/transmitterMode").equal("Transmitting");
  const outOfView = Discrete.Resource("/comm/groundStationInView").equal(false);
  return transmitting.and(outOfView).not().violations();
}
```

On a 24-hour plan with two downlinks — one inside the real Goldstone pass, one two hours later —
that reports exactly one violation, `02:00:00 -> 02:05:00`. PlanDev's constraint engine caught a
downlink to a station below the horizon using nothing but resources the model reported.

## The hard part: a fixed-step integrator on a microsecond timeline

Basilisk's clock only exists on multiples of the task step. PlanDev's is microseconds. Every way of
papering over that gap is silent, so the adapter deals with each one explicitly.

**`ConfigureStopTime` halts at the last step at or before the requested time.** A 2-hour plan whose
duration is `2:00:00.000123` gets samples up to `2:00:00.000000`. Profiles that stopped there would
fall short of the plan, and merlin's ingest gate rejects a profile that does not cover the
simulation. The adapter **extends the final segment** by the remainder, held flat — past the last
sample there is no data, and a hold is the only statement that invents none.

**A scheduled event fires at the first step at or after its time.** Activity edges are therefore
snapped with **ceil, not nearest**, and the span reports the **snapped** offsets. An `Observe`
requested at `00:10:00.000001` is stored as starting at `00:10:05`. Reporting the requested time
instead would leave the timeline showing an observation a step before the power profile shows its
draw, with nothing anywhere to explain the gap.

**An activity shorter than one step is refused.** This is the case with no honest answer, and which
way it fails depends on nothing the planner controls: land it between two steps and both edges snap
to the same instant, so it does nothing; land it *on* a step and it stretches to a whole one, so it
does five times what was asked. Either would be recorded as though it were what the plan said. The
adapter refuses both, and the message names `timeStepSeconds`, because that is the fix.

**Rates are secants, never instantaneous derivatives.** PlanDev evaluates a real profile as
`initial + rate × elapsed`, so each segment's computed end must land on the next segment's
`initial`. The battery saturates at capacity and the recorder fills, so the instantaneous derivative
disagrees at exactly those moments and the profile would contradict itself with nothing raised. The
measured discontinuity across a 2-hour run is **0.0**.

That last pair — secant rates and window closure — is generic to any fixed-step backend, so it lives
in [`adapter_core`](../adapter_core.py) (`snap_up`, `real_segments`, `discrete_segments`) rather than
here. NeXosim will want the same code.

## Two more things worth knowing

**The array is gimballed, and that is a modelling decision.** Basilisk's `simpleSolarPanel` projects
a body-fixed normal onto the sun direction, and this model has no attitude control — so a body-fixed
array generates power only when the plan's epoch happens to put the sun on the right side of the
vehicle. That is an artefact of leaving attitude out, not a property of any real spacecraft, and it
is the difference between a battery that cycles with the orbit and one that flatlines at zero on
some dates and not others. A `SysModel` re-points the array each step, rotating through the
spacecraft's own attitude rather than assuming the frames coincide.

**Simulations are serialized.** Basilisk registers its modules with a process-wide C++ messaging
system, so two simulations in one process corrupt each other rather than merely running slowly.
`adapter_core` serves on a threading HTTP server, so the backend holds a lock across the whole
build-and-run. A 24-hour plan takes well under a second; a deployment needing real concurrency runs
more replicas.

## SPICE kernels

The `bsk` wheel ships **no** ephemeris data. Basilisk fetches four files from `naif.jpl.nasa.gov` the
first time a SPICE interface is created — ~128 MB, almost all of it `de430.bsp`. Left to runtime that
is a cold first simulate that hangs or fails outright on any cluster without egress, so the
Dockerfile **bakes them in** at build time and pins the cache with `BSK_SUPPORT_DATA_CACHE`. The
image is 1.29 GB and runs with `--network=none`.

> The PyPI name is **`bsk`**. `pip install Basilisk` fetches an unrelated Redis ORM.

Only the four kernels this model loads are fetched, not Basilisk's whole 45-entry support-data
registry (albedo grids, atmosphere tables, a sky-brightness FITS), none of which it touches.

## Run it

```bash
export PLANDEV_NETWORK=plandev-dupe-1_default          # docker network ls
docker compose up --build basilisk                     # from external-model-backends/
```

Then add it to `EXTERNAL_MODEL_BACKENDS` on merlin **and every merlin worker**:

```json
{"name":"basilisk-lab","url":"http://basilisk-adapter:5021"}
```

## Tests

```bash
pip install "bsk==2.11.0" "numpy>=1.26"
python3 test_bsk_service.py -v
```

62 tests. Most need no propagation and run with no kernels on disk; the 13 in `TestRealSimulation`
skip themselves when the kernels are absent and run inside the image, which has them. The generic
half of the adapter is covered by [`../test_adapter_core.py`](../test_adapter_core.py), and the live
path through merlin — introspection, quantization, orbital geometry, computed attributes, the
sub-step refusal — by `ExternalModelTests` in the PlanDev repo's e2e suite.
