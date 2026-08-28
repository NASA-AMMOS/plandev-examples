package examples.power.activities;

import examples.power.models.pel.Camera_State;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import examples.power.Mission;

@ActivityType("TurnOnCamera")
public class TurnOnCamera {
    @Parameter public long duration = 10;

    @EffectModel
    public void run(Mission model) {
        DiscreteEffects.set(model.pel.cameraState, Camera_State.ON);
        delay(Duration.of(duration, Duration.HOURS));
        DiscreteEffects.set(model.pel.cameraState,Camera_State.OFF);
    }
}
