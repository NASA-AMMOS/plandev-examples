package examples.constraints.model.activities;

import examples.constraints.model.Mission;
import examples.constraints.model.SimplePEL.CameraState;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

/**
 * Instrument calibration activity. Turns on the camera briefly to
 * perform a calibration sequence. Used by the RecurrentCalibration
 * scheduling goal to demonstrate periodic activity placement.
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
