package examples.constraints.constraints;

import gov.nasa.ammos.plandev.procedural.constraints.Constraint;
import gov.nasa.ammos.plandev.procedural.constraints.Violations;
import gov.nasa.ammos.plandev.procedural.constraints.annotations.ConstraintProcedure;
import gov.nasa.ammos.plandev.procedural.timeline.plan.Plan;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

/**
 * Constraint: Downlink activities must meet a minimum duration.
 *
 * Demonstrates the activity-duration filtering pattern. Short downlinks
 * waste setup/teardown overhead without transferring meaningful data.
 */
@ConstraintProcedure
public record DownlinkMinDuration(Duration minDur) implements Constraint {

  public static class Defaults {
    public Duration minDur = Duration.of(30, Duration.MINUTE);
  }

  @Override
  public Violations run(Plan plan, SimulationResults simResults) {
    return Violations.on(
        simResults.instances("Downlink").filterShorterThan(minDur).active(),
        true);
  }
}
