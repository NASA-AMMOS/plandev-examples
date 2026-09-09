# Geometry Library

Reusable spacecraft geometry subsystem models for PlanDev mission models. Provides SPICE-backed orbital mechanics, event generation, and reusable resource registrations.

This library lets a mission compute geometric quantities from SPICE kernel data along its spacecraft's trajectory — spacecraft-to-body distance and speed, sub-spacecraft and illumination angles, Sun–body–spacecraft angle, orbit period and inclination, body half-angle size, and more. It also **detects** discrete orbital events (spacecraft eclipses, occultations, periapses, apoapses); the "spawner" activities that turn those detections into timeline activities live in the orbiter example, not this library (see below).

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

`gov.nasa.ammos.plandev.geometry`

## Key classes

- `GenericGeometryCalculator` — top-level orchestrator; computes resources at variable time steps over a calculation period
- `Body`, `Bodies` — NAIF body configuration (ID, frame, radius, which calculations to run)
- `GenericGeometryResources` — the set of resources every geometry model registers (positions, angles, events)
- `SpiceResourcePopulater` — drives SPICE calls and writes the resource values
- `BodyGeometryGenerator`, `VariableTimeStepGenerator` — sample-time strategies
- Direct SPICE access: `SpiceDirectTimeDependentStateCalculator`, `SpiceDirectEventGenerator` (the event *detection* primitive)
- Return objects: `RADec`, `LatLonCoord`, `OrbitConicElements`, `SubPointInformation`, `IlluminationAngles`
- Globals: `AbsoluteClock`, `JPLTimeConvertUtility`, `Window`

> **Event activities live in the orbiter example, not this library.** The spawner activities
> (`AddApoapsis`, `AddPeriapsis`, `AddOccultations`, `AddSpacecraftEclipses`) and the atomic
> events they emit (`Apoapsis`, `Periapsis`, `EnterOccultation`, `ExitOccultation`,
> `SpacecraftEnterEclipse`, `SpacecraftExitEclipse`) are defined in
> [examples/05-orbiter](../../examples/05-orbiter/) under
> `examples.orbiter.geometry.activities.{spawner,atomic}`. They wrap this library's
> `SpiceDirectEventGenerator`. This library ships the detection primitives; the mission model
> decides how to surface them as activities.

## SPICE kernels

Kernels are not bundled inside this library. The library reads them from `SPICE_DIRECTORY` (env var) or falls back to a relative `spice-kernels` path — see [SpiceConstants.java](src/main/java/gov/nasa/ammos/plandev/geometry/spice/SpiceConstants.java).

In this repo, the canonical kernel location is the top-level shared [spice-kernels/](../../spice-kernels/) directory (an 8-kernel set covering MRO, Mars, Earth, and Sun, ~238 MB total). When deploying to PlanDev, mount that directory into the merlin/scheduler workers and set `SPICE_DIRECTORY` accordingly — see [examples/05-orbiter/README.md](../../examples/05-orbiter/README.md).

## Usage

```gradle
dependencies {
    implementation project(':libraries:geometry')
}
```

Configure your bodies and instantiate the calculator from your `Mission` class:

```java
import gov.nasa.ammos.plandev.geometry.spiceinterpolation.*;
import gov.nasa.ammos.plandev.geometry.resources.GenericGeometryResources;

Bodies bodies = new Bodies(Mission.class);
GenericGeometryResources geometryResources = new GenericGeometryResources(bodies);
GenericGeometryCalculator geometryCalculator = new GenericGeometryCalculator(
    new SpiceResourcePopulater(...), bodies, geometryResources, ...);
geometryResources.registerStates(registrar);
```

See [examples/05-orbiter/src/main/java/examples/orbiter/Mission.java](../../examples/05-orbiter/src/main/java/examples/orbiter/Mission.java) for a complete wiring.

## Test coverage

`libraries/geometry/src/test/java/` covers the **direct SPICE layer**:

- [SpiceDirectTimeDependentStateCalculatorTest](src/test/java/gov/nasa/ammos/plandev/geometry/SpiceDirectTimeDependentStateCalculatorTest.java) — 15 sub-tests, MATLAB reference values for state / range / speed / altitude / Sun-Earth-spacecraft angles / sub-point / illumination / beta / half-angle / RA-Dec / LST.
- [SpiceDirectEventGeneratorTest](src/test/java/gov/nasa/ammos/plandev/geometry/SpiceDirectEventGeneratorTest.java) — occultations, periapses, apoapses, conjunctions against MATLAB reference.

### What is not covered

- **The PlanDev resource layer.** `SpiceResourcePopulater` (config parsing, data-gap window
  splitting) and `GenericGeometryCalculator` (whether registered resource values match direct
  SPICE calls) have no tests.
- **The spawner activities.** `AddSpacecraftEclipses`, `AddOccultations`, `AddPeriapsis` and
  `AddApoapsis` — which live in [examples/05-orbiter](../../examples/05-orbiter/) — have no
  tests, so nothing verifies the event counts they produce over a simulation window.
- **Kernel loading inside a mission model.** The tests above call the calculators directly.
  Loading kernels through a `@MissionModel` is exercised only by manually simulating the
  orbiter example.

Covering the first two requires a minimal test mission model (a `@MissionModel` package-info,
a test `Mission` and `Configuration`, and a geometry config resource) plus
`testAnnotationProcessor` wired into `build.gradle`; the upstream `aerie-multimission-models-bb`
had tests of this shape that were not carried over.

## Building

```sh
./gradlew :libraries:geometry:build
```

## Source

Initially derived from [NASA-AMMOS/aerie-multimission-models-bb](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) — SPICE scaffolding and core geometry calculators — plus event generators and resource classes consolidated from [aerie-orbiter-model](https://github.com/NASA-AMMOS/aerie-orbiter-model). The original Blackbird models were created for the **Blackbird planner**, a Java-based planning system at JPL. See [ATTRIBUTION.md](../../ATTRIBUTION.md) at the repo root.

## Acknowledgements

Thanks to **Chris Lawler** and **Flora Ridenhour**, the original developers of the Blackbird planner, who graciously provided the Blackbird multi-mission models to the PlanDev team as a starting point for this code.
