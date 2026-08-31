package examples.testing;

import gov.nasa.ammos.plandev.procedural.scheduling.plan.EditablePlan;
import gov.nasa.ammos.plandev.procedural.scheduling.utils.DefaultEditablePlanDriver;
import gov.nasa.ammos.plandev.procedural.timeline.collections.profiles.Real;
import gov.nasa.ammos.plandev.procedural.timeline.payloads.activities.DirectiveStart;
import gov.nasa.ammos.plandev.procedural.timeline.plan.SimulationResults;
import gov.nasa.ammos.plandev.procedural.utils.TypeUtilsEditablePlanAdapter;
import gov.nasa.ammos.plandev.procedural.utils.TypeUtilsPlanAdapter;
import gov.nasa.ammos.plandev.merlin.driver.MissionModel;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.orchestration.simulation.SimulationUtility;
import gov.nasa.ammos.plandev.types.Plan;
import gov.nasa.ammos.plandev.types.Timestamp;
import examples.testing.generated.GeneratedModelType;
import org.junit.jupiter.api.*;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Demonstrates how to set up simulation-based tests for PlanDev mission models.
 *
 * Pattern:
 * 1. Create a SimulationUtility and instantiate the mission model.
 * 2. For each test, create a fresh EditablePlan with a plan duration.
 * 3. Add activities to the plan.
 * 4. Simulate and assert on resource profiles.
 */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public class BasicSimulationTest {

  private MissionModel<?> model;
  private SimulationUtility simUtility;
  private Instant simulationStartTime;
  private EditablePlan plan;

  @BeforeAll
  void beforeAll() {
    simUtility = new SimulationUtility();
    Configuration simConfig = Configuration.defaultConfiguration();
    simulationStartTime = Instant.parse("2025-01-01T00:00:00Z");
    model = SimulationUtility.instantiateMissionModel(new GeneratedModelType(), simulationStartTime, simConfig);
  }

  @AfterAll
  void afterAll() {
    simUtility.close();
  }

  @BeforeEach
  void beforeEach() {
    plan = new DefaultEditablePlanDriver(
      new TypeUtilsEditablePlanAdapter(
        new TypeUtilsPlanAdapter(
          new Plan(
            "TestPlan",
            new Timestamp(simulationStartTime),
            new Timestamp(simulationStartTime.plusSeconds(60 * 60 * 24)),
            Map.of(),
            Map.of()
          )
        ),
        simUtility,
        model
      )
    );
  }

  @Test
  void testInitialResourceValues() {
    // Simulate with no activities -- verify defaults
    SimulationResults results = plan.simulate();

    Real soc = results.resource("BatterySOC", Real.deserializer());
    assertEquals(100.0, soc.sample(Duration.ZERO));

    Real dataVol = results.resource("DataVolume", Real.deserializer());
    assertEquals(20.0, dataVol.sample(Duration.ZERO));
  }

  @Test
  void testDrainBatteryReducesSOC() {
    // Place a DrainBattery activity at T+1h with amount=25
    plan.create(
      "DrainBattery",
      new DirectiveStart.Absolute(Duration.hours(1)),
      Map.of("amount", gov.nasa.ammos.plandev.merlin.protocol.types.SerializedValue.of(25.0))
    );

    SimulationResults results = plan.simulate();

    Real soc = results.resource("BatterySOC", Real.deserializer());
    // Before the activity, SOC should still be 100
    assertEquals(100.0, soc.sample(Duration.ZERO));
    // After the activity runs at T+1h, SOC should be 75
    assertEquals(75.0, soc.sample(Duration.hours(2)));
  }

  @Test
  void testCollectDataIncreasesVolume() {
    // Place a CollectData activity at T+2h with volume=500
    plan.create(
      "CollectData",
      new DirectiveStart.Absolute(Duration.hours(2)),
      Map.of("volume", gov.nasa.ammos.plandev.merlin.protocol.types.SerializedValue.of(500))
    );

    SimulationResults results = plan.simulate();

    Real dataVol = results.resource("DataVolume", Real.deserializer());
    // Before the activity
    assertEquals(0.0, dataVol.sample(Duration.ZERO));
    // After the activity runs at T+2h
    assertEquals(500.0, dataVol.sample(Duration.hours(3)));
  }
}
