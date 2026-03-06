# 02 - Data Only Example

A standalone Aerie mission model demonstrating the data management library. Migrated from [aerie-simple-model-data](https://github.com/NASA-AMMOS/aerie-simple-model-data) (demo module).

## What it models

A spacecraft with two prioritized onboard data bins and configurable storage limits and playback data rates. The default configuration provides 10 Gb of storage and 10 Kbps playback rate.

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

## Resources

Includes sample JSON files:
- `DataModelBasicView.json` - Aerie UI view definition showing data volumes, rates, and downlink tracking
- `sample-plan.json` - Example plan with activities demonstrating all data operations

## Building

```sh
./gradlew :examples:02-data-only:build
```

The output JAR at `build/libs/02-data-only.jar` can be uploaded directly to Aerie.
