package examples.constraints.procedures;

import gov.nasa.ammos.plandev.procedural.scheduling.Goal;
import gov.nasa.ammos.plandev.procedural.scheduling.annotations.SchedulingProcedure;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.EditablePlan;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.NewDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.AnyDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.DirectiveStart;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.merlin.protocol.types.SerializedValue;

import java.util.Map;

/**
 * Scheduling goal: Place a Calibrate activity every N hours.
 *
 * Demonstrates the simplest scheduling pattern — recurring activities
 * at a fixed interval throughout the plan. The goal checks for existing
 * calibrations and only adds new ones where needed.
 */
@SchedulingProcedure
public record RecurrentCalibration(Duration period) implements Goal {

  public static class Defaults {
    public Duration period = Duration.of(24, Duration.HOURS);
  }

  @Override
  public void run(EditablePlan plan) {
    var existingCals = plan.directives("Calibrate").collect();
    var bounds = plan.totalBounds();
    var currentTime = bounds.start;

    while (currentTime.shorterThan(bounds.end)) {
      // Check if a calibration already exists near this time
      boolean alreadyExists = false;
      for (var cal : existingCals) {
        var diff = cal.getStartTime().minus(currentTime);
        if (diff.abs().shorterThan(Duration.HOUR)) {
          alreadyExists = true;
          break;
        }
      }

      if (!alreadyExists) {
        plan.create(new NewDirective(
            new AnyDirective(Map.of(
                "durationMinutes", SerializedValue.of(30)
            )),
            "Calibrate (scheduled)",
            "Calibrate",
            new DirectiveStart.Absolute(currentTime)
        ));
      }

      currentTime = currentTime.plus(period);
    }

    plan.commit();
  }
}
