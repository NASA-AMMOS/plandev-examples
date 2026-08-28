package examples.data.activities;

import examples.data.Mission;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;

@ActivityType("SetMaxVolume")
public class SetMaxVolume {
  /**
   * The new max volume value
   */
  @Export.Parameter
  public double volume = 1e10; // bits

  @ActivityType.EffectModel
  public void run(Mission model) {
    // change the maxVolume resource to the specified volume immediately
    set(model.maxVolune, volume);
  }
}
