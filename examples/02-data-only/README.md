# 02 - Data Only Example

A standalone PlanDev mission model demonstrating the data management library. Migrated from [aerie-simple-model-data](https://github.com/NASA-AMMOS/aerie-simple-model-data) (demo module).

## What it models

A spacecraft with two prioritized onboard data bins and configurable storage limits and playback data rates. 
The default configuration provides 10 Gb of storage and 10 Kbps playback rate.

## Activities

From the data library:
- **ChangeDataGenerationRate** - Set a constant data generation rate for a bin
- **GenerateData** - Generate data in a bin at a rate for a duration/volume
- **PlaybackData** - Downlink data with volume or duration goals
- **DeleteData** - Delete data from a bin, optionally limited to already-downlinked data
- **ReprioritizeData** - Move data between bins

Demo-specific:
- **SetPlaybackDataRate** - Change the spacecraft's downlink data rate
- **SetMaxVolume** - Change the onboard storage capacity limit

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `initialMaxVolume` | 1e10 (10 Gb) | Onboard storage limit in bits |
| `initialDatarate` | 1e4 (10 Kbps) | Playback data rate in bits per second |

## Included files

- `DataModelBasicView.json` - PlanDev UI view definition showing data volumes, rates, and downlink tracking
- `sample-plan.json` - Example plan with activities demonstrating all data operations

## Building

```sh
./gradlew :examples:02-data-only:build
```

**Artifact:** `build/libs/02-data-only.jar` — upload directly to PlanDev.

## Try it

The bundled `sample-plan.json` exercises every data operation, so the quickest path is to use
it rather than build a plan by hand:

1. Upload `02-data-only.jar` as a mission model.
2. Import `sample-plan.json` as a plan against that model.
3. Load `DataModelBasicView.json` as a UI view.
4. Simulate, and follow `onboard.volume` as `GenerateData` fills the bins, `PlaybackData`
   drains them, and `DeleteData` clears what has already been downlinked.
5. Add a `SetMaxVolume` partway through and re-simulate to see the storage ceiling move.

Note the registered resource names follow `<bucket>.<property>` — `onboard.volume`,
`onboard.maxVolume`, `scBin0.volume`. Those are the strings constraints and goals reference.

No tests in this example — see [10-testing-patterns](../10-testing-patterns/).
