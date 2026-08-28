package examples.data.activities;

import examples.data.Mission;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;

@ActivityType("SetPlaybackDataRate")
public class SetPlaybackDataRate {
  /**
   * The new data rate value
   */
  @Export.Parameter
  public double rate = 0.0; // bits per second (bps)

  @ActivityType.EffectModel
  public void run(Mission model) {
    // change the data rate resource to the specified rate immediately
    set(model.dataRate, rate);
  }
}
