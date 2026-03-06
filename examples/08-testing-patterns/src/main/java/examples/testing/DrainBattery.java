package examples.testing;

import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;

import static gov.nasa.jpl.aerie.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;
import static gov.nasa.jpl.aerie.merlin.protocol.types.Duration.HOURS;
import static gov.nasa.jpl.aerie.merlin.protocol.types.Duration.duration;

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
