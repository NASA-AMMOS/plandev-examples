package examples.combined.activities;

import examples.combined.Mission;
import examples.combined.SimplePEL.TelecomState;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Turns on the telecom subsystem for a specified duration.
 * Use alongside PlaybackData (from the data library) to model
 * power draw during data downlink.
 */
@ActivityType("Downlink")
public class Downlink {

  @Parameter
  public long durationHours = 1;

  @EffectModel
  public void run(Mission model) {
    DiscreteEffects.set(model.pel.telecomState, TelecomState.ON);
    delay(Duration.of(durationHours, Duration.HOURS));
    DiscreteEffects.set(model.pel.telecomState, TelecomState.OFF);
  }
}
