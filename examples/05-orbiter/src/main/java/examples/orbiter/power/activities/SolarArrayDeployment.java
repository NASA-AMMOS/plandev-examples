package examples.orbiter.power.activities;

import examples.orbiter.Mission;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;
import gov.nasa.jpl.aerie.power.ArrayDeploymentStates;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

@ActivityType("SolarArrayDeployment")
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
