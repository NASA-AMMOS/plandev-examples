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

- **Geometry is mocked** — hardcoded distances and a fake visibility rotation. There is no integration with [libraries/geometry/](../geometry/) yet, so no real view-period calculation.
- **Antenna gain → bit rate is unimplemented** (TODO in `TelecomModel.java`).
- **Minimum elevation, horizon mask** — none (TODO in `GeometryModel.java`).
- **Pointing-loss function / beam pattern** — none (TODO in `TelecomValueMappers.java`).
- **Degradation loss is hardcoded to 1.0** (per the upstream `docs/ModelBehaviorDescription.md`).

Inline `TODO` block from [TelecomModel.java](src/main/java/gov/nasa/jpl/aerie/telecom/TelecomModel.java):

```
TODO:
 - Downlink Activity
 - Notion of DSN
 - Geometry: calculate view periods
 - Modes of the telecom subsystem
 - Rely on link equation for bitrate
```

## Test coverage

Two tests upstream are functional (Friis bit-rate calculation, mapper serialization). Two are stubs (delay-only or empty body). Treat any numbers this library produces as illustrative until the items above are filled in.

## Why keep it then?

It's a starting point. The link-equation core, the DSN station table, and the frequency-band scaffolding are reasonable seeds for a real telecom library. The plan is to flesh it out and then migrate the orbiter example off its stub onto this library once the gaps are closed.

## Follow-up: real geometry integration

The library defines its own [`GeometryModel`](src/main/java/gov/nasa/jpl/aerie/telecom/GeometryModel.java) interface (`isVisible`, `getDistanceBetween`, `getViewPeriods`), but ships **no implementation** — the upstream `aerie-simple-model-telecom` had a mocked `GeometryModelImpl` in a separate `geometry/` subproject that we deliberately skipped because [libraries/geometry/](../geometry/) already provides real SPICE-backed geometry from a different upstream.

The gap that remains: **nothing currently bridges `libraries/geometry`'s SPICE outputs into telecom's `GeometryModel` interface.** Until that adapter exists, `TelecomModel.daemon()` will NPE on any non-null but actual deployment. Two follow-up tasks worth tracking:

1. **Build a `SpiceBackedGeometryModel`** that implements telecom's `GeometryModel<String>` by delegating to `libraries/geometry`'s `GenericGeometryCalculator` / `SpiceDirectTimeDependentStateCalculator`. This is the "real" integration that closes the README's "geometry is mocked" caveat.
2. **Make `TelecomModel` defensive against null geometry** — a tiny null guard in `daemon()` would let the library be instantiated for resource-registration-only use cases without crashing.

The test ([src/test/java/.../TelecomModelTest.java](src/test/java/gov/nasa/jpl/aerie/telecom/TelecomModelTest.java)) uses a tiny inline `FixedDistanceGeometry` stub so the daemon's geometry lookups don't NPE — sufficient to pin the Friis arithmetic, insufficient to validate any visibility / view-period logic.

## Source

Initially derived from [NASA-AMMOS/aerie-simple-model-telecom](https://github.com/NASA-AMMOS/aerie-simple-model-telecom) (originally a private POC; last actively maintained March 2024). See [ATTRIBUTION.md](../../ATTRIBUTION.md) at the repo root for the full directory-to-source mapping.
