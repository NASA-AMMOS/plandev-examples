package examples.constraints.model.activities;

import examples.constraints.model.Mission;
import examples.constraints.model.SimplePEL.CameraState;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

@ActivityType("TakePicture")
public class TakePicture {

  @Parameter
  public long durationSeconds = 60;

  @Parameter
  public double dataRateBps = 5e6;

  @Parameter
  public int bin = 0;

  @EffectModel
  public void run(Mission model) {
    DiscreteEffects.set(model.pel.cameraState, CameraState.ON);
    var dur = Duration.of(durationSeconds, Duration.SECONDS);
    model.data.getOnboardBin(bin).receive(dataRateBps, dur);
    delay(dur);
    DiscreteEffects.set(model.pel.cameraState, CameraState.OFF);
  }
}
