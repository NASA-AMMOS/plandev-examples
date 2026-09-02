package examples.constraints.constraints;

import gov.nasa.ammos.plandev.procedural.constraints.Constraint;
import gov.nasa.ammos.plandev.procedural.constraints.Violations;
import gov.nasa.ammos.plandev.procedural.constraints.annotations.ConstraintProcedure;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Real;
import gov.nasa.ammos.plandev.procedural.timeline.plan.Plan;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;

/**
 * Constraint: Battery state of charge must stay above a minimum threshold.
 *
 * Flags violations whenever the battery SOC drops below the configured
 * minimum (default 20%). This prevents deep discharge that could damage
 * the battery or leave insufficient power for safe mode entry.
 */
@ConstraintProcedure
public record BatteryDepthOfDischarge(double minSOC) implements Constraint {

  public static class Defaults {
    public double minSOC = 20.0; // percent
  }

  @Override
  public Violations run(Plan plan, SimulationResults simResults) {
    var lowBatteryWindows = simResults
        .resource("mainbattery.batterySOC", Real.deserializer())
        .lessThan(minSOC)
        .highlightTrue();
    return Violations.inside(lowBatteryWindows);
  }
}
