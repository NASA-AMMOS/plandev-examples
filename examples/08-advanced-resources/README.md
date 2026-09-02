# 08 - Advanced Resources

Demonstrates the [streamline](https://github.com/NASA-AMMOS/plandev/blob/develop/contrib/src/main/java/gov/nasa/ammos/plandev/contrib/streamline/streamline-guide.md) resource types beyond the basic discrete
resources covered in the tutorial.

The streamline framework is an alternative library for defining resources in your mission model, available from
`plandev.contrib.streamline`. For more details on the motivations behind the framework, see [this PR](https://github.com/NASA-AMMOS/plandev/pull/1253)
and the [streamline user's guide](https://github.com/NASA-AMMOS/plandev/blob/develop/contrib/src/main/java/gov/nasa/ammos/plandev/contrib/streamline/streamline-guide.md).

The streamline library defines **five dynamics types** — `discrete`, `polynomial`,
`linear`, `clocks`, and `black_box`. This example exercises four of them (plus *derived*
resources, which are a way of building resources rather than a dynamics type). The fifth,
`black_box`, is demonstrated in
[libraries/power `RtgPowerProduction`](../../libraries/power/src/main/java/gov/nasa/ammos/plandev/power/RtgPowerProduction.java).

## Resource types demonstrated

| Type | Example resource | Description |
|---|---|---|
| **Discrete** | `instrumentState` | Step functions — an ON/OFF enum state |
| **Polynomial** | `instrumentPowerDraw`, `dataRate` | Continuous functions of time — power draw that ramps during warmup, plus a data rate that is integrated to `dataVolume` via `clampedIntegrate` |
| **Linear** | — (registration only) | Not modeled directly. The polynomials/clock above are converted to `Linear` via `assumeLinear` / `approximateAsLinear` only to register them, since PlanDev's `real` registrar takes linear profiles. This is the pattern the streamline guide recommends: model in `Polynomial`, convert to `Linear` just for output. |
| **Clock** (`VariableClock`) | `instrumentUptime` | A stopwatch that runs at 1x sim time while the instrument is ON and pauses (0x) while OFF, so it measures accumulated on-time |
| **Derived** | `totalPower`, `batterySOC`, `batteryLow` | Resources computed from other resources (sum, scaled integral, threshold) |


## Activities

| Activity | What it demonstrates |
|---|---|
| `StartInstrument` | Sets Discrete state ON, starts the Polynomial power ramp + data rate, `restart`s the uptime stopwatch; on shutoff it zeros power/rate and `pause`s the stopwatch |
| `StopInstrument` | Turns the instrument OFF, zeros power/rate, and `pause`s the stopwatch (freezes uptime, does not reset it) |
| `ResetTimer` | `reset`s the uptime stopwatch to zero and pauses it — independent of instrument state |

## Key patterns

- `Polynomial.polynomial(value, rate)` for linearly-changing resources
- `PolynomialResources.clampedIntegrate()` for bounded accumulation (min/max limits)
- `VariableClock.pausedStopwatch()` + `VariableClockEffects.restart` / `pause` / `reset` for a stopwatch that only counts while active
- `add()`, `multiply()`, `lessThan()` for derived resource chains
- `assumeLinear()` / `approximateAsLinear()` / `VariableClockResources.asLinear()` to register non-discrete resources with the `real` registrar

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `batteryCapacityWh` | 100.0 | Battery capacity in watt-hours |
| `initialSocPercent` | 80.0 | Initial state of charge (0-100) |

Instrument power is an activity parameter (`StartInstrument.powerW`) rather than a
configuration value, so different activations can draw different amounts.

## Build

```bash
./gradlew :examples:08-advanced-resources:build
```

**Artifact:** `build/libs/advanced-resources-example.jar` — upload directly to PlanDev.

## Try it

1. Upload `advanced-resources-example.jar` as a mission model and create a plan.
2. Add a `StartInstrument` with `durationHours = 2`.
3. Simulate, then look at each dynamics type on one timeline:
   - `instrumentState` steps ON then OFF (**discrete**)
   - `instrumentPowerDraw` ramps upward across the two hours rather than sitting flat —
     that is the `warmupRateWPerSec` term of the **polynomial**
   - `instrumentUptime` counts up while ON and flatlines after (**clock**)
   - `batterySOC` and `batteryLow` fall out of the others (**derived**)
4. Add a `StopInstrument` 30 minutes in — the instrument turns off early, and `instrumentUptime`
   freezes at 30 minutes instead of continuing.
5. Add a `ResetTimer` afterwards to send `instrumentUptime` back to zero without touching the
   instrument state.

Note `durationHours` always has a value, so a `StartInstrument` will always shut itself off at
the end of its duration; use `StopInstrument` for an earlier shutoff.

No tests in this example — see [10-testing-patterns](../10-testing-patterns/).
