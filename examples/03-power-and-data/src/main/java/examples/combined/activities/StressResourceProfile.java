package examples.combined.activities;

import examples.combined.Mission;
import examples.combined.SimplePEL.CameraState;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType.EffectModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Parameter;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

/**
 * Test activity that produces a high number of resource segments by toggling
 * the camera state and pumping data into bin 0 in a tight loop. Use this to
 * stress-test UI streaming/profile rendering performance.
 *
 * Total wall-clock duration ≈ numberOfPoints * intervalMillis.
 * With defaults (5000 points, 100 ms apart) the activity runs for ~8m20s
 * and emits ~5000 segments on cameraState/cameraLoad/totalLoad/battery
 * plus ~5000 segments on the bin 0 data volume.
 */
@ActivityType("StressResourceProfile")
public class StressResourceProfile {

  @Parameter
  public int numberOfPoints = 5000;

  @Parameter
  public long intervalMillis = 100;

  @Parameter
  public int bin = 0;

  @Parameter
  public double dataRateBps = 1e6;

  @EffectModel
  public void run(Mission model) {
    final var step = Duration.of(intervalMillis, Duration.MILLISECONDS);
    final var binToChange = model.data.getOnboardBin(bin);

    for (int i = 0; i < numberOfPoints; i++) {
      final var nextState = (i % 2 == 0) ? CameraState.ON : CameraState.OFF;
      DiscreteEffects.set(model.pel.cameraState, nextState);
      binToChange.receive(dataRateBps, step);
      delay(step);
    }

    DiscreteEffects.set(model.pel.cameraState, CameraState.OFF);
  }
}
