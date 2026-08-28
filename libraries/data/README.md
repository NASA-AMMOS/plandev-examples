# Data Library

Reusable data management subsystem model for PlanDev mission models. Migrated from [aerie-simple-model-data](https://github.com/NASA-AMMOS/aerie-simple-model-data) (model module).

## What it models

- **Onboard data storage** with prioritized bins/categories (buckets) and a configurable storage limit
- **Ground data tracking** with corresponding ground buckets that track how much data has been downlinked per bin
- **Data generation** at configurable rates into specific bins
- **Data playback/downlink** with volume or duration goals, respecting bin priority order
- **Data deletion** with optional constraint to only delete already-downlinked data
- **Data reprioritization** between bins

Downlink rate is allocated across bins in priority order (the highest-priority non-empty bin first) on each relevant input change, and each bucket enforces its volume upper bound via cascading child bounds.

## Package

`gov.nasa.ammos.plandev.data`

## Key classes

- `Data` - Main entry point. Constructs onboard and ground bucket hierarchies, wires up downlink logic.
- `Bucket` - A volume container with receive/remove rates, upper bounds, and optional children.
- `DataMissionModel` - Interface that mission models implement to expose the `Data` object to activities.
- Activities: `ChangeDataGenerationRate`, `DeleteData`, `GenerateData`, `PlaybackData`, `ReprioritizeData`
- Mappers: `CommonValueMappers` (Optional, Instant support), `InstantValueMapper`
- Optional downlink telemetry (opt-in; call after `registerStates`): `registerDownlinkTelemetry(registrar, groupSize)` registers behaviour-neutral derived resources for the UI — `onboard.highestDownlinkPriority` (the next bin to downlink), `ground.currentDownlinkPriority` (the bin currently draining), and grouped bin volumes (`onboard.binGroup_SS_EE.volume`, summed in blocks of `groupSize`). The three are also exposed individually as `registerHighestDownlinkPriority`, `registerCurrentDownlinkPriority`, and `registerGroupedBinVolumes`.

## Usage

In your mission model, implement `DataMissionModel` and construct a `Data` object:

```java
public class Mission implements DataMissionModel {
    public Data data;

    public Mission(Registrar registrar, Configuration config) {
        var newRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Throw);
        var maxVolume = asPolynomial(discreteResource(config.maxVolume()));
        this.data = new Data(Optional.of(dataRateResource), numBuckets, maxVolume);
        data.registerStates(newRegistrar);
    }

    @Override
    public Data getData() { return data; }
}
```

In your `build.gradle`:

```gradle
dependencies {
    implementation project(':libraries:data')
}
```

## Activity metadata (units & subsystem)

The activities carry PlanDev metadata annotations:

- **Units** — numeric parameters are annotated with `@Unit` (`bit`, `bit/s`). **To use these
  activities your `@MissionModel` package-info must declare the metadata annotation**, or
  value-mapper generation fails:
  ```java
  @WithMetadata(name = "unit", annotation = gov.nasa.ammos.plandev.contrib.metadata.Unit.class)
  ```
  (Resource units — bucket volumes/rates — are attached at registration and need no such
  declaration.)
- **Subsystem** — each activity is tagged `@Subsystem("data")`. This is inert unless the
  consuming model declares the subsystem, in which case the activities group under it:
  ```java
  @WithSubsystem("data")
  ```
  (Declaring it is optional; omitting it does not break the build.)

See `examples/04-hopper` and `examples/05-orbiter` for both in use.

## Building

```sh
./gradlew :libraries:data:build
```
