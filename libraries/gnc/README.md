# GNC Library

Reusable Guidance, Navigation, and Control (GNC) subsystem code for Aerie mission models. Provides attitude state, pointing-target abstractions, and rotation/observer machinery.

## What it models

- **Attitude state resources** — spacecraft orientation (rotation), rotation rate, slewing flag, pointing axis and angle
- **Pointing targets** — primary and secondary target abstractions (body center, body plane, orbit plane, ahead-cross-nadir, custom)
- **Observers** — generic and spacecraft-instrument observers that consume attitude/target state
- **Attitude generation** — rate-match and no-rate-match attitude models for slewing between targets
- **CK file integration** — read time-tagged SPICE C-kernel attitude segments (`CKAttitudeModel`)

GNC composes with the geometry library: pointing computations need spacecraft and target body positions, which come from `libraries/geometry`.

## Package

`gov.nasa.jpl.aerie.gnc`

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
import gov.nasa.jpl.aerie.gnc.GncDataModel;
import gov.nasa.jpl.aerie.gnc.primary.BodyCenterPrimaryTarget;

GncDataModel gnc = new GncDataModel();
gnc.registerStates(registrar);
// Wire targets/observers to your geometry calculator's outputs.
```

Rotation and vector math relies on Apache `commons-math3` (already a transitive dependency via Aerie's contrib library).

## Building

```sh
./gradlew :libraries:gnc:build
```

## Status

Marked **in work** in the upstream [aerie-multimission-models-bb](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) README. Treat the more exotic target/observer combinations as a starting point — well-trodden cases (body-center pointing, single primary target) are solid; the long tail is less exercised. Tests cover the rotation and pointing-angle core (see [GncTest.java](src/test/java/gov/nasa/jpl/aerie/gnc/GncTest.java)).

## Source

Initially derived from [NASA-AMMOS/aerie-multimission-models-bb](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) — attitude / target / observer code. The original Blackbird models were created for the **Blackbird planner**, a Java-based planning system at JPL. See [ATTRIBUTION.md](../../ATTRIBUTION.md) at the repo root.

## Acknowledgements

Thanks to **Chris Lawler** and **Flora Ridenhour**, the original developers of the Blackbird planner, who graciously provided the Blackbird multi-mission models to the Aerie team as a starting point for this code.
