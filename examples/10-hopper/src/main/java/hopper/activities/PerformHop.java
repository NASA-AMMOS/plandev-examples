package hopper.activities;

import hopper.Mission;
import hopper.SimplePEL.HopState;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

/**
 * Perform a hop which activates hop mode and draws power for the duration of the hop.
 */
@ActivityType("PerformHop")
public class PerformHop {

  @Parameter
  public long durationSeconds = 300;

  @Parameter
  public double dataRateBps = 5e6; // 5 Mbps

  @Parameter
  public int bin = 0;

  @EffectModel
  public void run(Mission model) {
    // Turn on hop mode (power impact)
    DiscreteEffects.set(model.pel.hopState, HopState.ON);

    // Generate data into onboard storage
    var binToChange = model.data.getOnboardBin(bin);
    var dur = Duration.of(durationSeconds, Duration.SECONDS);
    binToChange.receive(dataRateBps, dur);

    // Wait for hop duration
    delay(dur);

    // Turn off hop mode
    DiscreteEffects.set(model.pel.hopState, HopState.OFF);
  }
}
