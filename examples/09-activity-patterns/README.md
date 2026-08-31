# 09 - Activity Patterns

A cookbook of common activity patterns in PlanDev. Each activity demonstrates a specific idiom that modelers frequently need.

## Patterns

| Activity | Pattern | Key API |
|---|---|---|
| `StateMachineActivity` | Mode transitions (IDLE → WARMUP → ACTIVE → COOLDOWN → IDLE) | `DiscreteEffects.set()`, `delay()` |
| `ConditionalActivity` | Read resource state, branch on value | `Resources.currentValue()` |
| `LoopedActivity` | Repeat N times with delay | `delay()` in a loop, `DiscreteEffects.set()` |
| `ParallelActivities` | Concurrent execution branches | `ModelActions.spawn()` |
| `DelayPatterns` | Duration API usage | `Duration.of()`, `Duration.HOURS`, `plus()` |
| `ResourceGatedActivity` | Wait for a required resource state | `waitUntil()`, `DiscreteResources.when()` |
| `DurationLimitedActivity` | Stop at a target or a maximum duration | `Resources.currentValue()`, `PolynomialEffects.restoring()` |
| `ConfigurationDrivenActivity` | Read behavior settings from simulation configuration | Configuration record accessors |
| `DiscreteVsLinearActivity` | Combine stepped state with continuous accumulation | `DiscreteEffects.set()`, `PolynomialEffects.restoring()` |

## When to use each

- **State machine**: Instrument mode transitions, communication link setup/teardown
- **Conditional**: Skip operations when power is low, choose mode based on state
- **Looped**: Survey sequences, repeated calibrations, data collection cycles
- **Parallel**: Simultaneous instrument operations, concurrent subsystem startup
- **Delay**: Any activity with a duration
- **Resource-gated**: Operations that must wait for a subsystem to become available
- **Duration-limited**: Operations that stop at a target but must not exceed a time limit
- **Configuration-driven**: Values that should be selected once for the entire simulation
- **Discrete and linear resources**: Modes that change instantly alongside quantities that change continuously

## Try the gated and resource examples

1. To see `ResourceGatedActivity` wait, place `StateMachineActivity` at the start of the plan and `ResourceGatedActivity` one minute later. The gated activity starts when `instrumentMode` returns to `IDLE`.
2. Run `DurationLimitedActivity` with its defaults. At 300 MB/hour it reaches the 500 MB target in 100 minutes, before its 120-minute limit. Raise the target above 600 MB to see the duration limit win instead.
3. Change `configuredPowerDrawWatts` or `configuredOperationDurationMinutes` in the simulation configuration, then run `ConfigurationDrivenActivity` to see those settings control its resource profile and duration.
4. Run `DiscreteVsLinearActivity` and inspect `instrumentMode` and `dataVolume`. The mode changes at the activity boundaries while data volume increases continuously between them.

## Build

```bash
./gradlew :examples:09-activity-patterns:build
```
