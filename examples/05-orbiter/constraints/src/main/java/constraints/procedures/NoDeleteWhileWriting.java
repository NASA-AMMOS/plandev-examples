package constraints.procedures;

import gov.nasa.ammos.plandev.procedural.constraints.Constraint;
import gov.nasa.ammos.plandev.procedural.constraints.Violations;
import gov.nasa.ammos.plandev.procedural.constraints.annotations.ConstraintProcedure;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Booleans;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Real;
import gov.nasa.ammos.plandev.procedural.timeline.plan.Plan;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;

@ConstraintProcedure
public record NoDeleteWhileWriting() implements Constraint {
  @Override
  public Violations run(Plan plan, SimulationResults simResults) {
    Booleans deletes = simResults.instances("DeleteData").active();
    Booleans writes = simResults.instances().filterByType("GenerateData", "ChangeRadarDataMode").active();

    return Violations.on(
      writes.and(deletes),
      true
    );
  }
}
