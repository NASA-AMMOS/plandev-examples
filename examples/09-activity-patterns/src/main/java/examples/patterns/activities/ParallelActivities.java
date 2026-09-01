package examples.patterns.activities;

import examples.patterns.InstrumentMode;
import examples.patterns.Mission;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.ModelActions;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Demonstrates using spawn() to run two sub-tasks concurrently.
 *
 * <p>One branch performs the main instrument operation; the other samples the
 * power draw while that operation runs. Both execute in parallel within the
 * simulation.
 *
 * <p><b>The pattern to copy here is the division of writes.</b> Two branches
 * running at the same simulated instant have no guaranteed ordering, so if both
 * wrote the same resource the final value would depend on which ran last. The
 * monitoring branch therefore <i>reads</i> the shared resource ({@code powerDraw})
 * and <i>writes</i> only a resource it owns ({@code peakPowerDraw}), which makes
 * the result deterministic however the branches interleave.
 */
@ActivityType("ParallelActivities")
public class ParallelActivities {

    @Parameter
    public long operationMinutes = 10;

    @EffectModel
    public void run(Mission model) {
        // Spawn a parallel branch that samples power while the operation runs
        ModelActions.spawn(() -> monitorPower(model));

        // Main branch: run the instrument operation. It is the only writer of
        // instrumentMode / powerDraw / operationCount.
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.ACTIVE);
        DiscreteEffects.set(model.powerDraw, 45.0);
        delay(Duration.of(operationMinutes, Duration.MINUTES));

        // Finish the operation
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.IDLE);
        DiscreteEffects.set(model.powerDraw, 0.0);
        DiscreteEffects.set(model.operationCount, currentValue(model.operationCount) + 1);
    }

    /**
     * Samples powerDraw every two minutes for as long as the operation runs.
     *
     * <p>The first sample is offset by one minute so a read never lands on the exact
     * instant of one of the main branch's writes — legal, but it would tell you
     * nothing useful about which value you got.
     */
    private void monitorPower(Mission model) {
        final Duration period = Duration.of(2, Duration.MINUTES);
        final Duration operation = Duration.of(operationMinutes, Duration.MINUTES);

        Duration elapsed = Duration.of(1, Duration.MINUTES);
        delay(elapsed);

        while (elapsed.shorterThan(operation)) {
            // Read shared state, but write only a resource this branch owns.
            double observed = currentValue(model.powerDraw);
            if (observed > currentValue(model.peakPowerDraw)) {
                DiscreteEffects.set(model.peakPowerDraw, observed);
            }

            delay(period);
            elapsed = elapsed.plus(period);
        }
    }
}
