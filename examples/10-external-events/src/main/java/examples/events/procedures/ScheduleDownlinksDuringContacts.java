package examples.events.procedures;

import gov.nasa.ammos.plandev.procedural.scheduling.Goal;
import gov.nasa.ammos.plandev.procedural.scheduling.annotations.SchedulingProcedure;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.EditablePlan;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.NewDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.AnyDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.DirectiveStart;
import gov.nasa.ammos.plandev.procedural.timeline.plan.EventQuery;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.merlin.protocol.types.SerializedValue;

import java.util.Map;

/**
 * Procedural scheduling goal that reacts to external DSN contact events.
 *
 * For each DSN contact event in the plan, this goal schedules a Downlink
 * activity at the contact start time. It avoids duplicates by checking
 * whether a Downlink already exists within one hour of each contact.
 *
 * Usage:
 * 1. Upload DSN contact events as an external event source in PlanDev
 *    (event type: "DSNContact")
 * 2. Run this scheduling goal -- it will create Downlink activities
 *    aligned to the contact windows
 */
@SchedulingProcedure
public record ScheduleDownlinksDuringContacts() implements Goal {

  @Override
  public void run(EditablePlan plan) {
    // Query all DSN contact external events (filter by event type)
    var contactQuery = new EventQuery(null, "DSNContact", null);
    var contacts = plan.events(contactQuery).collect();
    var existingDownlinks = plan.directives("Downlink").collect();

    for (var contact : contacts) {
      var contactStart = contact.getInterval().start;

      // Check if a Downlink already exists near this contact
      boolean alreadyExists = false;
      for (var dl : existingDownlinks) {
        var diff = dl.getStartTime().minus(contactStart);
        // Duration has no abs(), so check both directions
        if (diff.shorterThan(Duration.HOUR) && Duration.negate(diff).shorterThan(Duration.HOUR)) {
          alreadyExists = true;
          break;
        }
      }

      if (!alreadyExists) {
        plan.create(new NewDirective(
            new AnyDirective(Map.of(
                "durationHours", SerializedValue.of(1)
            )),
            "Downlink (DSN contact: " + contact.key + ")",
            "Downlink",
            new DirectiveStart.Absolute(contactStart)
        ));
      }
    }

    plan.commit();
  }
}
