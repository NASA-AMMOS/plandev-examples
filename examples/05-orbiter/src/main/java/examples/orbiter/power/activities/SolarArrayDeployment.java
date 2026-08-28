package examples.orbiter.power.activities;

import examples.orbiter.Mission;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.power.ArrayDeploymentStates;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

@ActivityType("SolarArrayDeployment")
@Subsystem("power")
public class SolarArrayDeployment {

   @Parameter
   public double deployDuration = 30; // minutes

    @EffectModel
    public void run(Mission model) {
        model.array.setSolarArrayDeploymentState(ArrayDeploymentStates.DEPLOYING);
        delay(Duration.roundNearest(deployDuration, Duration.MINUTES));
        model.array.setSolarArrayDeploymentState(ArrayDeploymentStates.DEPLOYED);
    }
}
