package examples.testing;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static gov.nasa.ammos.plandev.merlin.protocol.types.Duration.HOURS;
import static gov.nasa.ammos.plandev.merlin.protocol.types.Duration.duration;

@ActivityType("DrainBattery")
public class DrainBattery {

  @Parameter
  public double amount = 10.0;

  @ActivityType.EffectModel
  public void run(final Mission model) {
    DiscreteEffects.set(model.batterySOC, currentValue(model.batterySOC) - amount);
    delay(duration(1, HOURS));
  }
}
