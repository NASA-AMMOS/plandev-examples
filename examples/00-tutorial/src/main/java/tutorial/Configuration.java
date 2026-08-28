package tutorial;

import static gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Template;

public record Configuration(Double ssrMaxCapacity,
                            long integrationSampleInterval,
                            MagDataCollectionMode startingMagMode) {

  public static final Double SSR_MAX_CAPACITY = 250.0;

  public static final long INTEGRATION_SAMPLE_INTERVAL = 60;

  public static final MagDataCollectionMode STARTING_MAG_MODE = MagDataCollectionMode.OFF;

  public static @Template Configuration defaultConfiguration() {
    return new Configuration(SSR_MAX_CAPACITY,
                             INTEGRATION_SAMPLE_INTERVAL,
                             STARTING_MAG_MODE);
  }
}
