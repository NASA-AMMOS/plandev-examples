package examples.resources.activities;

import examples.resources.Mission;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.clocks.ClockEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;

/**
 * Resets the instrument uptime clock to zero.
 * Demonstrates the Clock resource type: a clock automatically advances
 * with simulation time, and can be restarted to zero.
 */
@ActivityType("ResetTimer")
public class ResetTimer {

    @EffectModel
    public void run(Mission model) {
        ClockEffects.restart(model.instrumentUptime);
    }
}
