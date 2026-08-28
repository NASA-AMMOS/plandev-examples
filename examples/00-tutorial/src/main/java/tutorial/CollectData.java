package tutorial;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Validation;


import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static gov.nasa.ammos.plandev.merlin.protocol.types.Duration.SECONDS;

@ActivityType("CollectData")
public class CollectData {

    @Parameter
    public double rate = 10.0; // Mbps

    @Parameter
    public Duration duration = Duration.duration(1, Duration.HOURS);

    @Validation("Collection rate is beyond buffer limit of 100.0 Mbps")
    @Validation.Subject("rate")
    public boolean validateCollectionRate() {
      return rate <= 100.0;
    }

    @ActivityType.EffectModel
    public void run(Mission model) {

        /*
         Collect data at fixed rate over duration of activity
        */
        // Approach 1 - Modify rate at start/end of activity
        DiscreteEffects.increase(model.dataModel.RecordingRate, this.rate);
        delay(duration);
        DiscreteEffects.decrease(model.dataModel.RecordingRate, this.rate);

        // Approach 2 - Non-consumable "using" approach
        // DiscreteEffects.using(model.dataModel.RecordingRate, -this.rate, () -> delay(duration) );
        // delay(duration); (currently not needed, but may be if using becomes a spawn instead of a call)

        /*
        Store data collected over duration of activity to the spacecraft solid state recorder (SSR_Volume)
         */

        //
        // Integration Method 1 - Accumulate all volume at the end of the activity
        //
        // Divide by 1000 to go from Mb->Gb
        DiscreteEffects.increase(model.dataModel.SSR_Volume_Simple,this.rate*duration.ratioOver(SECONDS)/1000.0);

        //
        // Integration Method 2 - Spread out accumulation over many steps (improves resource accuracy during the time span of the
        // activity)
        //
//        int numSteps = 20;
//        Duration step_size = Duration.divide(duration, numSteps);
//        for (int i = 0; i < numSteps; i++) {
//            delay(step_size);
//            DiscreteEffects.increase(model.dataModel.SSR_Volume_MultiStep,this.rate*step_size.ratioOver(SECONDS)/1000.0);
//        }

        //
        // Integration Method 3 - Accumulate data volume upon change to recording rate
        //
//        model.dataModel.increaseRecordingRate(this.rate);
//        delay(duration);
//        model.dataModel.increaseRecordingRate(-this.rate);

    }
}
