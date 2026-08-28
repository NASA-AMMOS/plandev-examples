package examples.constraints.constraints;

import gov.nasa.ammos.plandev.procedural.constraints.Constraint;
import gov.nasa.ammos.plandev.procedural.constraints.Violations;
import gov.nasa.ammos.plandev.procedural.constraints.annotations.ConstraintProcedure;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Real;
import gov.nasa.ammos.plandev.procedural.timeline.plan.Plan;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;

/**
 * Constraint: Onboard data volume must not exceed storage capacity.
 *
 * Flags violations when data volume reaches 90% of the configured
 * maximum, giving operators time to schedule a downlink before
 * the storage actually overflows.
 */
@ConstraintProcedure
public record DataVolumeLimit(double maxVolumePercent) implements Constraint {

  public static class Defaults {
    public double maxVolumePercent = 90.0;
  }

  @Override
  public Violations run(Plan plan, SimulationResults simResults) {
    var volume = simResults.resource("/data/onboard/volume", Real.deserializer());
    var limit = simResults.resource("/data/onboard/limit", Real.deserializer());

    // Flag when volume exceeds the configured percentage of limit
    var overLimit = volume.minus(limit.times(maxVolumePercent / 100.0))
        .greaterThan(0)
        .highlightTrue();
    return Violations.inside(overLimit);
  }
}
