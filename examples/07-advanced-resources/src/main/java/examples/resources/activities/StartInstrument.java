package examples.resources.activities;

import examples.resources.InstrumentState;
import examples.resources.Mission;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.clocks.ClockEffects;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.contrib.streamline.core.MutableResource.set;
import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

/**
 * Turns an instrument on, demonstrating:
 * - Discrete effect: set instrument state to ON
 * - Polynomial effect: set power draw as a polynomial (constant + warmup rate)
 * - Polynomial effect: set data collection rate
 * - Clock effect: restart the uptime timer
 *
 * The instrument stays on for the specified duration, then shuts off.
 * Use StopInstrument to turn it off earlier, or omit duration for indefinite operation.
 */
@ActivityType("StartInstrument")
public class StartInstrument {

    @Parameter
    public double powerW = 25.0;

    @Parameter
    public double warmupRateWPerSec = 0.001;

    @Parameter
    public double dataRateMbps = 10.0;

    @Parameter
    public long durationHours = 4;

    @EffectModel
    public void run(Mission model) {
        // Discrete: set state to ON
        DiscreteEffects.set(model.instrumentState, InstrumentState.ON);

        // Polynomial: set power draw with warmup.
        // polynomial(25.0, 0.001) means power = 25 + 0.001*t (watts, where t is in seconds)
        set(model.instrumentPowerDraw, Polynomial.polynomial(powerW, warmupRateWPerSec));

        // Polynomial: set data rate (constant rate in Mb/s)
        set(model.dataRate, Polynomial.polynomial(dataRateMbps));

        // Clock: restart uptime timer from zero
        ClockEffects.restart(model.instrumentUptime);

        // Hold for specified duration
        delay(Duration.of(durationHours, Duration.HOURS));

        // Turn off after duration
        DiscreteEffects.set(model.instrumentState, InstrumentState.OFF);
        set(model.instrumentPowerDraw, Polynomial.polynomial(0.0));
        set(model.dataRate, Polynomial.polynomial(0.0));
    }
}
