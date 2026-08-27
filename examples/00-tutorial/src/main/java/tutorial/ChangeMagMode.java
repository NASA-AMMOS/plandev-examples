package tutorial;

import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export;

import static gov.nasa.jpl.aerie.contrib.streamline.core.Resources.currentValue;

@ActivityType("ChangeMagMode")
public class ChangeMagMode {

    @Export.Parameter
    public MagDataCollectionMode mode = MagDataCollectionMode.LOW_RATE;

    @ActivityType.EffectModel
    public void run(Mission model) {
         double currentRate = currentValue(model.dataModel.MagDataRate);
         double newRate = mode.getDataRate();
         // Divide by 10^6 for bps->Mbps conversion
         DiscreteEffects.increase(model.dataModel.RecordingRate, (newRate-currentRate)/1.0e3);
         DiscreteEffects.set(model.dataModel.MagDataMode, mode);
    }
}
