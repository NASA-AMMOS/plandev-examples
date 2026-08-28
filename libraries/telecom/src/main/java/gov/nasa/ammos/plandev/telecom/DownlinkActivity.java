package gov.nasa.ammos.plandev.telecom;

import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

public class DownlinkActivity {

    @Export.Parameter
    Duration duration;

    @Export.Parameter
    double bitRate;

    @ActivityType.ControllableDuration(parameterName = "duration")
    void run(TelecomModel model) {
        // Send data from s/c to ground

        // Get bit rate either from parameter or by a calculation from downlink bit rate capability

        set(model.downlinkBitRate, bitRate);
        delay(duration);
        set(model.downlinkBitRate, 0.0);



//        dataModel.beginDownlink(bitRate);

//        dataModel.endDownlink();
        // using(null, biteRate * duration)

//        using(model.dataModel.RecordingRate, -this.rate, () -> delay(duration) );

    }
}
