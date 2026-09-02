# 01 - Power Only Example

A complete PlanDev mission model demonstrating the power library with a Power Equipment List (PEL) and solar array.

## What It Models

This example simulates a spacecraft with:

- A **solar array** power source whose output varies with solar distance, sun angle, and eclipse conditions
- Two **batteries** (CBE and MEV) that charge and discharge based on net power
- A **Power Equipment List (PEL)** with state-based power loads for GNC, telecom, avionics, camera, and locomotion subsystems
- A **distance and angle calculator** daemon that updates solar geometry over time

### Activities

| Activity | Description |
|----------|-------------|
| SolarArrayDeployment | Deploys the solar array over a configurable duration |
| TurnOnCamera | Turns camera on for a specified duration, then off |
| TurnOnTelecom | Turns telecom on for a specified duration, then off |
| ChangeGNCState | Changes GNC between NOMINAL and TURNING states |
| Drive | Ramps up locomotion power in configurable steps |

### Key Resources

- `cbebattery.batterySOC` - Battery state of charge (%)
- `cbebattery.batteryCurrent` - Net current into/out of battery (A)
- `array.powerProduction` - Solar array power output (W)
- `spacecraft.cbeLoad` / `spacecraft.mevLoad` - Total CBE/MEV power loads (W)
- Component states: `gncState`, `telecomState`, `cameraState`, `avionicsState`

## How to Build

```bash
./gradlew :examples:01-power-only:build
```

**Artifact:** `build/libs/power-example.jar` — upload directly to PlanDev.

## Try it

1. Upload `power-example.jar` as a mission model and create a plan.
2. Add a `SolarArrayDeployment` at the start of the plan.
3. Add a `TurnOnCamera` (say 2 hours) followed by a `Drive`.
4. Simulate, then watch `cbebattery.batterySOC` fall while the loads are on and recover once
   they turn off. `spacecraft.cbeLoad` shows the summed PEL draw driving it.
5. Load `PowerModelBasicView.json` as a UI view to get these plotted together.

## Tests

```bash
./gradlew :examples:01-power-only:test
```

Three suites — [`SimulationTest`](src/test/java/examples/power/SimulationTest.java),
[`TurnOnCameraTest`](src/test/java/examples/power/TurnOnCameraTest.java), and
[`TurnOnTelecomTest`](src/test/java/examples/power/TurnOnTelecomTest.java) — all run
in-process without a PlanDev deployment.

## Included Files

- `pel.json` - PEL definition, the input to the [`pel_java_generator.py`](../../tools/pel_java_generator.py) script that generates the PEL model Java code. See [tools/README.md](../../tools/README.md) for how to run it — you must pass an output directory and package, since it does not default to this example's layout.
- `PowerModelBasicView.json` - An PlanDev UI view definition for visualizing power model resources

## Source

Migrated from [NASA-AMMOS/aerie-simple-model-power](https://github.com/NASA-AMMOS/aerie-simple-model-power) (`demosystem` package).
