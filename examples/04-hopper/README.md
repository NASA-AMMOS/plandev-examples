# 04 - Hopper (Lunar Hopper)

A small, complete **lunar hopper** mission model that composes the `power` and `data`
building blocks. This is the gentle next step after [03-power-and-data](../03-power-and-data/):
where 03 shows the bare composition pattern, hopper is a realistic little model — with its own
activities, constraints, external events, and an external dataset — that you can read end to
end and imitate for your own mission. The much larger [05-orbiter](../05-orbiter/) is the deep
end.

## What it models

A surface hopper that images a site, hops to a new location, and downlinks its data during
ground contacts:

- **Power** — a `SimplePEL` (power equipment list) tracks three load states and sums them into
  a total load that drives the library `BatteryModel`, fed by a library `GenericSolarArray`:

  | State | OFF | ON |
  |-------|-----|----|
  | `cameraState` | 0 W | 48 W |
  | `hopState` | 80 W (idle) | 1000 W (hopping) |
  | `telecomState` | 0 W | 25 W |

  Geometry is intentionally simplified (constant 1 AU from the Sun, array Sun-facing, no
  eclipse) — hopper is about *composition*, not orbital mechanics. The orbiter adds real SPICE
  geometry.

- **Data** — two prioritized onboard storage bins (library `Data`), a 10 Gb default storage
  limit, and a 10 Kbps default playback rate (both `Configuration` parameters).

## What's new vs. 03-power-and-data

- A real mission flavor with three activities that each drive **both** subsystems.
- A **constraints** subproject (`MinBatterySOC`).
- **External events** (DSN ground contacts) and an **external dataset** (lunar Sun/Earth
  elevation) — the kinds of real-world inputs a mission planner schedules against.

## Activities

| Activity | Power effect | Data effect |
|----------|--------------|-------------|
| `TakePicture` | camera ON for the duration | writes science data into an onboard bin at `dataRateBps` |
| `PerformHop` | hop ON (1000 W) for the duration | writes telemetry data into an onboard bin |
| `Downlink` | telecom ON for the duration | spawns the library `PlaybackData`, then `DeleteData` on all bins when done |

`TakePicture` and `PerformHop` use `Bucket.receive(rate, duration)` — a blocking call that
turns the bin's receive rate on, accumulates data for the duration, then turns it off
(so it both produces data and provides the activity's delay). `Downlink` reuses the library's
`PlaybackData` / `DeleteData` activities directly.

## External events & datasets

- `external-events/` — example DSN ground-contact windows (`dss24_source.json`,
  `comms_pass_schema.json`) you can upload as external events and schedule `Downlink`s against.
- `external-datasets/` — a lunar Sun/Earth elevation profile computed from SPICE
  (`generate_lunar_elevation.py` → `lunar_elevation_dataset.json`). See
  [external-datasets/README.md](external-datasets/README.md) for the math and how to regenerate.
- `hopperplan1.json` — a sample plan; `views/lunar_elevation_view.json` — a sample view.

## Build

```bash
# Mission model JAR (uploadable to PlanDev)
./gradlew :examples:04-hopper:build        # produces hopper.jar

# Constraint procedure JAR
./gradlew :examples:04-hopper:constraints:build
```

The model composes `libraries/power` and `libraries/data` — it imports their classes directly
(`gov.nasa.jpl.aerie.power.*`, `gov.nasa.jpl.aerie.data.*`) and adds the hopper-specific
`SimplePEL` and activities on top. This is the pattern to copy for your own model; see
[USING-IN-YOUR-OWN-REPO.md](../../USING-IN-YOUR-OWN-REPO.md).
