package hopper.activities;

import hopper.Mission;
import hopper.SimplePEL.HopState;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

/**
 * Perform a hop which activates hop mode and draws power for the duration of the hop.
 */
@ActivityType("PerformHop")
@Subsystem("mobility")
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

    // Generate data into onboard storage. receive(rate, dur) is a blocking
    // call: it turns the receive rate on, waits for the full duration while
    // data accumulates, then turns the rate back off. So this both produces the
    // data and provides the hop delay -- no extra delay needed.
    var binToChange = model.data.getOnboardBin(bin);
    var dur = Duration.of(durationSeconds, Duration.SECONDS);
    binToChange.receive(dataRateBps, dur);

    // Turn off hop mode
    DiscreteEffects.set(model.pel.hopState, HopState.OFF);
  }
}
