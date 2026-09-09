package examples.resources.activities;

import examples.resources.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.VariableClockEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;

/**
 * Resets the instrument uptime stopwatch to zero and pauses it.
 * Demonstrates the VariableClock resource type: a stopwatch that advances at 1x simulation
 * time while running and 0x while paused. {@code reset} stops it and zeroes the elapsed
 * time (contrast with {@code restart}, which zeroes it and leaves it running).
 */
@ActivityType("ResetTimer")
public class ResetTimer {

    @EffectModel
    public void run(Mission model) {
        VariableClockEffects.reset(model.instrumentUptime);
    }
}
