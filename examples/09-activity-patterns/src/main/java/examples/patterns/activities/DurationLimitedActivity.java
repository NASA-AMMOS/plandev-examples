package examples.patterns.activities;

import examples.patterns.InstrumentMode;
import examples.patterns.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.ClockResources;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialEffects.restoring;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.greaterThanOrEquals;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.waitUntil;

/** Collects data until the target volume is reached or the duration limit expires. */
@ActivityType("DurationLimitedActivity")
public class DurationLimitedActivity {
  @Parameter
  public long maxDurationMinutes = 120;

  @Parameter
  public double targetDataVolumeMb = 500.0;

  @Parameter
  public double collectionRateMbPerHour = 300.0;

  @EffectModel
  public void run(Mission model) {
    if (collectionRateMbPerHour <= 0) {
      throw new IllegalArgumentException("collectionRateMbPerHour must be positive");
    }

    if (currentValue(model.dataVolume) >= targetDataVolumeMb) return;

    final Duration deadline = currentValue(model.simulationClock)
        .plus(Duration.of(maxDurationMinutes, Duration.MINUTES));
    // create boolean discrete resources for conditions of "reached target" and "reached duration limit"
    final var targetReached = greaterThanOrEquals(model.dataVolume, targetDataVolumeMb);
    final var durationLimitReached = ClockResources.greaterThanOrEquals(
        model.simulationClock,
        DiscreteResources.constant(deadline));
    // create an "or" boolean resource that is true when either resource is true
    final var shouldStop = DiscreteResources.or(targetReached, durationLimitReached);

    set(model.instrumentMode, InstrumentMode.ACTIVE);
    set(model.powerDraw, 45.0);
    restoring(model.dataVolume, collectionRateMbPerHour / 3600, () ->
        waitUntil(DiscreteResources.when(shouldStop)));
    set(model.instrumentMode, InstrumentMode.IDLE);
    set(model.powerDraw, 0.0);
    set(model.operationCount, currentValue(model.operationCount) + 1);
  }
}
