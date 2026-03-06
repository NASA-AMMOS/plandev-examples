package gov.nasa.jpl.aerie.geometry.globals;

import gov.nasa.jpl.aerie.contrib.streamline.core.Resources;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import java.time.Instant;

public class AbsoluteClock {

  private Instant startTime;

  public AbsoluteClock(final Instant startTime) {
    this.startTime = startTime;
  }

  public Instant now() {
    return startTime.plusMillis(Resources.currentTime().in(Duration.MILLISECONDS));
  }

}
