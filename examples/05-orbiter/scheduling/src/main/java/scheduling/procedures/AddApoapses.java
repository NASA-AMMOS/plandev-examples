package scheduling.procedures;

import gov.nasa.ammos.plandev.procedural.scheduling.Goal;
import gov.nasa.ammos.plandev.procedural.scheduling.annotations.SchedulingProcedure;
import gov.nasa.ammos.plandev.procedural.scheduling.annotations.WithDefaults;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.EditablePlan;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.NewDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.AnyDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.DirectiveStart;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.merlin.protocol.types.SerializedValue;
import gov.nasa.jpl.time.Time;
import gov.nasa.ammos.plandev.geometry.globals.JPLTimeConvertUtility;
import examples.orbiter.geometry.activities.atomic.Apoapsis;
import gov.nasa.ammos.plandev.geometry.directspicecalls.SpiceDirectEventGenerator;
import gov.nasa.ammos.plandev.geometry.interfaces.GeometryInformationNotAvailableException;
import gov.nasa.ammos.plandev.geometry.spiceinterpolation.Bodies;
import examples.orbiter.Mission;import examples.orbiter.spice.Spice;
import spice.basic.SpiceErrorException;

import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static examples.orbiter.generated.ActivityActions.spawn;

@SchedulingProcedure
public record AddApoapses(
        String body,
        String target,
        Duration stepSize,
        double minDistanceFilter ) implements Goal {

    public static final Path VERSIONED_KERNELS_ROOT_DIRECTORY = Path.of(System.getenv().getOrDefault("SPICE_DIRECTORY", "spice-kernels"));

    public static final String NAIF_META_KERNEL_PATH = VERSIONED_KERNELS_ROOT_DIRECTORY.toString() + "/latest_meta_kernel.tm";

    @WithDefaults
    public static class Template {
        public String body = "mro";
        public String target = "MARS";
        public Duration stepSize = Duration.MINUTE;
        public double minDistanceFilter = 1.0;
    }

    @Override
    public void run(EditablePlan plan) {

      // Instantiate Spice
      try {
        Spice.initialize(NAIF_META_KERNEL_PATH);
      } catch (SpiceErrorException e) {
        System.out.println(e.getMessage());
      }

      // Initialize Geometry Bodies
      Bodies bodiesObj = new Bodies(Mission.class);
      SpiceDirectEventGenerator generator = new SpiceDirectEventGenerator(bodiesObj.getBodiesMap());
      Instant planStart = plan.toAbsolute(plan.totalBounds().start);
      Instant planEnd = plan.toAbsolute(plan.totalBounds().end);

      List<Time> apoapsisTimes;

      Map<String, SerializedValue> actArgs = Map.of("body", SerializedValue.of(target));

      try {
        apoapsisTimes = generator.getApoapses( JPLTimeConvertUtility.jplTimeFromUTCInstant(planStart),
          JPLTimeConvertUtility.jplTimeFromUTCInstant(planEnd),
          JPLTimeConvertUtility.getJplTimeDur(stepSize), body, target, minDistanceFilter, "NONE");
      } catch (GeometryInformationNotAvailableException e) {
        apoapsisTimes = new ArrayList<>();
      }
      for(Time apoapsisTime : apoapsisTimes){

        // Create new activity
        var newDirective = new NewDirective(
          new AnyDirective(actArgs),
          "Apoapsis_" + target,
          "Apoapsis",
          new DirectiveStart.Absolute(plan.toRelative( apoapsisTime.toTimezone("UTC").toInstant())));
        plan.create(newDirective);

      }
      // Actually add activities to the plan
      plan.commit();

    }
}
