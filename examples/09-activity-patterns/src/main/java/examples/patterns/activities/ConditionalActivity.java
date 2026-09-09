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
 * Demonstrates reading current resource state to make decisions.
 *
 * If current power draw exceeds a threshold, the operation is skipped.
 * Otherwise, it performs the operation and increments the operation count.
 */
@ActivityType("ConditionalActivity")
public class ConditionalActivity {

    @Parameter
    public double powerThreshold = 40.0;

    @Parameter
    public long operationDurationMinutes = 10;

    @EffectModel
    public void run(Mission model) {
        double currentPower = currentValue(model.powerDraw);

        if (currentPower > powerThreshold) {
            // Power too high -- skip the operation, just wait
            delay(Duration.of(1, Duration.MINUTES));
        } else {
            // Power is within budget -- perform the operation
            DiscreteEffects.set(model.powerDraw, currentPower + 15.0);
            delay(Duration.of(operationDurationMinutes, Duration.MINUTES));

            // Restore power and record completion
            DiscreteEffects.set(model.powerDraw, currentPower);
            DiscreteEffects.set(model.operationCount, currentValue(model.operationCount) + 1);
        }
    }
}
