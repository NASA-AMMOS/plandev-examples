# 10 - Testing Patterns

Demonstrates how to write automated tests for PlanDev mission models using stateless simulation.

## What's in this example

**Mission model**: Minimal model with `batterySOC` and `dataVolume` resources, plus `DrainBattery` and `CollectData` activities.

**Tests** (in `src/test/java/`):

| Test | What it verifies |
|---|---|
| `testInitialResourceValues` | Simulate with no activities, check initial resource values |
| `testDrainBatteryReducesSOC` | Place a DrainBattery, verify SOC decreases by expected amount |
| `testCollectDataIncreasesVolume` | Place a CollectData, verify data volume increases |

## Key testing pattern

Tests instantiate the generated mission model and run Merlin's simulation driver directly in the test process. 
No running PlanDev services, database, or uploaded mission-model JAR are required:

1. Instantiate the mission model from its generated `GeneratedModelType`.
2. Create an in-memory plan and add activity directives.
3. Run the plan through `SimulationUtility`.
4. Query the resulting resource profiles and assert their values.

## Running tests

```bash
./gradlew :examples:10-testing-patterns:test
```

Gradle prints a test summary in the terminal. A detailed HTML report is generated at:

```text
examples/10-testing-patterns/build/reports/tests/test/index.html
```

Individual XML results are written to:

```text
examples/10-testing-patterns/build/test-results/test/
```

## Build

```bash
./gradlew :examples:10-testing-patterns:build
```

**Artifact:** `build/libs/testing-patterns-example.jar` — upload directly to PlanDev, though
the point of this example is the tests rather than the model.
