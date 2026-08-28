package gov.nasa.ammos.plandev.power;

import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.merlin.framework.junit.MerlinExtension;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestInstance.Lifecycle;
import org.junit.jupiter.api.extension.ExtendWith;

import java.time.Instant;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.set;
import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources.discreteResource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.constant;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static gov.nasa.ammos.plandev.merlin.protocol.types.Duration.HOUR;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Simulation tests for the power subsystem — {@link BatteryModel}, {@link GenericSolarArray},
 * and {@link RtgPowerProduction}. Uses {@link MerlinExtension} (which requires
 * {@link Lifecycle#PER_CLASS}), so all models are constructed once in the test class
 * constructor. Tests use delta-based assertions to remain order-independent.
 */
@ExtendWith(MerlinExtension.class)
@TestInstance(Lifecycle.PER_CLASS)
public class PowerModelTest {

  // One fresh model per scenario, all built in the init context (constructor).

  private final MutableResource<Discrete<Double>> idleDemand = discreteResource(0.0);
  private final BatteryModel idleBattery =
      new BatteryModel("idle", BatterySimConfig.defaultConfiguration(), idleDemand, constant(0.0));

  // 140 W demand at 0 W production = -5 A net at 28 V bus.
  private final MutableResource<Discrete<Double>> drainDemand = discreteResource(140.0);
  private final BatteryModel drainingBattery =
      new BatteryModel("drain", BatterySimConfig.defaultConfiguration(), drainDemand, constant(0.0));

  // 2800 W demand = 100 A net drain — drains the 100 Ah battery in ~1 h.
  private final MutableResource<Discrete<Double>> overDrainDemand = discreteResource(2800.0);
  private final BatteryModel overDrainBattery =
      new BatteryModel("over", BatterySimConfig.defaultConfiguration(), overDrainDemand, constant(0.0));

  // Solar arrays.
  private final MutableResource<Discrete<Double>> undeployedDistance = discreteResource(1.0);
  private final GenericSolarArray undeployedArray = new GenericSolarArray(
      new SolarArraySimConfig(
          ArrayDeploymentStates.UNDEPLOYED,
          SolarArraySimConfig.DEFAULT_ARRAY_MECH_AREA,
          SolarArraySimConfig.DEFAULT_PACKING_FACTOR,
          SolarArraySimConfig.DEFAULT_CELL_EFFICIENCY,
          SolarArraySimConfig.DEFAULT_CONVERSION_EFFICIENCY,
          SolarArraySimConfig.DEFAULT_OTHER_LOSSES),
      undeployedDistance, discreteResource(0.0), discreteResource(1.0));

  private final MutableResource<Discrete<Double>> deployedDistance = discreteResource(1.0);
  private final GenericSolarArray deployedArray = new GenericSolarArray(
      SolarArraySimConfig.defaultConfiguration(),
      deployedDistance, discreteResource(0.0), discreteResource(1.0));

  // RTG with a fixed decayStart and 50 %/yr decay so the change is observable over short deltas.
  private static final Instant RTG_START = Instant.parse("2025-01-01T00:00:00Z");
  private final RtgPowerProduction rtg = new RtgPowerProduction(
      new RtgSimConfig(1, 100.0, 50.0, RTG_START), RTG_START);

  // ---- Battery tests ----

  @Test
  void testIdleBatteryStaysAtFullSOC() {
    // No demand and no production -> net current is 0, SOC never changes from the 100 % initial.
    assertEquals(100.0, currentValue(idleBattery.batterySOC), 0.01);
    assertTrue(currentValue(idleBattery.batteryFull));
  }

  @Test
  void testBatteryDrainsWhenDemandExceedsProduction() {
    // Delta assertion so test order doesn't matter: SOC drops by ~5 % per hour at -5 A.
    double socBefore = currentValue(drainingBattery.batterySOC);
    delay(1, HOUR);
    double socAfter = currentValue(drainingBattery.batterySOC);
    assertEquals(5.0, socBefore - socAfter, 0.5);
  }

  @Test
  void testBatteryClampsAtZeroSOC() {
    // overDrainBattery drains at 100 A continuously from sim t=0. After 2 h of any sim run,
    // SOC is clamped at 0 regardless of which test ran first.
    delay(2, HOUR);
    assertEquals(0.0, currentValue(overDrainBattery.batterySOC), 0.01);
    assertTrue(currentValue(overDrainBattery.batteryEmpty));
  }

  // ---- Solar array tests ----

  @Test
  void testSolarUndeployedProducesZero() {
    assertEquals(0.0, currentValue(undeployedArray.powerProduction), 1e-9);
  }

  @Test
  void testSolarInverseSquareLaw() {
    set(deployedDistance, discrete(1.0));
    double powerAt1AU = currentValue(deployedArray.powerProduction);
    assertTrue(powerAt1AU > 0, "expected positive power when deployed at 1 AU, got " + powerAt1AU);

    set(deployedDistance, discrete(2.0));
    double powerAt2AU = currentValue(deployedArray.powerProduction);

    // 1/r²: 2x distance -> 1/4 power.
    assertEquals(powerAt1AU / 4.0, powerAt2AU, powerAt1AU * 0.001);
  }

  // ---- RTG tests ----

  @Test
  void testRtgDecaysMonotonically() {
    double powerBefore = currentValue(rtg.powerProduction);
    delay(30, Duration.DAYS);
    double powerAfter = currentValue(rtg.powerProduction);

    assertTrue(powerAfter < powerBefore,
        "RTG power should decay; was " + powerBefore + ", " + powerAfter + " 30 d later");
    // 50 %/yr * (30/365.25)yr -> ~4 % drop. Generous slack for the linear approximation.
    assertTrue(powerAfter > powerBefore * 0.9,
        "RTG decay unexpectedly large: " + powerBefore + " -> " + powerAfter + " in 30 days");
  }
}
