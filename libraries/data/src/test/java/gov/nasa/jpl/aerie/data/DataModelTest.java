package gov.nasa.jpl.aerie.data;

import gov.nasa.jpl.aerie.contrib.streamline.core.MutableResource;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.jpl.aerie.merlin.framework.junit.MerlinExtension;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestInstance.Lifecycle;
import org.junit.jupiter.api.extension.ExtendWith;

import java.util.Optional;

import static gov.nasa.jpl.aerie.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteResources.discreteResource;
import static gov.nasa.jpl.aerie.contrib.streamline.modeling.polynomial.PolynomialResources.asPolynomial;
import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;
import static gov.nasa.jpl.aerie.merlin.protocol.types.Duration.SECOND;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Simulation tests for {@link Data} and {@link Bucket}.
 *
 * <p>Uses {@link MerlinExtension} to drive a streamline simulation context directly:
 * the constructor builds a {@link Data} instance and test methods invoke bin
 * operations via {@link gov.nasa.jpl.aerie.merlin.framework.ModelActions}.
 *
 * <p>Setup: 2 onboard bins (bin 0 higher priority than bin 1), parent capacity
 * 1e10 bits, downlink rate 1e4 bps. Bin names follow {@link Data}'s convention:
 * {@code scBin0}, {@code scBin1}, {@code gndBin0}, {@code gndBin1}.
 */
@ExtendWith(MerlinExtension.class)
@TestInstance(Lifecycle.PER_CLASS)
public class DataModelTest {

  private final Data data;

  public DataModelTest() {
    MutableResource<Discrete<Double>> dataRate = discreteResource(1e4);
    MutableResource<Discrete<Double>> maxVolume = discreteResource(1e10);
    this.data = new Data(Optional.of(asPolynomial(dataRate)), 2, asPolynomial(maxVolume));
  }

  /** A fresh model has zero volume in every bin. */
  @Test
  void testInitialBinVolumesAreZero() {
    assertEquals(0.0, currentValue(data.getOnboardBin(0).volume));
    assertEquals(0.0, currentValue(data.getOnboardBin(1).volume));
    assertEquals(0.0, currentValue(data.onboard.volume));
  }

  /** receive() on a bin raises that bin's volume and the parent onboard volume. */
  @Test
  void testReceiveRaisesBinVolume() {
    data.getOnboardBin(0).receive(100.0, Duration.of(10, SECOND));
    delay(11, SECOND);

    assertEquals(1000.0, currentValue(data.getOnboardBin(0).volume), 0.5);
    assertEquals(0.0,    currentValue(data.getOnboardBin(1).volume));
    assertEquals(1000.0, currentValue(data.onboard.volume), 0.5);
  }

  /**
   * A pending downlink request causes the corresponding ground bin to accumulate
   * the downlinked data. The onboard bin's volume is unchanged — downlink in this
   * model is logical (tracked via {@code onboard.received - ground.received}),
   * not physical. Physical removal happens via {@code DeleteData}.
   */
  @Test
  void testPlaybackTransfersToGround() {
    data.getOnboardBin(0).receive(1000.0, Duration.of(10, SECOND));
    delay(11, SECOND);
    assertEquals(10_000.0, currentValue(data.getOnboardBin(0).volume), 1.0);

    MutableResource.set(data.volumeRequestedToDownlink,
        gov.nasa.jpl.aerie.contrib.streamline.modeling.polynomial.Polynomial.polynomial(10_000.0));
    delay(2, SECOND);

    double gnd = currentValue(data.getGroundBin(0).volume);
    assertTrue(gnd >= 9_000.0, "ground bin should hold most of the data, was " + gnd);
    assertEquals(10_000.0, currentValue(data.getOnboardBin(0).volume), 1.0); // unchanged
  }

  /**
   * With data in both bins and a finite downlink rate, the higher-priority bin
   * (bin 0) is downlinked before bin 1 starts.
   */
  @Test
  void testPriorityOrderingDuringPlayback() {
    // 5_000 bits into each bin.
    data.getOnboardBin(0).receive(1000.0, Duration.of(5, SECOND));
    data.getOnboardBin(1).receive(1000.0, Duration.of(5, SECOND));
    delay(6, SECOND);
    assertEquals(5_000.0, currentValue(data.getOnboardBin(0).volume), 1.0);
    assertEquals(5_000.0, currentValue(data.getOnboardBin(1).volume), 1.0);

    // Request a 5_000-bit downlink at 1e4 bps -> takes ~0.5s. Sample at 2s.
    MutableResource.set(data.volumeRequestedToDownlink,
        gov.nasa.jpl.aerie.contrib.streamline.modeling.polynomial.Polynomial.polynomial(5_000.0));
    delay(2, SECOND);

    double gndBin0 = currentValue(data.getGroundBin(0).volume);
    double gndBin1 = currentValue(data.getGroundBin(1).volume);

    assertTrue(gndBin0 >= 4_500.0, "bin 0 should drain first (got " + gndBin0 + ")");
    assertTrue(gndBin1 < 500.0,    "bin 1 should not start until bin 0 is empty (got " + gndBin1 + ")");
  }
}
