# PlanDev Activity Recipes

Copy-paste patterns for common mission modeling tasks. Each recipe shows the minimal code needed — adapt to your mission.

## Table of Contents

- [State Machines](#state-machines)
- [Conditional Logic](#conditional-logic)
- [Looping Activities](#looping-activities)
- [Spawning Parallel Activities](#spawning-parallel-activities)
- [Resource-Gated Execution](#resource-gated-execution)
- [Duration-Limited Activities](#duration-limited-activities)
- [Configuration-Driven Behavior](#configuration-driven-behavior)
- [Discrete vs Linear Resources](#discrete-vs-linear-resources)

---

## State Machines

Model mode transitions like IDLE -> WARMUP -> ACTIVE -> COOLDOWN -> IDLE:

```java
@ActivityType("InstrumentOperation")
public class InstrumentOperation {
  @Parameter
  public Duration warmupDuration = Duration.of(5, Duration.MINUTES);

  @EffectModel
  public void run(Mission mission) {
    mission.instrumentMode.set("WARMUP");
    delay(warmupDuration);

    mission.instrumentMode.set("ACTIVE");
    delay(Duration.of(30, Duration.MINUTES));

    mission.instrumentMode.set("COOLDOWN");
    delay(Duration.of(2, Duration.MINUTES));

    mission.instrumentMode.set("IDLE");
  }
}
```

## Conditional Logic

Branch behavior based on resource state:

```java
@ActivityType("ConditionalDownlink")
public class ConditionalDownlink {
  @Parameter
  public double dataThreshold = 100.0; // MB

  @EffectModel
  public void run(Mission mission) {
    double currentData = mission.dataVolume.get();

    if (currentData > dataThreshold) {
      // High-rate downlink
      mission.dataRate.set(-50.0); // MB/hr
      delay(Duration.of(2, Duration.HOURS));
      mission.dataRate.set(0.0);
    } else {
      // Low-rate housekeeping only
      mission.dataRate.set(-5.0);
      delay(Duration.of(30, Duration.MINUTES));
      mission.dataRate.set(0.0);
    }
  }
}
```

## Looping Activities

Repeat an operation N times with delays:

```java
@ActivityType("ScanSequence")
public class ScanSequence {
  @Parameter
  public int numScans = 5;

  @Parameter
  public Duration scanDuration = Duration.of(10, Duration.MINUTES);

  @Parameter
  public Duration pauseBetweenScans = Duration.of(2, Duration.MINUTES);

  @EffectModel
  public void run(Mission mission) {
    for (int i = 0; i < numScans; i++) {
      mission.instrumentMode.set("SCANNING");
      mission.powerDraw.add(15.0); // watts
      delay(scanDuration);

      mission.instrumentMode.set("IDLE");
      mission.powerDraw.add(-15.0);

      if (i < numScans - 1) {
        delay(pauseBetweenScans);
      }
    }
  }
}
```

## Spawning Parallel Activities

Run multiple operations concurrently using `spawn()`:

```java
@ActivityType("ScienceObservation")
public class ScienceObservation {
  @EffectModel
  public void run(Mission mission) {
    // Start data collection and thermal management in parallel
    spawn(new CollectData(Duration.of(1, Duration.HOURS)));
    spawn(new HeaterControl("INSTRUMENT_A"));

    // This activity completes immediately — children run independently
    // Use call() instead of spawn() if you need to wait for completion
  }
}
```

Use `call()` to wait for a child activity to finish before continuing:

```java
@ActivityType("CalibrateAndObserve")
public class CalibrateAndObserve {
  @EffectModel
  public void run(Mission mission) {
    // Wait for calibration to finish first
    call(new Calibrate());

    // Then start observation
    call(new Observe(Duration.of(30, Duration.MINUTES)));
  }
}
```

## Resource-Gated Execution

Wait until a resource reaches a required value:

```java
@ActivityType("PowerGatedOperation")
public class PowerGatedOperation {
  @Parameter
  public double requiredSOC = 0.8; // 80% state of charge

  @EffectModel
  public void run(Mission mission) {
    // Wait until battery has enough charge
    waitUntil(greaterThanOrEqual(mission.batterySOC, requiredSOC));

    // Now safe to run power-hungry operation
    mission.powerDraw.add(100.0);
    delay(Duration.of(1, Duration.HOURS));
    mission.powerDraw.add(-100.0);
  }
}
```

## Duration-Limited Activities

Set a maximum duration with early termination:

```java
@ActivityType("TimedExperiment")
public class TimedExperiment {
  @Parameter
  public Duration maxDuration = Duration.of(2, Duration.HOURS);

  @Parameter
  public double targetDataVolume = 500.0; // MB

  @EffectModel
  public void run(Mission mission) {
    mission.instrumentMode.set("COLLECTING");
    mission.dataRate.set(10.0); // MB/hr

    // Wait for either: enough data collected OR timeout
    // In practice, use delay() for the max duration
    // and check data volume in a scheduling constraint
    delay(maxDuration);

    mission.instrumentMode.set("IDLE");
    mission.dataRate.set(0.0);
  }
}
```

## Configuration-Driven Behavior

Use simulation configuration to parameterize the model:

```java
// Configuration.java — define what operators can tune per-plan
@AutoValueMapper
public record Configuration(
    @Template("Initial battery charge (0.0-1.0)")
    double initialBatterySOC,

    @Template("Solar array area in m^2")
    double solarArrayArea,

    @Template("Downlink rate in Mbps")
    double downlinkRate
) {
  public static final Configuration DEFAULT = new Configuration(1.0, 10.0, 2.0);
}

// Mission.java — use configuration values
public class Mission {
  public Mission(Registrar registrar, Configuration config) {
    this.batterySOC = registrar.real("batterySOC");
    this.batterySOC.set(config.initialBatterySOC());

    this.solarArrayArea = config.solarArrayArea();
    this.downlinkRate = config.downlinkRate();
  }
}
```

## Discrete vs Linear Resources

**Discrete resources** change at specific points in time (modes, flags, counts):

```java
// In your Mission or model class
public final MutableResource<String> instrumentMode =
    resource("instrumentMode", discrete("IDLE"));

public final MutableResource<Integer> imageCount =
    resource("imageCount", discrete(0));

// In an activity
mission.instrumentMode.set("ACTIVE");
mission.imageCount.set(mission.imageCount.get() + 1);
```

**Linear resources** change continuously over time (power draw, data volume, temperature):

```java
// In your Mission or model class — polynomial resource
public final MutableResource<Double> dataVolume =
    resource("dataVolume", polynomial(0.0));

public final MutableResource<Double> dataRate =
    resource("dataRate", polynomial(0.0));

// In an activity — set the rate, not the value
mission.dataRate.set(10.0);  // 10 MB/hr accumulation
delay(Duration.of(2, Duration.HOURS));
// dataVolume is now 20 MB higher
mission.dataRate.set(0.0);
```

---

For complete working examples, see the numbered directories in `examples/`. Each one has a README explaining the concepts it demonstrates.
