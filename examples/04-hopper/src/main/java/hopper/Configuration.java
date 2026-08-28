package hopper;

import gov.nasa.ammos.plandev.power.PowerModelSimConfig;

import static gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Template;

public record Configuration(
    PowerModelSimConfig powerConfig,
    double initialMaxVolume,
    double initialDataRate
) {
  public static @Template Configuration defaultConfiguration() {
    return new Configuration(
        PowerModelSimConfig.defaultConfiguration(),
        1e10,  // 10 Gb
        1e4    // 10 Kbps
    );
  }
}
