# 07 - Activity Patterns

A cookbook of common activity patterns in Aerie. Each activity demonstrates a specific idiom that modelers frequently need.

## Patterns

| Activity | Pattern | Key API |
|---|---|---|
| `StateMachineActivity` | Mode transitions (IDLE → WARMUP → ACTIVE → COOLDOWN → IDLE) | `DiscreteEffects.set()`, `delay()` |
| `ConditionalActivity` | Read resource state, branch on value | `Resources.currentValue()` |
| `LoopedActivity` | Repeat N times with delay | `delay()` in a loop, `DiscreteEffects.set()` |
| `ParallelActivities` | Concurrent execution branches | `ModelActions.spawn()` |
| `DelayPatterns` | Duration API usage | `Duration.of()`, `Duration.HOURS`, `plus()` |

## When to use each

- **State machine**: Instrument mode transitions, communication link setup/teardown
- **Conditional**: Skip operations when power is low, choose mode based on state
- **Looped**: Survey sequences, repeated calibrations, data collection cycles
- **Parallel**: Simultaneous instrument operations, concurrent subsystem startup
- **Delay**: Any activity with a duration

## Build

```bash
./gradlew :examples:08-activity-patterns:build
```
