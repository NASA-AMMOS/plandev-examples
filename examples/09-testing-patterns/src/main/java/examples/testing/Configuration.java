package examples.testing;

import static gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Template;

public record Configuration(double initialSOC, int initialDataVolume) {

  public static @Template Configuration defaultConfiguration() {
    return new Configuration(100.0, 0);
  }
}
