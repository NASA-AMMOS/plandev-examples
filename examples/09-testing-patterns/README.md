# 09 - Testing Patterns

Demonstrates how to write automated tests for Aerie mission models using stateless simulation.

## What's in this example

**Mission model**: Minimal model with `batterySOC` and `dataVolume` resources, plus `DrainBattery` and `CollectData` activities.

**Tests** (in `src/test/java/`):

| Test | What it verifies |
|---|---|
| `testInitialResourceValues` | Simulate with no activities, check initial resource values |
| `testDrainBatteryReducesSOC` | Place a DrainBattery, verify SOC decreases by expected amount |
| `testCollectDataIncreasesVolume` | Place a CollectData, verify data volume increases |

## Key testing pattern

Tests use Aerie's stateless simulation utilities to run a simulation in-process without needing a running Aerie server:

1. Build a `MissionModel` instance from your generated plugin
2. Create activity directives with parameters and start times
3. Run simulation over a time range
4. Query resource profiles from `SimulationResults` and assert values

## Running tests

```bash
./gradlew :examples:09-testing-patterns:test
```

## Build

```bash
./gradlew :examples:09-testing-patterns:build
```
