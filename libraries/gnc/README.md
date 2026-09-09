# GNC Library

Reusable Guidance, Navigation, and Control (GNC) subsystem code for PlanDev mission models. Provides attitude state, pointing-target abstractions, and rotation/observer machinery.

## What it models

- **Attitude state resources** — spacecraft orientation (rotation), rotation rate, slewing flag, pointing axis and angle
- **Pointing targets** — primary and secondary target abstractions (body center, body plane, orbit plane, ahead-cross-nadir, custom)
- **Observers** — generic and spacecraft-instrument observers that consume attitude/target state
- **Attitude generation** — rate-match and no-rate-match attitude models for slewing between targets
- **CK file integration** — read time-tagged SPICE C-kernel attitude segments (`CKAttitudeModel`)

GNC composes with the geometry library: pointing computations need spacecraft and target body positions, which come from `libraries/geometry`.

## Package

`gov.nasa.ammos.plandev.gnc`

## Key classes

- `GncDataModel` — central resource holder (attitude, rotation rate, slewing flag, pointing axis/angle)
- `AttitudeFunctions` — rotation composition, boresight-to-target angle, CK file utilities
- Targets: `BodyCenterPrimaryTarget`, `AheadCrossNadirPrimaryTarget`, `CustomPrimaryTarget`, `BodyCenterSecondaryTarget`, `BodyPlaneSecondaryTarget`, `OrbitPlaneSecondaryTarget`, `CustomSecondaryTarget`
- Observers: `CustomObserver`, `SpacecraftInstrumentObserver`
- Attitude generators: `GenerateAttitudeModel`, `GenerateRateMatchAttitudeModel`, `GenerateNoRateMatchAttitudeModel`
- `CKAttitudeModel` — load time-tagged quaternion segments from a SPICE CK file
- Interfaces: `ADCModel`, `Target`, `Observer`, `Orientation`
- `AttitudeNotAvailableException` — raised when a CK lookup or attitude computation cannot be satisfied

## Usage

```gradle
dependencies {
    implementation project(':libraries:gnc')
}
```

In your `Mission` class:

```java
import gov.nasa.ammos.plandev.gnc.GncDataModel;
import gov.nasa.ammos.plandev.gnc.primary.BodyCenterPrimaryTarget;

GncDataModel gnc = new GncDataModel();
gnc.registerStates(registrar);
// Wire targets/observers to your geometry calculator's outputs.
```

Rotation and vector math relies on Apache `commons-math3`, which this library declares
explicitly as an `api` dependency at a pinned version (see
[build.gradle](build.gradle)) — it does **not** arrive transitively, so a project that copies
this code out of the repo must declare it too:

```gradle
api 'org.apache.commons:commons-math3:3.6.1'
```

## Scope: primitives, not a mission model

This is a set of **building blocks** — attitude, targets, observers, and rotation math — not a
ready-made GNC mission model. There are no activity types here: upstream's `PointingActivity`
was deliberately not carried over, because it was mission-specific, incomplete, and coupled to
Blackbird's configuration. Expect to write your own activities on top of these classes.

## Building

```sh
./gradlew :libraries:gnc:build
```

## Status

Marked **in work** in the upstream [aerie-multimission-models-bb](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) README. Treat the more exotic target/observer combinations as a starting point — well-trodden cases (body-center pointing, single primary target) are solid; the long tail is less exercised. Tests cover the rotation and pointing-angle core (see [GncTest.java](src/test/java/gov/nasa/ammos/plandev/gnc/GncTest.java)).

## Source

Initially derived from [NASA-AMMOS/aerie-multimission-models-bb](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) — attitude / target / observer code. The original Blackbird models were created for the **Blackbird planner**, a Java-based planning system at JPL. See [ATTRIBUTION.md](../../ATTRIBUTION.md) at the repo root.

## Acknowledgements

Thanks to **Chris Lawler** and **Flora Ridenhour**, the original developers of the Blackbird planner, who graciously provided the Blackbird multi-mission models to the PlanDev team as a starting point for this code.
