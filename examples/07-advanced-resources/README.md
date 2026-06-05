# 07 - Advanced Resources

Demonstrates all 5 Streamline resource types beyond the basic Discrete resources covered in the tutorial.

## Resource types demonstrated

| Type | Example resource | Description |
|---|---|---|
| **Discrete** | `instrumentState` | Step functions — ON/OFF enum state |
| **Polynomial** | `instrumentPowerDraw` | Continuous functions of time — power draw that changes during warmup |
| **Linear** (via integration) | `dataVolume` | Clamped integral of data rate with min/max bounds |
| **Clock** | `instrumentUptime` | Elapsed time since last instrument power-on |
| **Derived** | `totalPower`, `batterySOC`, `batteryLow` | Resources computed from other resources |

## Activities

| Activity | What it demonstrates |
|---|---|
| `StartInstrument` | Sets Discrete state, starts Polynomial power ramp, restarts Clock |
| `StopInstrument` | Resets power to zero, stops the clock |
| `ResetTimer` | Resets the Clock resource independently |

## Key patterns

- `Polynomial.polynomial(value, rate)` for linearly-changing resources
- `PolynomialResources.clampedIntegrate()` for bounded accumulation
- `ClockResources.clock()` for drift-free timing
- `add()`, `lessThan()` for derived resource chains

## Build

```bash
./gradlew :examples:07-advanced-resources:build
```
