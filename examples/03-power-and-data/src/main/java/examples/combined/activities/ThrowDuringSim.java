package examples.combined.activities;

import examples.combined.Mission;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Test activity that throws a RuntimeException after a configurable delay.
 * Useful for exercising simulation error reporting in the UI.
 */
@ActivityType("ThrowDuringSim")
public class ThrowDuringSim {

  @Parameter
  public long delaySeconds = 1;

  @Parameter
  public String message = "Intentional failure from ThrowDuringSim activity";

  @EffectModel
  public void run(Mission model) {
    delay(Duration.of(delaySeconds, Duration.SECONDS));
    throw new RuntimeException(message);
  }
}
