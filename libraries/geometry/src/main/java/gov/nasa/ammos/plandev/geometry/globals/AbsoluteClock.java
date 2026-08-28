package gov.nasa.ammos.plandev.geometry.globals;

import gov.nasa.ammos.plandev.contrib.streamline.core.Resources;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

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
