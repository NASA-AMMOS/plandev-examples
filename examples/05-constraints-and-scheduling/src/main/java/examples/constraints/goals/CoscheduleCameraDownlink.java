package examples.constraints.goals;

import gov.nasa.ammos.aerie.procedural.scheduling.Goal;
import gov.nasa.ammos.aerie.procedural.scheduling.annotations.SchedulingProcedure;
import gov.nasa.ammos.aerie.procedural.scheduling.plan.EditablePlan;
import gov.nasa.ammos.aerie.procedural.scheduling.plan.NewDirective;
import gov.nasa.ammos.aerie.procedural.timeline.payloads.activities.AnyDirective;
import gov.nasa.ammos.aerie.procedural.timeline.payloads.activities.DirectiveStart;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;
import gov.nasa.jpl.aerie.merlin.protocol.types.SerializedValue;

import java.util.Map;

/**
 * Scheduling goal: After every TakePicture, schedule a Downlink.
 *
 * Demonstrates co-scheduling — placing one activity in response to
 * another. For each TakePicture in the plan, this goal adds a
 * 1-hour Downlink activity starting 30 minutes after the picture
 * completes, unless one already exists nearby.
 */
@SchedulingProcedure
public record CoscheduleCameraDownlink(Duration delayAfterPicture) implements Goal {

  public static class Defaults {
    public Duration delayAfterPicture = Duration.of(30, Duration.MINUTES);
  }

  @Override
  public void run(EditablePlan plan) {
    var pictures = plan.directives("TakePicture").collect();
    var existingDownlinks = plan.directives("Downlink").collect();

    for (var picture : pictures) {
      // Estimate picture end time (start + durationSeconds parameter)
      var pictureDuration = Duration.of(60, Duration.SECONDS); // default
      var pictureEnd = picture.getStartTime().plus(pictureDuration);
      var downlinkStart = pictureEnd.plus(delayAfterPicture);

      // Check if a downlink already exists near this time
      boolean alreadyExists = false;
      for (var dl : existingDownlinks) {
        var diff = dl.getStartTime().minus(downlinkStart);
        if (diff.abs().shorterThan(Duration.HOUR)) {
          alreadyExists = true;
          break;
        }
      }

      if (!alreadyExists) {
        plan.create(new NewDirective(
            new AnyDirective(Map.of(
                "durationHours", SerializedValue.of(1)
            )),
            "Downlink (after picture)",
            "Downlink",
            new DirectiveStart.Absolute(downlinkStart)
        ));
      }
    }

    plan.commit();
  }
}
