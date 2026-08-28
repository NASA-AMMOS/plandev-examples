package examples.orbiter.geometry.activities.atomic;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import examples.orbiter.Mission;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

@ActivityType("ExitOccultation")
@Subsystem("geometry")
public class ExitOccultation {

  @Export.Parameter
  public String body;
  @Export.Parameter
  public String station;

  public ExitOccultation() {};

  public ExitOccultation(String body, String station) {
    this.body = body;
    this.station = station;
  }

  @ActivityType.EffectModel
  public void run(Mission model){
    //setGroup("OccultationEvents");
    // setName("EnterOccultation_" + body + "_SeenFrom_" + station);
    DiscreteEffects.decrement(model.geometryResources.Occultation, 1);
    DiscreteEffects.turnOff(model.geometryResources.SpacecraftOccultationByBodyAndStation.get(body).get(station));
  }
}
