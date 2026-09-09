package examples.patterns.activities;

import examples.patterns.InstrumentMode;
import examples.patterns.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.set;
import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Demonstrates the two resource flavors side by side.
 *
 * Discrete: you set the value, and it stays flat until the next effect.
 * Linear:   you set the rate, and the simulation carries the value. Setting dataVolume
 *           directly would be a mistake -- it is derived from dataRate.
 *
 * In the plots, instrumentMode and operationCount are step functions while dataVolume is a
 * ramp whose slope changes at each rate change. powerDraw is discrete, but batterySoc
 * integrates it, so a discrete input still drives a continuous output.
 */
@ActivityType("DiscreteVsLinearActivity")
public class DiscreteVsLinearActivity {

  @Parameter
  public double lowRateMbps = 0.5;

  @Parameter
  public double highRateMbps = 2.0;

  @Parameter
  public long segmentMinutes = 15;

  @EffectModel
  public void run(Mission model) {
    // Discrete effect: a step change that persists.
    DiscreteEffects.set(model.instrumentMode, InstrumentMode.ACTIVE);
    DiscreteEffects.set(model.powerDraw, 20.0);

    // Linear effect: set a rate, not a value.
    set(model.dataRate, Polynomial.polynomial(lowRateMbps));
    delay(Duration.of(segmentMinutes, Duration.MINUTES));
    // dataVolume has risen by lowRateMbps * segmentMinutes * 60 Mb, on its own.

    // Change the slope; the accumulated volume carries over.
    set(model.dataRate, Polynomial.polynomial(highRateMbps));
    DiscreteEffects.set(model.powerDraw, 45.0);
    delay(Duration.of(segmentMinutes, Duration.MINUTES));

    // Zeroing the rate freezes the volume -- it does not reset it.
    set(model.dataRate, Polynomial.polynomial(0.0));
    DiscreteEffects.set(model.powerDraw, 0.0);
    DiscreteEffects.set(model.instrumentMode, InstrumentMode.IDLE);
    DiscreteEffects.set(model.operationCount, currentValue(model.operationCount) + 1);
  }
}