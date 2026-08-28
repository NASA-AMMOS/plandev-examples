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

The JAR is output to `build/libs/power-example.jar` and can be uploaded directly to PlanDev.

## Included Files

- `pel.json` - PEL definition used by the `pel_java_generator.py` script to generate the PEL model Java code
- `PowerModelBasicView.json` - An PlanDev UI view definition for visualizing power model resources

## Source

Migrated from [NASA-AMMOS/aerie-simple-model-power](https://github.com/NASA-AMMOS/aerie-simple-model-power) (`demosystem` package).
