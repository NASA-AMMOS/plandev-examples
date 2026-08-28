package examples.patterns.activities;

import examples.patterns.InstrumentMode;
import examples.patterns.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Demonstrates mode transitions through a state machine:
 * IDLE -> WARMUP -> ACTIVE -> COOLDOWN -> IDLE
 *
 * Each transition includes a delay and updates the power draw accordingly.
 */
@ActivityType("StateMachineActivity")
public class StateMachineActivity {

    @Parameter
    public long warmupMinutes = 5;

    @Parameter
    public long activeMinutes = 30;

    @Parameter
    public long cooldownMinutes = 3;

    @EffectModel
    public void run(Mission model) {
        // IDLE -> WARMUP
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.WARMUP);
        DiscreteEffects.set(model.powerDraw, 10.0);
        delay(Duration.of(warmupMinutes, Duration.MINUTES));

        // WARMUP -> ACTIVE
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.ACTIVE);
        DiscreteEffects.set(model.powerDraw, 50.0);
        delay(Duration.of(activeMinutes, Duration.MINUTES));

        // ACTIVE -> COOLDOWN
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.COOLDOWN);
        DiscreteEffects.set(model.powerDraw, 5.0);
        delay(Duration.of(cooldownMinutes, Duration.MINUTES));

        // COOLDOWN -> IDLE
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.IDLE);
        DiscreteEffects.set(model.powerDraw, 0.0);
    }
}
