package examples.patterns.activities;

import examples.patterns.InstrumentMode;
import examples.patterns.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources.when;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.waitUntil;

/** Waits for the instrument to become idle before starting an operation. */
@ActivityType("ResourceGatedActivity")
public class ResourceGatedActivity {
  @Parameter
  public long operationDurationMinutes = 10;

  @EffectModel
  public void run(Mission model) {
    waitUntil(when(DiscreteResources.equals(
        model.instrumentMode,
        DiscreteResources.constant(InstrumentMode.IDLE))));

    set(model.instrumentMode, InstrumentMode.ACTIVE);
    set(model.powerDraw, 50.0);
    delay(Duration.of(operationDurationMinutes, Duration.MINUTES));
    set(model.instrumentMode, InstrumentMode.IDLE);
    set(model.powerDraw, 0.0);
    set(model.operationCount, currentValue(model.operationCount) + 1);
  }
}
