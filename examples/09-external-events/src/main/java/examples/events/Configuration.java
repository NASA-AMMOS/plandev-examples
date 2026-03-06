package examples.events;

import gov.nasa.jpl.aerie.power.PowerModelSimConfig;

import static gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Template;

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
