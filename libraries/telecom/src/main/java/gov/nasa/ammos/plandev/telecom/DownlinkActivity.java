package gov.nasa.ammos.plandev.telecom;

import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Holds the downlink bit rate at a fixed value for a duration, then returns it to zero.
 *
 * <p><strong>Not a usable activity type yet.</strong> The class carries no
 * {@code @ActivityType("...")} annotation, so PlanDev's annotation processor never registers it
 * and it cannot be placed in a plan; nothing in this repo references it. It is scaffold left in
 * place alongside the rest of the experimental telecom library.
 *
 * <p>To make it real: annotate the class {@code @ActivityType("Downlink")}, make the fields and
 * {@code run} public, and decide where {@code bitRate} should come from — the intent (see the
 * inline comment) was to derive it from the link budget rather than take it as a parameter.
 *
 * @see TelecomModel for the library's status and what is missing
 */
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
