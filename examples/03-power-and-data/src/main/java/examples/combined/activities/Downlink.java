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
 *
 * <p>{@code durationHours} is fractional so a downlink can be sized to a real
 * contact window — DSN passes are rarely a whole number of hours. See
 * {@code examples/07-external-events}, whose scheduling goal derives this value
 * from each contact's interval.
 */
@ActivityType("Downlink")
public class Downlink {

  @Parameter
  public double durationHours = 1.0;

  @EffectModel
  public void run(Mission model) {
    // Converted via seconds so fractional hours survive (1.5 -> 01:30:00)
    var duration = Duration.of(Math.round(durationHours * 3600), Duration.SECONDS);

    DiscreteEffects.set(model.pel.telecomState, TelecomState.ON);
    spawn(model, new PlaybackData(duration));
    delay(duration);
    DiscreteEffects.set(model.pel.telecomState, TelecomState.OFF);
  }

}
