package examples.orbiter.geometry.activities.atomic;

import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Parameter;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import examples.orbiter.Mission;
import spice.basic.CSPICE;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects.set;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

/**
 * The point at which the spacecraft is closest to the
 #        center of mass of the body.
 */
@ActivityType("Periapsis")
@Subsystem("geometry")
public class Periapsis {

  @Parameter
  public String body = "";

  public Periapsis() {}

  public Periapsis(String body) {
    this.body = body;
  }

  @ActivityType.EffectModel
  public void run(Mission model) {
    set(model.geometryResources.Periapsis.get(body), true);
    delay(Duration.SECOND);
    set(model.geometryResources.Periapsis.get(body), false);
  }
}
