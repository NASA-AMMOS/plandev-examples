package examples.constraints.constraints;

import gov.nasa.ammos.plandev.procedural.constraints.Constraint;
import gov.nasa.ammos.plandev.procedural.constraints.Violations;
import gov.nasa.ammos.plandev.procedural.constraints.annotations.ConstraintProcedure;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Real;
import gov.nasa.ammos.plandev.procedural.timeline.plan.Plan;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;

/**
 * Constraint: Power generation must meet demand.
 *
 * Flags violations when periods when power demand
 * exceeds generation, causing the battery to discharge.
 */
@ConstraintProcedure
public record PowerBalance() implements Constraint {

  @Override
  public Violations run(Plan plan, SimulationResults simResults) {
    // Net current = generation - load. When negative, battery is discharging.
    var netCurrent = simResults.resource("mainbattery.batteryCurrentUnclamped", Real.deserializer());
    var dischargingWindows = netCurrent.lessThan(0).highlightTrue();
    return Violations.inside(dischargingWindows);
  }
}
