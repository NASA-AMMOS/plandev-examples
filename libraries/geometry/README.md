# Geometry Library

Reusable spacecraft geometry subsystem models for Aerie mission models. Provides SPICE-backed orbital mechanics, event generation, and reusable resource registrations.

This library lets a mission compute geometric quantities from SPICE kernel data along its spacecraft's trajectory — spacecraft-to-body distance and speed, sub-spacecraft and illumination angles, Sun–body–spacecraft angle, orbit period and inclination, body half-angle size, and more — plus "spawner" activities that schedule spacecraft eclipses, occultations, periapses, and apoapses.

## What it models

- **Spacecraft position, velocity, and altitude** from SPICE ephemerides (BSP kernels)
- **Orbital event detection** — apoapsis, periapsis, solar eclipses (penumbral / umbral), occultations
- **Sub-point information** — sub-spacecraft and sub-solar points (lat/lon), illumination angles
- **Beta angle** between orbit plane and the Sun direction
- **DSN visibility** — uplink/downlink ranges and one-way light times to ground stations
- **Coordinate conversions** — right ascension / declination, orbit conic elements
- **Time conversions** — JPL time ↔ ephemeris time, planning-window absolute clock

The library lets a mission model declare which bodies are involved (spacecraft, target body, observer body, etc.) and what computations should run; SPICE kernel access is centralized via `SpiceUtils` and `SpiceConstants`. Bodies and the geometric quantities to compute are typically configured in a `default_geometry_config.json` file that gets bundled into the mission-model JAR at compile time.

To point the model at the right spacecraft, set its NAIF ID — for the orbiter example this is the `spiceSpacecraftId` mission configuration parameter (default `-74`, MRO).

## Package

`gov.nasa.jpl.aerie.geometry`

## Key classes

- `GenericGeometryCalculator` — top-level orchestrator; computes resources at variable time steps over a calculation period
- `Body`, `Bodies` — NAIF body configuration (ID, frame, radius, which calculations to run)
- `GenericGeometryResources` — the set of resources every geometry model registers (positions, angles, events)
- `SpiceResourcePopulater` — drives SPICE calls and writes the resource values
- `BodyGeometryGenerator`, `VariableTimeStepGenerator` — sample-time strategies
- Direct SPICE access: `SpiceDirectTimeDependentStateCalculator`, `SpiceDirectEventGenerator`
- Event spawners (in `geometry.activities.spawner`): `AddApoapsis`, `AddPeriapsis`, `AddOccultations`, `AddSpacecraftEclipses`
- Atomic events (in `geometry.activities.atomic`): `Apoapsis`, `Periapsis`, `EnterOccultation`, `ExitOccultation`, `SpacecraftEnterEclipse`, `SpacecraftExitEclipse`
- Return objects: `RADec`, `LatLonCoord`, `OrbitConicElements`, `SubPointInformation`, `IlluminationAngles`
- Globals: `AbsoluteClock`, `JPLTimeConvertUtility`, `Window`

## SPICE kernels

Kernels are not bundled inside this library. The library reads them from `SPICE_DIRECTORY` (env var) or falls back to a relative `spice-kernels` path — see [SpiceConstants.java](src/main/java/gov/nasa/jpl/aerie/geometry/spice/SpiceConstants.java).

In this repo, the canonical kernel location is the top-level shared [spice-kernels/](../../spice-kernels/) directory (an 8-kernel set covering MRO, Mars, Earth, and Sun, ~238 MB total). When deploying to Aerie, mount that directory into the merlin/scheduler workers and set `SPICE_DIRECTORY` accordingly — see [examples/05-orbiter/README.md](../../examples/05-orbiter/README.md).

## Usage

```gradle
dependencies {
    implementation project(':libraries:geometry')
}
```

Configure your bodies and instantiate the calculator from your `Mission` class:

```java
import gov.nasa.jpl.aerie.geometry.spiceinterpolation.*;
import gov.nasa.jpl.aerie.geometry.resources.GenericGeometryResources;

Bodies bodies = new Bodies(Mission.class);
GenericGeometryResources geometryResources = new GenericGeometryResources(bodies);
GenericGeometryCalculator geometryCalculator = new GenericGeometryCalculator(
    new SpiceResourcePopulater(...), bodies, geometryResources, ...);
geometryResources.registerStates(registrar);
```

See [examples/05-orbiter/src/main/java/examples/orbiter/Mission.java](../../examples/05-orbiter/src/main/java/examples/orbiter/Mission.java) for a complete wiring.

## Test coverage

`libraries/geometry/src/test/java/` covers the **direct SPICE layer**:

- [SpiceDirectTimeDependentStateCalculatorTest](src/test/java/gov/nasa/jpl/aerie/geometry/SpiceDirectTimeDependentStateCalculatorTest.java) — 14 sub-tests, MATLAB reference values for state / range / speed / altitude / Sun-Earth-spacecraft angles / sub-point / illumination / beta / half-angle / RA-Dec / LST.
- [SpiceDirectEventGeneratorTest](src/test/java/gov/nasa/jpl/aerie/geometry/SpiceDirectEventGeneratorTest.java) — occultations, periapses, apoapses, conjunctions against MATLAB reference.

**TODO — resource layer + spawner activities are not yet covered here.** The upstream `aerie-multimission-models-bb` had three more tests that depend on a `Mission` class with `default_geometry_config.json` and a full `@MissionModel` package-info:

1. `SpiceResourcePopulaterTest` — config parsing + data-gap window splitting.
2. `GenericGeometryCalculatorTest` — Aerie resource values match direct SPICE calls within ±0.01°.
3. `GeometrySpawnersTest` — spawner activities (`AddSpacecraftEclipses`, `AddOccultations`, `AddPeriapsis`, `AddApoapsis`) produce the right event counts over a sim window.

To port these, build a minimal test mission model inside `libraries/geometry/src/test/java/.../testmodel/`: a `TestMission`, `TestConfiguration`, `package-info.java` with `@MissionModel` + the ~10 activity registrations, plus `default_geometry_config.json` copied from [examples/05-orbiter/src/main/resources/examples/orbiter/default_geometry_config.json](../../examples/05-orbiter/src/main/resources/examples/orbiter/default_geometry_config.json) into `src/test/resources/`. Enable `testAnnotationProcessor "gov.nasa.jpl.aerie:merlin-framework-processor:${aerieVersion}"` in `build.gradle`. ~150–200 lines of scaffold; same shape as the upstream tests.

## Building

```sh
./gradlew :libraries:geometry:build
```

## Source

Initially derived from [NASA-AMMOS/aerie-multimission-models-bb](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) — SPICE scaffolding and core geometry calculators — plus event generators and resource classes consolidated from [aerie-orbiter-model](https://github.com/NASA-AMMOS/aerie-orbiter-model). The original Blackbird models were created for the **Blackbird planner**, a Java-based planning system at JPL. See [ATTRIBUTION.md](../../ATTRIBUTION.md) at the repo root.

## Acknowledgements

Thanks to **Chris Lawler** and **Flora Ridenhour**, the original developers of the Blackbird planner, who graciously provided the Blackbird multi-mission models to the Aerie team as a starting point for this code.
