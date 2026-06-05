# 04 - Orbiter (MRO)

A full-featured Mars orbiter mission model based on the Mars Reconnaissance Orbiter (MRO). This is the most complex example in the repository, integrating five subsystems with SPICE-based orbital geometry.

Migrated from [aerie-orbiter-model](https://github.com/NASA-AMMOS/aerie-orbiter-model).

## Subsystems

| Subsystem | Description |
|-----------|-------------|
| **Geometry** | SPICE-based orbital mechanics — spacecraft position, eclipse detection, occultation events, orbit parameters |
| **Power** | 14-component PEL (ADCS, CDH, EPS, heaters, imager, radar, SSR, telecom TWTAs, etc.), solar array with geometry-driven power generation, dual CBE/MEV battery tracking |
| **Data** | Multi-bin onboard storage with priority-based playback, configurable bin count (default 20) |
| **Telecom** | Friis link equation model with configurable transmitter/receiver/frequency parameters |
| **Radar** | VISAR radar instrument with observation modes and data collection |

## Activities

21 activity types across all subsystems:

- **Geometry spawners**: `AddApoapsis`, `AddPeriapsis`, `AddOccultations`, `AddSpacecraftEclipses` — spawn event markers from SPICE data
- **Geometry events**: `Apoapsis`, `Periapsis`, `EnterOccultation`, `ExitOccultation`, `SpacecraftEnterEclipse`, `SpacecraftExitEclipse`
- **Power**: `SolarArrayDeployment`
- **Data** (from `libraries/data`): `GenerateData`, `PlaybackData`, `DeleteData`, `ChangeDataGenerationRate`, `ReprioritizeData`
- **Telecom**: `Downlink`
- **Radar**: `Radar_On`, `Radar_Off`, `ChangeRadarDataMode`, `TakeRadarObservation`

## SPICE kernels

This model requires SPICE kernels for orbital geometry calculations. The kernels live at the top-level shared directory [`spice-kernels/`](../../spice-kernels/) (tracked via Git LFS, ~238 MB total) — shared with `libraries/geometry`'s tests.

The kernel directory is configurable via the `SPICE_DIRECTORY` environment variable (defaults to `spice-kernels`, resolved relative to the JVM's working directory).

### Running locally

The kernels are already in place — just build and the model will find them.

### Deploying to Aerie (Docker)

When uploading the JAR to Aerie, the SPICE kernels must be volume-mounted into the merlin worker container:

```yaml
# In your docker-compose.yml, add to the aerie_merlin service:
volumes:
  - ./spice-kernels:/spice/kernels
environment:
  SPICE_DIRECTORY: /spice/kernels
```

Or point `SPICE_DIRECTORY` at wherever you mount the kernels.

## Scheduling goals

9 procedural scheduling goals (in `scheduling/`), built as individual ShadowJar artifacts:

| Goal | What it does |
|---|---|
| `AddPeriapses` | SPICE: Computes periapsis events and creates Periapsis activities |
| `AddApoapses` | SPICE: Computes apoapsis events and creates Apoapsis activities |
| `AddOccultations` | SPICE: Computes occultation windows, creates EnterOccultation/ExitOccultation activities |
| `AddSpacecraftEclipses` | SPICE: Computes eclipse windows, creates EnterEclipse/ExitEclipse activities |
| `ScheduleRadarObservations` | Schedules VISAR observations across science orbits (50% DEM, 37.5% MedRes, 12.5% HiRes) |
| `ScheduleDownlinks` | Schedules Downlink activities on designated downlink orbits, outside occultation windows |
| `SchedulePriorityActivities` | Priority-based scheduling with 7 activity priorities and altitude thresholds |
| `SchedulePriorityActivitiesAfterDownlink` | Battery-aware priority scheduling with two modes: RE-SIMULATION and VIRTUAL BATTERY |
| `ScheduleRadarWithStopConditions` | Simulate-then-verify with rollback: pre/post-checks on battery, data volume, and downlink conflicts |

## Constraint procedures

6 procedural constraints (in `constraints/`):

| Constraint | What it checks |
|---|---|
| `MinBatterySOC` | Battery SOC must stay above a configurable minimum |
| `NoDeleteWhileWriting` | DeleteData and GenerateData/ChangeRadarDataMode must not overlap |
| `DownlinkMinDuration` | Downlink activities must meet a minimum duration |
| `NoDownlinkDuringOccultations` | No Downlink activities during occultation windows |
| `ReprioritizeAfterDownlink` | ReprioritizeData must occur within a configurable time after each Downlink |
| `MinWarmupDuration` | Radar must warm up for a minimum time before data collection begins |

## Demo data

Sample plans, views, and external events are in `demo/`:

| Directory | Contents |
|---|---|
| `demo/plans/` | SimplePlan (12 activities), MarsSat Plan (full orbital), Constraint Violation Plan, Example_MarsSat_Plan |
| `demo/views/` | Timeline views: 5 Bin, MarsSat Overview, MarsSat Power, Overview |
| `demo/external-events/` | DSS-24 comm pass source and schema for external event scheduling |
| `demo/external-datasets/` | `sample_dataset.json` (3 profiles × 60k segments) for SimplePlan; regenerate with `generate_sample_dataset.py` |

## Build

```bash
# Mission model JAR
./gradlew :examples:05-orbiter:build

# Scheduling procedure JARs (requires compiling first)
./gradlew :examples:05-orbiter:scheduling:compileJava
./gradlew :examples:05-orbiter:scheduling:buildAllSchedulingProcedureJars

# Constraint procedure JARs
./gradlew :examples:05-orbiter:constraints:compileJava
./gradlew :examples:05-orbiter:constraints:buildAllConstraintProcedureJars
```

The fat JAR at `build/libs/orbiter-example.jar` can be uploaded to Aerie (after mounting SPICE kernels). Scheduling and constraint procedure JARs are built individually in their respective `build/libs/` directories.

## Configuration

The model exposes several configuration parameters when creating a plan:

- `spiceSpacecraftId` — NAIF spacecraft ID (default: -74, MRO)
- `powerConfig` — Battery capacity, solar array area, degradation factors
- `dataConfig` — Storage capacity, playback rate, number of bins
- `offPointAngle` — Worst-case off-Sun angle for power calculations (default: 70 degrees)
