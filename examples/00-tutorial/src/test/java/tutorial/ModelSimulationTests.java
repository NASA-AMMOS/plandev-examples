package tutorial;

import gov.nasa.ammos.plandev.procedural.scheduling.plan.EditablePlan;
import gov.nasa.ammos.plandev.procedural.scheduling.utils.DefaultEditablePlanDriver;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Real;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Strings;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.DirectiveStart;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;
import gov.nasa.ammos.plandev.procedural.utils.TypeUtilsEditablePlanAdapter;
import gov.nasa.ammos.plandev.procedural.utils.TypeUtilsPlanAdapter;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.DurationValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper;
import gov.nasa.ammos.plandev.merlin.driver.MissionModel;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.orchestration.simulation.SimulationUtility;
import gov.nasa.ammos.plandev.types.Plan;
import gov.nasa.ammos.plandev.types.Timestamp;
import tutorial.generated.GeneratedModelType;
import org.junit.jupiter.api.*;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Example test for simulating a mission model
 * General workflow:
 * 1. Create a {@link SimulationUtility} instance.
 * 2. Load the mission model using the sim utility.
 * 3. Create a new empty plan. You'll need to use a couple adapters, see SchedulingProcedureTests.beforeEach.
 *    for an example.
 * 4. Add activities to the plan as desired
 * 5. Look at resultant simulation results and check with assertions
 */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public class ModelSimulationTests {

  private MissionModel<?> model;
  private SimulationUtility simUtility;
  private Instant simulationStartTime;
  private EditablePlan plan;

  /* Setup and instantiate the mission model. */
  @BeforeAll
  void beforeAll() {
    // Note no resource file streamer is required since we don't plan to write out resources to a file
    simUtility = new SimulationUtility();
    Configuration simConfig = Configuration.defaultConfiguration();
    simulationStartTime = Instant.parse("2025-01-01T00:00:00Z");
    model = SimulationUtility.instantiateMissionModel(new GeneratedModelType(), simulationStartTime, simConfig);

  }

  /* Close out . */
  @AfterAll
  void afterAll() {
    simUtility.close();
  }

  @BeforeEach
  void beforeEach() {
    plan = new DefaultEditablePlanDriver(
      new TypeUtilsEditablePlanAdapter(
        new TypeUtilsPlanAdapter(
          new Plan("TestPlan", new Timestamp(simulationStartTime), new Timestamp(simulationStartTime.plusSeconds(60 * 60 * 24)), Map.of(), Map.of())
        ),
        simUtility,
        model
      )
    );
  }

  @Test
  final void testSchedulePeriodicDataCollections() {

    // Create three activities. Two ChangeMagMode activities and a CollectData in between
    plan.create("ChangeMagMode", new DirectiveStart.Absolute(Duration.hours(1)), Map.of("mode",
      new EnumValueMapper<>(MagDataCollectionMode.class).serializeValue(MagDataCollectionMode.HIGH_RATE)));
    plan.create("ChangeMagMode", new DirectiveStart.Absolute(Duration.hours(12)), Map.of("mode",
      new EnumValueMapper<>(MagDataCollectionMode.class).serializeValue(MagDataCollectionMode.LOW_RATE)));
    plan.create("CollectData", new DirectiveStart.Absolute(Duration.hours(6)), Map.of("duration",
      new DurationValueMapper().serializeValue(Duration.HOUR)));

    // Simulate Plan
    SimulationResults simResults = plan.simulate();

    // Perform assertions
    Strings modeProfile = simResults.resource("MagDataMode", Strings.deserializer());
    assertEquals("HIGH_RATE", modeProfile.sample(Duration.hours(1)));
    assertEquals("LOW_RATE", modeProfile.sample(Duration.hours(12)));

    Real rateProfile = simResults.resource("RecordingRate", Real.deserializer() );
    assertEquals(15,rateProfile.sample(Duration.hours(6.5)));

  }

}
