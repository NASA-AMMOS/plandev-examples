package examples.patterns;

import static gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Template;

public record Configuration(
    double initialDataVolumeMb,
    double configuredPowerDrawWatts,
    long configuredOperationDurationMinutes
) {
  public static @Template Configuration defaultConfiguration() {
    return new Configuration(0.0, 35.0, 20);
  }
}
