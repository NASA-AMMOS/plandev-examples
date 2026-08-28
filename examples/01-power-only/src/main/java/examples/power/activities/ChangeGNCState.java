package examples.power.activities;

import examples.power.models.pel.GNC_State;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import examples.power.Mission;

@ActivityType("ChangeGNCState")
public class ChangeGNCState {
    @Parameter public GNC_State newState = GNC_State.TURNING;

    @EffectModel
    public void run(Mission model) {
        DiscreteEffects.set(model.pel.gncState, newState);
    }
}
