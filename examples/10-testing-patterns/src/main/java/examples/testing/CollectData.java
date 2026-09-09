package examples.testing;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static gov.nasa.ammos.plandev.merlin.protocol.types.Duration.MINUTES;
import static gov.nasa.ammos.plandev.merlin.protocol.types.Duration.duration;

@ActivityType("CollectData")
public class CollectData {

  @Parameter
  public int volume = 100;

  @ActivityType.EffectModel
  public void run(final Mission model) {
    DiscreteEffects.set(model.dataVolume, currentValue(model.dataVolume) + volume);
    delay(duration(30, MINUTES));
  }
}
