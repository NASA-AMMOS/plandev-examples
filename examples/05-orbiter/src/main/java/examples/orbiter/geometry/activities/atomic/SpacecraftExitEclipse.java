package examples.orbiter.geometry.activities.atomic;

import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import examples.orbiter.Mission;
import gov.nasa.ammos.plandev.geometry.resources.EclipseTypes;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static examples.orbiter.geometry.activities.atomic.SpacecraftEnterEclipse.getWorstEclipseFromAllBodies;

@ActivityType("SpacecraftExitEclipse")
@Subsystem("geometry")
public class SpacecraftExitEclipse {

  @Export.Parameter
  public String body;

  public SpacecraftExitEclipse() {};

  public SpacecraftExitEclipse(String body) {
    this.body = body;
  }

  @ActivityType.EffectModel
  public void run(Mission model){
    set(model.geometryResources.SpacecraftEclipseByBody.get(body), EclipseTypes.NONE);

    EclipseTypes worstOverallEclipseType = getWorstEclipseFromAllBodies(model);
    set(model.geometryResources.AnySpacecraftEclipse, worstOverallEclipseType);

    if(worstOverallEclipseType.equals(EclipseTypes.NONE)){
      set(model.geometryResources.FractionOfSunNotInEclipse, 1.0);
    }
    delay(Duration.SECOND);
  }

}
