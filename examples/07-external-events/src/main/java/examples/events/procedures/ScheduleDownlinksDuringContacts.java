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
 * <p>For each DSN contact event in the plan, this goal schedules a Downlink
 * activity that spans the contact window, skipping contacts that already have a
 * Downlink nearby.
 *
 * <p>The two things worth copying from this goal:
 * <ul>
 *   <li><b>Size the activity to the event.</b> The downlink duration comes from
 *       {@code contact.getInterval()}, not a constant — a 1h45m pass gets a
 *       1h45m downlink. Hardcoding a duration would waste most real contacts.</li>
 *   <li><b>Read the event payload.</b> {@code contact.attributes} carries the
 *       schema's fields (station, band, bitrate); this goal uses the bitrate to
 *       skip passes too weak to be worth scheduling, and puts the station in the
 *       directive name.</li>
 * </ul>
 *
 * Usage:
 * 1. Upload the event schema and source in {@code src/main/resources/} to PlanDev
 *    (event type: "DSNContact")
 * 2. Run this scheduling goal -- it will create Downlink activities
 *    aligned to the contact windows
 */
@SchedulingProcedure
public record ScheduleDownlinksDuringContacts(double minimumBitrateKbps) implements Goal {

  public static class Defaults {
    /** Contacts slower than this are skipped as not worth a downlink. */
    public double minimumBitrateKbps = 0.0;
  }

  /** Two downlinks closer together than this are treated as the same opportunity. */
  private static final Duration DEDUPE_WINDOW = Duration.HOUR;

  @Override
  public void run(EditablePlan plan) {
    // Query all DSN contact external events (filter by event type)
    var contactQuery = new EventQuery(null, "DSNContact", null);
    var contacts = plan.events(contactQuery).collect();
    var existingDownlinks = plan.directives("Downlink").collect();

    for (var contact : contacts) {
      var window = contact.getInterval();
      var contactStart = window.start;

      // Payload: skip contacts whose bitrate is below the configured floor.
      if (bitrateKbps(contact.attributes) < minimumBitrateKbps) {
        continue;
      }

      // Check if a Downlink already exists near this contact
      boolean alreadyExists = false;
      for (var dl : existingDownlinks) {
        if (dl.getStartTime().minus(contactStart).abs().shorterThan(DEDUPE_WINDOW)) {
          alreadyExists = true;
          break;
        }
      }
      if (alreadyExists) {
        continue;
      }

      // Size the downlink to the contact window rather than assuming a fixed length.
      double durationHours = window.duration().ratioOver(Duration.HOUR);

      plan.create(new NewDirective(
          new AnyDirective(Map.of(
              "durationHours", SerializedValue.of(durationHours)
          )),
          "Downlink (" + stationOf(contact.attributes) + ": " + contact.key + ")",
          "Downlink",
          new DirectiveStart.Absolute(contactStart)
      ));
    }

    plan.commit();
  }

  /** Reads the schema's optional {@code bitrate_kbps} attribute, defaulting to permissive. */
  private static double bitrateKbps(Map<String, SerializedValue> attributes) {
    var value = attributes.get("bitrate_kbps");
    if (value == null) return Double.MAX_VALUE;
    return value.asReal().orElse(Double.MAX_VALUE);
  }

  /** Reads the schema's required {@code station} attribute. */
  private static String stationOf(Map<String, SerializedValue> attributes) {
    var value = attributes.get("station");
    if (value == null) return "unknown station";
    return value.asString().orElse("unknown station");
  }
}
