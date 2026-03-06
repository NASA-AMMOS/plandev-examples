# Aerie Lander (Archived)

> **This is an archived, read-only reference.** The code is preserved for historical context but is not maintained or built as part of this repository. Last updated July 2023.

Migrated from [aerie-lander](https://github.com/NASA-AMMOS/aerie-lander).

A mission model of a lander-type mission (inspired by InSight) developed for the Aerie planning and simulation environment. This is a very complex Aerie mission model with 104 activity types across 10 subsystems.

## Subsystems

| Subsystem | Model class | Description |
|-----------|-------------|-------------|
| **APSS** | `APSSModel` | Atmospheric science instrument (pressure, wind, temperature) |
| **Comm (UHF)** | `CommModel` | UHF relay link to orbiters |
| **Comm (X-Band)** | `CommModel` | Direct-to-Earth X-band communication |
| **DSN** | `DSNModel` | Deep Space Network station allocation and visibility |
| **Data** | `DataModel` | Onboard data management, virtual channels, housekeeping |
| **Engineering** | `EngModel` | Safe mode, heaters, tether storage, DART/FPT tables |
| **Heat Probe** | `HeatProbeModel` | HP3 mole instrument |
| **IDS** | `IDSModel` | Instrument deployment system (robotic arm) |
| **Power** | `PowerModel` | Solar array power generation and battery |
| **SEIS** | `SeisModel` | Seismometer instrument (VBB + SP channels) |
| **Wake** | `WakeModel` | Wake/sleep cycle management |
| **Time** | `Clocks` | Mission clocks (LMST, SCLK) |

## Why this is archived

The lander model is too monolithic to refactor into composable libraries — it was built as a single tightly-coupled model before the library pattern existed. It remains valuable as:

- A reference for how a real mission-scale model is structured
- Examples of complex activity patterns (comm scheduling, instrument operations)
- A benchmark for model complexity (~147 Java source files, 17 test files)

For building new models, use the composable libraries in `libraries/` instead.
