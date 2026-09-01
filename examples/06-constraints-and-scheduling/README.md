# 06 - Constraints and Scheduling

Demonstrates PlanDev's procedural constraints and scheduling goals. This project *only* contains constraints and goals,
with no mission model, and is meant to be used alongside the [03-power-and-data](../03-power-and-data/) model.

## What's in this example

**Mission model**: Uses the [03-power-and-data](../03-power-and-data/) model (power, data, TakePicture, Downlink, Calibrate activities). This example contains only the constraint and scheduling procedures — no duplicated model code.

**Constraint procedures** (in `constraints/`):

| Constraint | What it checks |
|---|---|
| `BatteryDepthOfDischarge` | Battery SOC must stay above a minimum threshold (default 20%) |
| `DataVolumeLimit` | Onboard data volume must not exceed 90% of storage capacity |
| `PowerBalance` | Flags periods where power consumption exceeds generation |
| `NoSimultaneousCameraAndDownlink` | TakePicture and Downlink activities must not overlap (mutual exclusion pattern) |
| `DownlinkMinDuration` | Downlink activities must meet a minimum duration (default 30 min) |

**Scheduling goals** (in `goals/`):

| Goal | What it does |
|---|---|
| `RecurrentCalibration` | Places a Calibrate activity every N hours (default 24h) |
| `CoscheduleCameraDownlink` | Schedules a Downlink 30 minutes after every TakePicture |

## How to use

1. Build and upload the `03-power-and-data` mission model JAR to PlanDev, then create a plan.
2. Add some `TakePicture` activities to the plan.
3. Build and [upload](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/management/) this example’s scheduling procedure JAR.
4. [Run](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/execution/) the `RecurrentCalibration` scheduling procedure to add `Calibrate` activities at the configured interval.
5. Run `CoscheduleCameraDownlink` to add a one-hour Downlink after each TakePicture.
6. Simulate the updated plan so the generated activities are included in the resource profiles.
7. Run the constraint procedures and observe battery, data, power, duration, or activity-overlap violations on the timeline.

## Build

```bash
# Build the mission model (from example 03)
./gradlew :examples:03-power-and-data:build

# Build the procedure JAR
./gradlew :examples:06-constraints-and-scheduling:compileJava
./gradlew :examples:06-constraints-and-scheduling:buildAllProcedureJars
```
