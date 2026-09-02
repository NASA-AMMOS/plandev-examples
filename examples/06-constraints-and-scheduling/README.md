# 06 - Constraints and Scheduling

**What this teaches:** writing PlanDev procedural constraints (rules a plan must satisfy) and
procedural scheduling goals (activities the scheduler should add for you).

**Prerequisite:** this project contains **no mission model**. It is a set of procedures that
run against the model from [03-power-and-data](../03-power-and-data/), so build and upload
that first.

## What's in this example

**Constraint procedures** — [`src/main/java/examples/constraints/constraints/`](src/main/java/examples/constraints/constraints/)

| Constraint | What it checks |
|---|---|
| [`BatteryDepthOfDischarge`](src/main/java/examples/constraints/constraints/BatteryDepthOfDischarge.java) | Battery SOC must stay above a minimum threshold (default 20%) |
| [`DataVolumeLimit`](src/main/java/examples/constraints/constraints/DataVolumeLimit.java) | Onboard data volume must not exceed 90% of storage capacity |
| [`PowerBalance`](src/main/java/examples/constraints/constraints/PowerBalance.java) | Flags periods where power consumption exceeds generation |
| [`NoSimultaneousCameraAndDownlink`](src/main/java/examples/constraints/constraints/NoSimultaneousCameraAndDownlink.java) | TakePicture and Downlink activities must not overlap (mutual exclusion pattern) |
| [`DownlinkMinDuration`](src/main/java/examples/constraints/constraints/DownlinkMinDuration.java) | Downlink activities must meet a minimum duration (default 30 min) |

**Scheduling goals** — [`src/main/java/examples/constraints/procedures/`](src/main/java/examples/constraints/procedures/)

| Goal | What it does |
|---|---|
| [`RecurrentCalibration`](src/main/java/examples/constraints/procedures/RecurrentCalibration.java) | Places a Calibrate activity every N hours (default 24h) |
| [`CoscheduleCameraDownlink`](src/main/java/examples/constraints/procedures/CoscheduleCameraDownlink.java) | Schedules a one-hour Downlink 30 minutes after every TakePicture |

Constraints reference resources by their **registered name** (`mainbattery.batterySOC`,
`onboard.volume`). Those strings aren't checked at compile time, so a resource rename in the
model breaks the constraint at run time, not build time.

## Build

```bash
# The mission model these procedures run against (example 03)
./gradlew :examples:03-power-and-data:build

# The procedures — compile first, then build the JARs
./gradlew :examples:06-constraints-and-scheduling:compileJava
./gradlew :examples:06-constraints-and-scheduling:buildAllProcedureJars
```

> Two commands are needed here, and `:build` on its own produces **no artifacts**.

**Artifacts:** seven JARs in `build/libs/`, one per procedure, each named after it
(`DataVolumeLimit.jar`, `RecurrentCalibration.jar`, …). The mission model JAR is
`examples/03-power-and-data/build/libs/power-and-data-example.jar`.

## Try it

1. Upload `power-and-data-example.jar` as a mission model and create a plan from it.
2. Add a few `TakePicture` activities to the plan.
3. [Upload](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/management/)
   the two **goal** JARs (`RecurrentCalibration`, `CoscheduleCameraDownlink`) and all five
   **constraint** JARs. Each JAR is uploaded separately.
4. [Run](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/execution/)
   `RecurrentCalibration` — `Calibrate` activities appear at the configured interval.
5. Run `CoscheduleCameraDownlink` — a one-hour `Downlink` appears after each `TakePicture`.
6. **Simulate the plan**, so the generated activities are reflected in the resource profiles.
   Constraints evaluate against simulation results, so this step is required.
7. Run the constraints and look for battery, data-volume, power, duration, and
   activity-overlap violations on the timeline.

To see violations rather than a clean plan, pack the `TakePicture` activities close together —
that drains the battery and fills the data store faster than the scheduled downlinks recover it.

No tests in this example — see [10-testing-patterns](../10-testing-patterns/).

## Docs

- [Procedural scheduling and constraints: getting started](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/procedural/getting-started/)
- [Procedural constraints](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/procedural/constraints/introduction/)
- [Procedural scheduling goals](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/procedural/scheduling/introduction/)
