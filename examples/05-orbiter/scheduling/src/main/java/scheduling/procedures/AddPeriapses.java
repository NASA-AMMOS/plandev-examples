package scheduling.procedures;

import gov.nasa.ammos.plandev.procedural.scheduling.ActivityAutoDelete;
import gov.nasa.ammos.plandev.procedural.scheduling.Goal;
import gov.nasa.ammos.plandev.procedural.scheduling.annotations.SchedulingProcedure;
import gov.nasa.ammos.plandev.procedural.scheduling.annotations.WithDefaults;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.DeletedAnchorStrategy;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.EditablePlan;
import gov.nasa.ammos.plandev.procedural.scheduling.plan.NewDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.AnyDirective;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.DirectiveStart;
import gov.nasa.ammos.plandev.procedural.timeline.plan.Plan;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.merlin.protocol.types.SerializedValue;
import gov.nasa.ammos.plandev.geometry.globals.JPLTimeConvertUtility;
import gov.nasa.ammos.plandev.geometry.directspicecalls.SpiceDirectEventGenerator;
import gov.nasa.ammos.plandev.geometry.interfaces.GeometryInformationNotAvailableException;
import gov.nasa.ammos.plandev.geometry.spiceinterpolation.Bodies;
import examples.orbiter.Mission;import examples.orbiter.spice.Spice;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import spice.basic.SpiceErrorException;

import gov.nasa.jpl.time.Time;

import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@SchedulingProcedure
public record AddPeriapses(
        String body,
        String target,
        Duration stepSize,
        double maxDistanceFilter ) implements Goal {

    public static final Path VERSIONED_KERNELS_ROOT_DIRECTORY = Path.of(System.getenv().getOrDefault("SPICE_DIRECTORY", "spice-kernels"));

    public static final String NAIF_META_KERNEL_PATH = VERSIONED_KERNELS_ROOT_DIRECTORY.toString() + "/latest_meta_kernel.tm";

    @WithDefaults
    public static class Template {
        public String body = "mro";
        public String target = "MARS";
        public Duration stepSize = Duration.MINUTE;
        public double maxDistanceFilter = 1000000000.0;
    }
    
    @NotNull
    @Override
    public ActivityAutoDelete shouldDeletePastCreations(
        @NotNull final Plan plan,
        @Nullable final SimulationResults simResults) {
      // Delete Periapsis activities created by previous runs of this goal
      return new ActivityAutoDelete.AtBeginning(DeletedAnchorStrategy.Cascade, false);
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

      List<Time> periapsisTimes;

      Map<String, SerializedValue> actArgs = Map.of("body", SerializedValue.of(target));

      try {
        periapsisTimes = generator.getPeriapses(JPLTimeConvertUtility.jplTimeFromUTCInstant(planStart),
          JPLTimeConvertUtility.jplTimeFromUTCInstant(planEnd),
          JPLTimeConvertUtility.getJplTimeDur(stepSize), body, target, maxDistanceFilter, "NONE");
      } catch (GeometryInformationNotAvailableException e) {
        periapsisTimes = new ArrayList<>();
      }

      for (Time periapsisTime : periapsisTimes) {

        // Create new activity
        var newDirective = new NewDirective(
          new AnyDirective(actArgs),
          "Periapsis_" + target,
          "Periapsis",
          new DirectiveStart.Absolute(plan.toRelative( periapsisTime.toTimezone("UTC").toInstant())));
        plan.create(newDirective);

      }

      // Actually add activities to the plan
      plan.commit();

    }
}
