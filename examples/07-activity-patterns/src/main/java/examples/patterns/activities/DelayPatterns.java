package examples.patterns.activities;

import examples.patterns.Mission;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

/**
 * Demonstrates the Duration API with different time units.
 *
 * Shows how to use delay() with seconds, minutes, and hours,
 * as well as Duration arithmetic for combining durations.
 */
@ActivityType("DelayPatterns")
public class DelayPatterns {

    @EffectModel
    public void run(Mission model) {
        // Delay in seconds
        DiscreteEffects.set(model.powerDraw, 5.0);
        delay(Duration.of(30, Duration.SECONDS));

        // Delay in minutes
        DiscreteEffects.set(model.powerDraw, 10.0);
        delay(Duration.of(2, Duration.MINUTES));

        // Delay in hours
        DiscreteEffects.set(model.powerDraw, 25.0);
        delay(Duration.of(1, Duration.HOURS));

        // Combined duration using Duration.plus
        DiscreteEffects.set(model.powerDraw, 15.0);
        Duration combined = Duration.of(1, Duration.HOURS).plus(Duration.of(30, Duration.MINUTES));
        delay(combined);

        // Back to zero
        DiscreteEffects.set(model.powerDraw, 0.0);
        DiscreteEffects.set(model.operationCount, currentValue(model.operationCount) + 1);
    }
}
