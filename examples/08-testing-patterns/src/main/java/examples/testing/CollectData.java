package examples.testing;

import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;

import static gov.nasa.jpl.aerie.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;
import static gov.nasa.jpl.aerie.merlin.protocol.types.Duration.MINUTES;
import static gov.nasa.jpl.aerie.merlin.protocol.types.Duration.duration;

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
