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
 * Flags violations when battery net power (generation - consumption)
 * is negative for extended periods, indicating the spacecraft is
 * drawing down the battery faster than it can recharge.
 */
@ConstraintProcedure
public record PowerBalance() implements Constraint {

  @Override
  public Violations run(Plan plan, SimulationResults simResults) {
    // Net power = generation - load. When negative, battery is discharging.
    var netPower = simResults.resource("main.batteryNetPower", Real.deserializer());
    var dischargingWindows = netPower.lessThan(0).highlightTrue();
    return Violations.inside(dischargingWindows);
  }
}
