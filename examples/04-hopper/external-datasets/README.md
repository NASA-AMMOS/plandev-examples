# Hopper — Sun & Earth Elevation (external dataset)

A SPICE-computed, JPL-Horizons-validated time-series of the **Sun and Earth
elevation** above the local horizon as seen from a fixed point on the lunar
surface (default: south-pole site lat −87.5°, lon 5.0°). This reproduces the
behavior of the reference "Lunar Sun/Earth Visibility Calculator" — near the
pole the Sun grazes the horizon (~±4°) and the Earth oscillates ~±9° due to
lunar libration.

This is **Phase 1** of the hopper Sun/Earth-elevation work: it provides the
*reference* the in-simulation resource (a later phase's `SurfaceGeometryCalculator`)
is validated against — mirroring the "JPL Horizons reference" series in the chart.
Uploaded to a plan, it also stands on its own as the **external-dataset** answer
to "show Sun/Earth elevation on a hopper plan."

## Profiles

`lunar_elevation_dataset.json` (real-typed, `{initial, rate}` linear segments):

| Profile | Source | Meaning |
|---|---|---|
| `sunElevation` | SPICE (IAU_MOON, spherical Moon) | Sun apparent elevation (deg) — the method the Java model mirrors |
| `earthElevation` | SPICE (IAU_MOON, spherical Moon) | Earth apparent elevation (deg) |
| `sunElevationHorizons` | JPL Horizons (`--horizons`) | Independent reference overlay |
| `earthElevationHorizons` | JPL Horizons (`--horizons`) | Independent reference overlay |

Default: 2028, 365 days, **hourly** (`--step-minutes 60`) → 8,760 seg/profile,
~35k rows total, ~2.7 MiB. Elevation is smooth, so hourly is visually
indistinguishable from finer sampling.

> **Keep the row count modest.** Aerie ingests external-dataset segments at only
> ~hundreds of `profile_segment` rows/sec, so size for *ingest time*, not detail:
> hourly-over-a-year (~35k rows) ingests in ~1 min; sub-10-minute resolution
> (~240k rows) took ~7 min. There is **no** minimum segment count. Use a coarser
> `--step-minutes` (or fewer `--days`) for faster uploads.

## How it's computed & validated

Per epoch: target (Sun=10 / Earth=399) position relative to the Moon center in
J2000 (`spkpos`, `abcorr=LT+S`), rotated into the `IAU_MOON` body-fixed frame
(`pxform`), minus the observer's surface offset; elevation = 90° − angle(look, up).
Keeping the full surface-offset subtraction is what produces Earth's libration swing.

Two independent cross-checks confirm correctness:

- **`--fidelity`** (offline): manual method vs SPICE's own topocentric routine
  `azlcpo` → agreement **0.0000°**.
- **`--horizons`** (network): manual method vs JPL Horizons apparent elevation →
  agreement **0.002°** across the year. This settles the frame-fidelity question:
  **`IAU_MOON` is more than adequate** — no high-fidelity `MOON_ME` kernels needed.

## Regenerate

Requires `spiceypy` + `numpy` and the shared kernels in
[`spice-kernels/`](../../../spice-kernels/) (`de440s.bsp`, `pck00011.tpc`,
`naif0012.tls` — already in the repo; `git lfs pull` if you only have pointers).

```bash
pip install spiceypy numpy

# Computed profiles only (offline, reproducible):
python3 generate_lunar_elevation.py

# Add the JPL Horizons reference profiles + report deviation (needs network):
python3 generate_lunar_elevation.py --horizons

# Behind a TLS-intercepting proxy (self-signed cert), add --insecure:
python3 generate_lunar_elevation.py --horizons --insecure
```

Useful flags: `--lat/--lon` (site), `--start YYYY-MM-DD`, `--days`, `--segments`,
`--plan-id`, `--out`. Override the kernel directory with `SPICE_DIRECTORY`.

## Upload to a plan

External datasets attach to a specific Aerie plan, so set `--plan-id` to your
plan's id (the JSON's `planId` must match) and POST `lunar_elevation_dataset.json`
to Aerie's external-dataset endpoint (UI: plan → External Datasets → upload; or
the merlin API `addExternalDataset`). The profiles then render on the plan
timeline alongside the model's resources.
