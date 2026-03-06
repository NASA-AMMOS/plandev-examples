package examples.events.activities;

import examples.events.Mission;
import examples.events.SimplePEL.CameraState;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

/**
 * Takes a picture, turning on the camera (power draw) and generating science data.
 */
@ActivityType("TakePicture")
public class TakePicture {

  @Parameter
  public long durationSeconds = 60;

  @Parameter
  public double dataRateBps = 5e6; // 5 Mbps

  @Parameter
  public int bin = 0;

  @EffectModel
  public void run(Mission model) {
    // Turn on camera (power impact)
    DiscreteEffects.set(model.pel.cameraState, CameraState.ON);

    // Generate science data into onboard storage
    var binToChange = model.data.getOnboardBin(bin);
    var dur = Duration.of(durationSeconds, Duration.SECONDS);
    binToChange.receive(dataRateBps, dur);

    // Wait for imaging duration
    delay(dur);

    // Turn off camera
    DiscreteEffects.set(model.pel.cameraState, CameraState.OFF);
  }
}
