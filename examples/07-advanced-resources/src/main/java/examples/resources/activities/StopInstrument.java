package examples.resources.activities;

import examples.resources.InstrumentState;
import examples.resources.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.VariableClockEffects;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.set;

/**
 * Turns an instrument off immediately.
 * - Sets instrument state to OFF (Discrete)
 * - Zeros out power draw (Polynomial)
 * - Zeros out data rate (Polynomial)
 * - Pauses the uptime stopwatch (VariableClock) so it freezes at the elapsed on-time
 *   rather than resetting it — use ResetTimer to zero it
 */
@ActivityType("StopInstrument")
public class StopInstrument {

    @EffectModel
    public void run(Mission model) {
        DiscreteEffects.set(model.instrumentState, InstrumentState.OFF);
        set(model.instrumentPowerDraw, Polynomial.polynomial(0.0));
        set(model.dataRate, Polynomial.polynomial(0.0));
        VariableClockEffects.pause(model.instrumentUptime);
    }
}
