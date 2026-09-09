package examples.patterns.activities;

import examples.patterns.InstrumentMode;
import examples.patterns.Mission;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/** Uses simulation configuration for its power draw and duration. */
@ActivityType("ConfigurationDrivenActivity")
public class ConfigurationDrivenActivity {
  @EffectModel
  public void run(Mission model) {
    set(model.instrumentMode, InstrumentMode.ACTIVE);
    set(model.powerDraw, model.configuration.configuredPowerDrawWatts());
    delay(Duration.of(model.configuration.configuredOperationDurationMinutes(), Duration.MINUTES));
    set(model.instrumentMode, InstrumentMode.IDLE);
    set(model.powerDraw, 0.0);
    set(model.operationCount, currentValue(model.operationCount) + 1);
  }
}
