package examples.patterns.activities;

import examples.patterns.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Demonstrates repeating an operation N times with a delay between iterations.
 *
 * Each iteration increments the operationCount resource and includes a brief
 * power spike during the operation.
 */
@ActivityType("LoopedActivity")
public class LoopedActivity {

    @Parameter
    public int repetitions = 5;

    @Parameter
    public long delayBetweenSeconds = 30;

    @EffectModel
    public void run(Mission model) {
        for (int i = 0; i < repetitions; i++) {
            // Perform one operation
            DiscreteEffects.set(model.powerDraw, 20.0);
            delay(Duration.of(10, Duration.SECONDS));

            // Operation complete
            DiscreteEffects.set(model.powerDraw, 0.0);
            DiscreteEffects.set(model.operationCount, currentValue(model.operationCount) + 1);

            // Wait between iterations (skip delay after last iteration)
            if (i < repetitions - 1) {
                delay(Duration.of(delayBetweenSeconds, Duration.SECONDS));
            }
        }
    }
}
