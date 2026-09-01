# 03 - Power and Data Combined

Demonstrates how to compose multiple subsystem libraries into a single mission model. This is the simplest multi-library example — it integrates the power and data libraries to show that activities can affect both subsystems simultaneously.

## What's in this model

**Power subsystem** (from `libraries/power/`):
- Solar array power generation (constant 1 AU, no eclipse for simplicity)
- Battery charge/discharge tracking
- Simplified PEL with camera and telecom power states

**Data subsystem** (from `libraries/data/`):
- Onboard storage buckets with priority-based management
- Playback to ground with rate limiting
- Volume tracking per bin

## Activities

| Activity | Subsystems affected | Description |
|----------|-------------------|-------------|
| `TakePicture` | Power + Data | Turns on camera (draws power) while generating science data into a storage bin |
| `Downlink` | Power | Turns on telecom subsystem for a specified duration |
| `Calibrate` | Power | Turns on camera for a calibration sequence (default 30 min) |
| `GenerateData` | Data | Generates data into an onboard bin at a specified rate |
| `PlaybackData` | Data | Plays back data from onboard storage to ground |
| `DeleteData` | Data | Removes data from an onboard bin |

## Build

```bash
./gradlew :examples:03-power-and-data:build
```

**Artifact:** `build/libs/power-and-data-example.jar` — upload directly to PlanDev.

## Try it

1. Upload `power-and-data-example.jar` as a mission model and create a plan.
2. Add three or four `TakePicture` activities in a row.
3. Simulate. `mainbattery.batterySOC` drops as the camera draws power, and `onboard.volume`
   climbs as the pictures land in the storage bin — one activity moving both subsystems is the
   whole point of this example.
4. Add a `Downlink` after them and re-simulate: telecom power goes up, and `onboard.volume`
   comes back down as the spawned `PlaybackData` drains the bin.

`Downlink`'s `durationHours` is fractional, so `1.5` gives a 90-minute pass — example 07 uses
that to size downlinks to real contact windows.

No tests in this example — see [10-testing-patterns](../10-testing-patterns/).

## Key takeaway

The `Mission` class composes library models by instantiating them and wiring their resources together. 
Activities can then interact with multiple subsystems — `TakePicture` draws power via the PEL while 
simultaneously writing data to the storage model. This is the pattern used by more complex examples like the orbiter.

This model also serves as the base mission model for examples [06-constraints-and-scheduling](../06-constraints-and-scheduling/) and [07-external-events](../07-external-events/), which add procedural constraints and scheduling goals on top of this model without duplicating its code.
