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
 * One branch handles power monitoring (periodically logging the power draw),
 * while the other branch performs the main instrument operation.
 * Both branches execute in parallel within the simulation.
 */
@ActivityType("ParallelActivities")
public class ParallelActivities {

    @Parameter
    public long operationMinutes = 10;

    @EffectModel
    public void run(Mission model) {
        // Spawn a parallel branch that monitors power by periodically updating
        ModelActions.spawn(() -> monitorPower(model));

        // Main branch: run the instrument operation
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.ACTIVE);
        DiscreteEffects.set(model.powerDraw, 45.0);
        delay(Duration.of(operationMinutes, Duration.MINUTES));

        // Finish the operation
        DiscreteEffects.set(model.instrumentMode, InstrumentMode.IDLE);
        DiscreteEffects.set(model.powerDraw, 0.0);
        DiscreteEffects.set(model.operationCount, currentValue(model.operationCount) + 1);
    }

    private void monitorPower(Mission model) {
        // This runs in parallel with the main branch.
        // Simulate a periodic power monitoring task that runs for a fixed duration.
        for (int i = 0; i < 5; i++) {
            delay(Duration.of(2, Duration.MINUTES));
            // The spawned task can read resource state but should be careful
            // about concurrent writes. Here we just add a small monitoring overhead.
            double current = currentValue(model.powerDraw);
            DiscreteEffects.set(model.powerDraw, current + 0.1);
        }
    }
}
