package examples.constraints.constraints;

import gov.nasa.ammos.plandev.procedural.constraints.Constraint;
import gov.nasa.ammos.plandev.procedural.constraints.Violations;
import gov.nasa.ammos.plandev.procedural.constraints.annotations.ConstraintProcedure;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Booleans;
import gov.nasa.ammos.plandev.procedural.timeline.plan.Plan;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;

/**
 * Constraint: TakePicture and Downlink activities must not overlap.
 *
 * Demonstrates the mutual-exclusion pattern using activity instance
 * windows and boolean AND logic. Realistic scenario: camera and
 * downlink share power or antenna resources.
 */
@ConstraintProcedure
public record NoSimultaneousCameraAndDownlink() implements Constraint {

  @Override
  public Violations run(Plan plan, SimulationResults simResults) {
    Booleans cameraActive = simResults.instances("TakePicture").active();
    Booleans downlinkActive = simResults.instances("Downlink").active();

    return Violations.on(
        cameraActive.and(downlinkActive),
        true
    );
  }
}
