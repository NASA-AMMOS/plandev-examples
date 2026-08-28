# 00-tutorial: Simple SSR Data Recorder

Start here! This is the basic PlanDev mission model from the [modeling tutorial](https://nasa-ammos.github.io/aerie-docs/tutorials/mission-modeling/introduction/).

## What It Models

A simple spacecraft with a Solid State Recorder (SSR) that:
- Records data at configurable rates
- Tracks data volume with multiple integration approaches
- Has a magnetometer with switchable collection modes (OFF, LOW_RATE, HIGH_RATE)

## Key Concepts

- **Activities:** `CollectData` (records data), `ChangeMagMode` (switches magnetometer mode)
- **Resources:** `RecordingRate`, `SSR_Volume_Simple`, `SSR_Volume_Polynomial`, `MagDataMode`
- **Configuration:** Initial battery SOC, integration sample interval, starting mag mode
- **Integration approaches:** The `DataModel` demonstrates 4 different ways to track accumulated volume — from simple discrete updates to polynomial (continuous) integration

## Building

```bash
./gradlew :examples:00-tutorial:build
```

## Source

Migrated from [aerie-modeling-tutorial](https://github.com/NASA-AMMOS/aerie-modeling-tutorial) with package renamed from `missionmodel` to `tutorial`.

## Next Steps

After understanding this model, move on to `examples/01-power-only/` to see how reusable subsystem libraries work.
