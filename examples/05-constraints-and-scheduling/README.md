# 05 - Constraints and Scheduling

Demonstrates Aerie's procedural constraints and scheduling goals — the features that separate Aerie from a simple simulator.

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

1. Upload the `03-power-and-data` model JAR to Aerie and create a plan
2. Add some TakePicture activities to the plan
3. Upload this example's procedure JAR and run the scheduling goals
4. Run the constraints to check for battery, data, and power violations
5. Simulate and observe the constraint violations on the timeline

## Build

```bash
# Build the mission model (from example 03)
./gradlew :examples:03-power-and-data:build

# Build the procedure JAR
./gradlew :examples:05-constraints-and-scheduling:build
```
