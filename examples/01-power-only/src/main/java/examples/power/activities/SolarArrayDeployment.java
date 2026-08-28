package examples.power.activities;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import examples.power.Mission;
import gov.nasa.ammos.plandev.power.ArrayDeploymentStates;
import gov.nasa.ammos.plandev.power.GenericSolarArray;

@ActivityType("SolarArrayDeployment")
public class SolarArrayDeployment {

   @Parameter
   public double deployDuration = 30; // minutes

    @EffectModel
    public void run(Mission model) {
        if (model.powerSource instanceof GenericSolarArray) {
            ((GenericSolarArray) model.powerSource).setSolarArrayDeploymentState(ArrayDeploymentStates.DEPLOYING);
            delay(Duration.roundNearest(deployDuration, Duration.MINUTES));
            ((GenericSolarArray) model.powerSource).setSolarArrayDeploymentState(ArrayDeploymentStates.DEPLOYED);
        }
    }
}
