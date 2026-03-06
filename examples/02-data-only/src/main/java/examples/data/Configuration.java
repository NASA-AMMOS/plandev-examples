package examples.data;

import static gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Template;

public record Configuration(double initialMaxVolume, double initialDatarate) {
  public static @Template Configuration defaultConfiguration() {
    return new Configuration(1e10, 1e4); // 10 Gb and 10 Kbps
  }
}
