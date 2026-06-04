package examples.resources.activities;

import examples.resources.InstrumentState;
import examples.resources.Mission;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;

import static gov.nasa.jpl.aerie.contrib.streamline.core.MutableResource.set;

/**
 * Turns an instrument off immediately.
 * - Sets instrument state to OFF (Discrete)
 * - Zeros out power draw (Polynomial)
 * - Zeros out data rate (Polynomial)
 * - Does NOT reset the uptime clock (it keeps counting from last start)
 */
@ActivityType("StopInstrument")
public class StopInstrument {

    @EffectModel
    public void run(Mission model) {
        DiscreteEffects.set(model.instrumentState, InstrumentState.OFF);
        set(model.instrumentPowerDraw, Polynomial.polynomial(0.0));
        set(model.dataRate, Polynomial.polynomial(0.0));
    }
}
