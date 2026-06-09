package hopper.activities;

import hopper.Mission;
import hopper.SimplePEL.TelecomState;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;
import gov.nasa.jpl.aerie.data.activities.DeleteData;
import gov.nasa.jpl.aerie.data.activities.PlaybackData;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Subsystem;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;

import java.util.Optional;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;
import static hopper.generated.ActivityActions.spawn;
import static hopper.generated.ActivityActions.spawn;
/**
 * Turns on the telecom subsystem for a specified duration, 
 * spawn a PlaybackData activity to model data downlink, 
 * waits for the duration to elapse,
 * spawn a DeleteData activity to model data deletion after downlink,
 * and then turns off the telecom subsystem.
 */
@ActivityType("Downlink")
@Subsystem("telecom")
public class Downlink {

  @Parameter
  public Duration duration = Duration.HOUR;

  public Downlink() {}

  public Downlink(Duration duration) {
    this.duration = duration;
  }
  
  @EffectModel
  public void run(Mission model) {
    // Set telecom state to on
    DiscreteEffects.set(model.pel.telecomState, TelecomState.ON);
    
    // Spawn PlaybackData activity to model data downlink
    spawn(model, new PlaybackData(duration));

    // Wait for the duration to elapse
    delay(duration);

    // Spawn DeleteData activity to model data deletion after downlink
    for(int i = 0; i < model.data.onboardBuckets.size(); ++i){
      spawn(model, new DeleteData(Double.MAX_VALUE, true, i));
    }

    // Set telecom state to off
    DiscreteEffects.set(model.pel.telecomState, TelecomState.OFF);
  }
}
