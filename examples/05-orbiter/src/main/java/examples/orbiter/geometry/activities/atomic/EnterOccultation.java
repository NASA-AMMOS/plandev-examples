package examples.orbiter.geometry.activities.atomic;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import examples.orbiter.Mission;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

@ActivityType("EnterOccultation")
@Subsystem("geometry")
public class EnterOccultation {

  @Parameter
  public String body = "";
  @Parameter
  public String station = "DSS-24";

  public EnterOccultation() {};

  public EnterOccultation(String body, String station) {
    this.body = body;
    this.station = station;
  }

  @ActivityType.EffectModel
  public void run(Mission model){
    //setGroup("OccultationEvents");
    // setName("EnterOccultation_" + body + "_SeenFrom_" + station);
    DiscreteEffects.increment(model.geometryResources.Occultation, 1);
    DiscreteEffects.turnOn(model.geometryResources.SpacecraftOccultationByBodyAndStation.get(body).get(station));
  }
}
