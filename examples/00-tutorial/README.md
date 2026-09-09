# 00-tutorial: Simple SSR Data Recorder

Start here! This is the basic PlanDev mission model from the [modeling tutorial](https://nasa-ammos.github.io/plandev-docs/tutorials/mission-modeling/introduction/).

## What It Models

A simple spacecraft with a Solid State Recorder (SSR) that:
- Records data at configurable rates
- Tracks data volume with multiple integration approaches
- Has a magnetometer with switchable collection modes (OFF, LOW_RATE, HIGH_RATE)

## Key Concepts

- **Activities:** `CollectData` (records data), `ChangeMagMode` (switches magnetometer mode)
- **Resources:** `RecordingRate`, `SSR_Volume_Simple`, `SSR_Volume_Polynomial`, `MagDataMode`
- **Configuration:** SSR maximum capacity, integration sample interval, starting magnetometer mode
  (see [`Configuration.java`](src/main/java/tutorial/Configuration.java) — there is no battery in this model)
- **Integration approaches:** The `DataModel` demonstrates 4 different ways to track accumulated volume — from simple discrete updates to polynomial (continuous) integration

## Building

```bash
./gradlew :examples:00-tutorial:build
```

**Artifact:** `build/libs/00-tutorial.jar` — upload directly to PlanDev.

## Try it

1. Upload `00-tutorial.jar` as a mission model and create a plan.
2. Add a `ChangeMagMode` activity set to `HIGH_RATE`, then a `CollectData` activity after it.
3. Simulate, and compare `SSR_Volume_Simple` against `SSR_Volume_Polynomial` on the timeline —
   they track the same physical quantity by different integration strategies, which is the
   point of the example.
4. Add a second `ChangeMagMode` back to `OFF` and re-simulate to watch the recording rate drop.

## Tests

```bash
./gradlew :examples:00-tutorial:test
```

[`ModelSimulationTests`](src/test/java/tutorial/ModelSimulationTests.java) runs the model
through a simulation in-process — no PlanDev deployment needed.

## Source

Migrated from [aerie-modeling-tutorial](https://github.com/NASA-AMMOS/aerie-modeling-tutorial) with package renamed from `missionmodel` to `tutorial`.

## Next Steps

After understanding this model, move on to `examples/01-power-only/` to see how reusable subsystem libraries work.
