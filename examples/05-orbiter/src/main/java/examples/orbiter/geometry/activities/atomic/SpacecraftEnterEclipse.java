package examples.orbiter.geometry.activities.atomic;

import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import examples.orbiter.Mission;
import gov.nasa.ammos.plandev.geometry.resources.EclipseTypes;
import gov.nasa.ammos.plandev.geometry.resources.GenericGeometryResources;
import gov.nasa.ammos.plandev.geometry.spiceinterpolation.Body;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

@ActivityType("SpacecraftEnterEclipse")
@Subsystem("geometry")
public class SpacecraftEnterEclipse {
  @Parameter
  public String body;
  @Parameter
  public EclipseTypes type;

  @Parameter
  public Duration duration;

  public SpacecraftEnterEclipse() {};

  public SpacecraftEnterEclipse(String body, EclipseTypes type, Duration d) {
    this.body = body;
    this.type = type;
    this.duration = d;
  }

  @ActivityType.EffectModel
  public void run(Mission model){
    EclipseTypes priorType = currentValue(model.geometryResources.SpacecraftEclipseByBody.get(body));
    set(model.geometryResources.SpacecraftEclipseByBody.get(body), type);

    EclipseTypes worstOverallEclipseType = getWorstEclipseFromAllBodies(model);
    set(model.geometryResources.AnySpacecraftEclipse, type);

    if(worstOverallEclipseType.equals(EclipseTypes.FULL)){
      set(model.geometryResources.FractionOfSunNotInEclipse, 0.0);
    }
    else if(type.equals(EclipseTypes.NONE)){
      set(model.geometryResources.FractionOfSunNotInEclipse, 1.0);
    }
    else{
      // this controls how high fidelity your partial eclipse model is
      int num_segments = 10;

      Duration stepTime = Duration.divide(duration, num_segments);
      for(int i = 0; i < num_segments; i++){
          // some call to vzfrac that we don't have access to yet, so instead let's be dumb
          if(priorType.equals(EclipseTypes.NONE)) {
            // We are transitioning from full Sun to less than full Sun
            set(model.geometryResources.FractionOfSunNotInEclipse, (1.0- (((double) i) / num_segments)));
          }
          else{
            // we're transitioning from full back to none
            set(model.geometryResources.FractionOfSunNotInEclipse, ((double) i) / num_segments);
          }
          delay(stepTime);
      }

      // set(model.geometryResources.FractionOfSunNotInEclipse, 0.0);
    }

  }

  static EclipseTypes getWorstEclipseFromAllBodies(Mission model){
    EclipseTypes worstEclipse = EclipseTypes.NONE;
    for(Body body: GenericGeometryResources.getBodies().values()){
      EclipseTypes thisBodysWorstEclipse = currentValue(model.geometryResources.SpacecraftEclipseByBody.get(body.getName()));
      if(!thisBodysWorstEclipse.equals(EclipseTypes.NONE)){
        if(worstEclipse.equals(EclipseTypes.NONE)){
          worstEclipse = thisBodysWorstEclipse;
        }
        else if(worstEclipse.equals(EclipseTypes.PARTIAL) && thisBodysWorstEclipse.equals(EclipseTypes.FULL)){
          worstEclipse = thisBodysWorstEclipse;
        }
        else if(worstEclipse.equals(EclipseTypes.ANNULAR) && thisBodysWorstEclipse.equals(EclipseTypes.FULL)){
          worstEclipse = thisBodysWorstEclipse;
        }
      }
    }
    return worstEclipse;
  }
}
