package examples.combined.activities;

import examples.combined.Mission;
import examples.combined.SimplePEL.TelecomState;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

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
