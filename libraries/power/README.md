# Power Library

Reusable spacecraft power subsystem models for PlanDev mission models.

## What It Models

This library provides generic power system components that can be composed into mission-specific models:

- **BatteryModel** - Spacecraft battery with state of charge tracking, clamped charge/discharge, and configurable capacity. Computes battery current from the difference between power production and demand.
- **GenericSolarArray** - Solar array power source that computes power production based on solar distance, array-to-sun angle, eclipse factor, deployment state, and configurable cell/conversion efficiencies.
- **RtgPowerProduction** - Radioisotope thermoelectric generator (RTG) power source with exponential decay model.
- **PowerSource** - Abstract base class for power sources, providing a common interface for battery integration.
- **PowerModelSimConfig** - Top-level simulation configuration record combining battery and solar array configs.
- **BatterySimConfig** - Battery parameters (capacity, bus voltage, initial SOC).
- **SolarArraySimConfig** - Solar array parameters (area, packing factor, cell efficiency, deployment state).
- **RtgSimConfig** - RTG parameters (number of RTGs, BOL power, decay rate).
- **ArrayDeploymentStates** - Enum for solar array deployment states (UNDEPLOYED, DEPLOYING, DEPLOYED).

## Usage

Add as a dependency in your example or mission model `build.gradle`:

```groovy
dependencies {
  implementation project(':libraries:power')
}
```

Then instantiate the power components in your Mission class:

```java
import gov.nasa.jpl.aerie.power.*;

// Create a solar array power source
PowerSource powerSource = new GenericSolarArray(
    config.powerConfig().powerSourceConfig(),
    distanceResource, angleResource, eclipseResource);

// Create a battery connected to the power source and load
BatteryModel battery = new BatteryModel(
    "main", config.powerConfig().batteryConfig(),
    totalLoadResource, powerSource.getPowerProduction());
```

## Source

Migrated from [NASA-AMMOS/aerie-simple-model-power](https://github.com/NASA-AMMOS/aerie-simple-model-power) (`powersystem` package).
