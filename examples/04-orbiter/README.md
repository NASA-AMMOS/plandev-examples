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

22 activity types across all subsystems:

- **Geometry spawners**: `AddApoapsis`, `AddPeriapsis`, `AddOccultations`, `AddSpacecraftEclipses` — spawn event markers from SPICE data
- **Geometry events**: `Apoapsis`, `Periapsis`, `EnterOccultation`, `ExitOccultation`, `SpacecraftEnterEclipse`, `SpacecraftExitEclipse`
- **Power**: `SolarArrayDeployment`
- **Data**: `GenerateData`, `PlaybackData`, `DeleteData`, `FilterData`, `ChangeDataGenerationRate`, `ReprioritizeData`
- **Telecom**: `Downlink`
- **Radar**: `Radar_On`, `Radar_Off`, `ChangeRadarDataMode`, `TakeRadarObservation`

## SPICE kernels

This model requires SPICE kernels for orbital geometry calculations. The kernels are included in `spice/kernels/` (tracked via Git LFS, ~238 MB total).

The kernel directory is configurable via the `SPICE_DIRECTORY` environment variable (defaults to `spice/kernels`).

### Running locally

The kernels are already in place — just build and the model will find them.

### Deploying to Aerie (Docker)

When uploading the JAR to Aerie, the SPICE kernels must be volume-mounted into the merlin worker container:

```yaml
# In your docker-compose.yml, add to the aerie_merlin service:
volumes:
  - ./examples/04-orbiter/spice/kernels:/spice/kernels
```

Or set the `SPICE_DIRECTORY` environment variable to point to wherever you mount them.

## Build

```bash
./gradlew :examples:04-orbiter:build
```

The fat JAR at `build/libs/orbiter-example.jar` can be uploaded to Aerie (after mounting SPICE kernels).

## Configuration

The model exposes several configuration parameters when creating a plan:

- `spiceSpacecraftId` — NAIF spacecraft ID (default: -74, MRO)
- `powerConfig` — Battery capacity, solar array area, degradation factors
- `dataConfig` — Storage capacity, playback rate, number of bins
- `offPointAngle` — Worst-case off-Sun angle for power calculations (default: 70 degrees)
