package examples.orbiter.radar;

import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Subsystem;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;
import examples.orbiter.Mission;
import examples.orbiter.power.pel.Radar_State;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;
import static examples.orbiter.generated.ActivityActions.spawn;

@ActivityType("Radar_Off")
@Subsystem("radar")
public class Radar_Off {

  @ActivityType.EffectModel
  public void run(Mission model) {
    DiscreteEffects.set(model.pel.radarState, Radar_State.OFF);
    spawn(model, new ChangeRadarDataMode(RadarDataCollectionMode.OFF));
    delay(Duration.SECOND);
  }
}
