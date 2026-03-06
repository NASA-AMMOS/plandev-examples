# 05 - Constraints and Scheduling

Demonstrates Aerie's procedural constraints and scheduling goals — the features that separate Aerie from a simple simulator.

## What's in this example

**Mission model**: A simple spacecraft with power (solar array, battery, PEL) and data (storage buckets) subsystems, plus TakePicture, Downlink, and Calibrate activities.

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

1. Upload the JAR to Aerie
2. Create a plan and add some TakePicture activities
3. Run the scheduling goals to auto-place Calibrate and Downlink activities
4. Run the constraints to check for battery, data, and power violations
5. Simulate and observe the constraint violations on the timeline

## Build

```bash
./gradlew :examples:05-constraints-and-scheduling:build
```
