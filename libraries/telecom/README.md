# Telecom Library

Reusable telecom (downlink) subsystem code for PlanDev mission models — Friis link-equation model, DSN ground-station configs, and per-link bit-rate resources.

## Status: experimental, not currently consumed

This library is **scaffold, not a finished subsystem**. None of the examples in this repo currently depend on it. The orbiter example ([examples/05-orbiter/](../../examples/05-orbiter/)) has its own minimal in-tree `TelecomModel` stub (one resource: `downlinkBitRate`) rather than using this library — see the comment in [examples/05-orbiter/src/main/java/examples/orbiter/telecom/TelecomModel.java](../../examples/05-orbiter/src/main/java/examples/orbiter/telecom/TelecomModel.java).

What works:

- Friis link-equation arithmetic over configurable transmitter / receiver / frequency parameters
- 6 DSN ground stations (Canberra, Madrid, and Goldstone, each at 70 m and 34 m) and 7 frequency bands
- Per-link bit-rate resources
- `DownlinkActivity` sets the resulting bit rate for a duration

What does **not** work, and would need to be filled in before this library is usable for serious link-budget work:

- **No geometry implementation ships at all.** The library defines a `GeometryModel` interface (`isVisible`, `getDistanceBetween`, `getViewPeriods`) but provides no implementation of it, and nothing bridges [libraries/geometry/](../geometry/)'s SPICE outputs onto that interface. Upstream had a mocked implementation with hardcoded distances; it was deliberately not carried over. Practical consequence: `TelecomModel` must be handed a `GeometryModel` by the caller, and `daemon()` will NPE if it is given null.
- **Antenna gain → bit rate is unimplemented** (TODO in `TelecomModel.java`).
- **Minimum elevation, horizon mask** — none (TODO in `GeometryModel.java`).
- **Pointing-loss function / beam pattern** — none (TODO in `TelecomValueMappers.java`).
- **Degradation loss is hardcoded to 1.0.**

Inline `TODO` block from [TelecomModel.java](src/main/java/gov/nasa/ammos/plandev/telecom/TelecomModel.java):

```
TODO:
 - Downlink Activity
 - Notion of DSN
 - Geometry: calculate view periods
 - Modes of the telecom subsystem
 - Rely on link equation for bitrate
```

## Test coverage

One test file, [`TelecomModelTest`](src/test/java/gov/nasa/ammos/plandev/telecom/TelecomModelTest.java), with two tests. It uses a small inline `FixedDistanceGeometry` stub so the daemon's geometry lookups don't NPE — enough to pin the Friis arithmetic, not enough to validate any visibility or view-period logic. Treat any numbers this library produces as illustrative until the gaps above are filled in.

## Why keep it then?

It's a starting point. The link-equation core, the DSN station table, and the frequency-band scaffolding are reasonable seeds for a real telecom library. The plan is to flesh it out and then migrate the orbiter example off its stub onto this library once the gaps are closed.

## What it would take to finish it

1. **A `SpiceBackedGeometryModel`** implementing telecom's [`GeometryModel`](src/main/java/gov/nasa/ammos/plandev/telecom/GeometryModel.java) by delegating to [libraries/geometry](../geometry/)'s `GenericGeometryCalculator` / `SpiceDirectTimeDependentStateCalculator`. This is the missing piece that would make link budgets mean anything.
2. **A null guard in `TelecomModel.daemon()`**, so the library can be instantiated for resource-registration-only use without crashing.
3. The antenna-gain, elevation-mask and pointing-loss TODOs listed above.

## Source

Initially derived from [NASA-AMMOS/aerie-simple-model-telecom](https://github.com/NASA-AMMOS/aerie-simple-model-telecom) (originally a private POC; last actively maintained March 2024). See [ATTRIBUTION.md](../../ATTRIBUTION.md) at the repo root for the full directory-to-source mapping.
