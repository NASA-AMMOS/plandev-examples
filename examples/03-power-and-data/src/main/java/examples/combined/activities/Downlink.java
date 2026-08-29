package examples.combined.activities;

import examples.combined.Mission;
import examples.combined.SimplePEL.TelecomState;
import gov.nasa.ammos.plandev.data.activities.PlaybackData;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static examples.combined.generated.ActivityActions.spawn;

/**
 * Turns on the telecom subsystem and plays back onboard data for the
 * specified duration.
 */
@ActivityType("Downlink")
public class Downlink {

  @Parameter
  public long durationHours = 1;

  @EffectModel
  public void run(Mission model) {
    var duration = Duration.of(durationHours, Duration.HOURS);

    DiscreteEffects.set(model.pel.telecomState, TelecomState.ON);
    spawn(model, new PlaybackData(duration));
    delay(duration);
    DiscreteEffects.set(model.pel.telecomState, TelecomState.OFF);
  }

}
