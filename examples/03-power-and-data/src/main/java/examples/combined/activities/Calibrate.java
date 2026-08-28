package examples.combined.activities;

import examples.combined.Mission;
import examples.combined.SimplePEL.CameraState;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * Instrument calibration activity. Turns on the camera briefly to
 * perform a calibration sequence.
 */
@ActivityType("Calibrate")
public class Calibrate {

  @Parameter
  public long durationMinutes = 30;

  @EffectModel
  public void run(Mission model) {
    DiscreteEffects.set(model.pel.cameraState, CameraState.ON);
    delay(Duration.of(durationMinutes, Duration.MINUTES));
    DiscreteEffects.set(model.pel.cameraState, CameraState.OFF);
  }
}
