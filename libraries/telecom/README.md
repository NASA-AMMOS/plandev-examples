# Telecom Library

Reusable telecom (downlink) subsystem code for Aerie mission models — Friis link-equation model, DSN ground-station configs, and per-link bit-rate resources.

## Status: experimental, not currently consumed

This library is **scaffold, not a finished subsystem**. None of the examples in this repo currently depend on it. The orbiter example ([examples/04-orbiter/](../../examples/04-orbiter/)) has its own minimal in-tree `TelecomModel` stub (one resource: `downlinkBitRate`) rather than using this library — see the comment in [examples/04-orbiter/src/main/java/examples/orbiter/telecom/TelecomModel.java](../../examples/04-orbiter/src/main/java/examples/orbiter/telecom/TelecomModel.java).

What works:

- Friis link-equation arithmetic over configurable transmitter / receiver / frequency parameters
- 6 DSN ground stations (DSS-14, 24, 25, 26, 34, 43, 54, etc.) and 7 frequency bands
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

It's a starting point. The link-equation core, the DSN station table, and the frequency-band scaffolding are reasonable seeds for a real telecom library. The plan is to flesh it out (see [§5.2 / §6 P1 in the consolidation plan](../../ATTRIBUTION.md)) and then migrate the orbiter example off its stub onto this library once the gaps are closed.

## Source

Initially derived from [NASA-AMMOS/aerie-simple-model-telecom](https://github.com/NASA-AMMOS/aerie-simple-model-telecom) (originally a private POC; last actively maintained March 2024). See [ATTRIBUTION.md](../../ATTRIBUTION.md) at the repo root for the full directory-to-source mapping.
