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
import static gov.nasa.jpl.aerie.merlin.protocol.types.Duration.SECOND;
import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Regression guard for the {@link Bucket} per-bin upper-bound logic at a high bin count.
 *
 * <p>This builds a {@link Data} model with {@code BIN_COUNT} = 20 — matching the orbiter
 * example's default. An earlier {@link Bucket} version derived each bin's {@code volume_ub}
 * from the previous bin's ({@code volume_ub[i] = min(own, volume_ub[i-1] - clampedVolume[i-1])}),
 * which referenced {@code volume_ub[i-1]} twice. Because streamline derived resources are not
 * memoized across references, evaluating the deepest bin's dynamics fanned out as
 * {@code O(2^binCount)} — so simply <em>constructing</em> this model (which samples rate
 * dynamics in {@code finishInit}) pegged a CPU for minutes and hung Aerie model instantiation
 * (resource-type extraction). With each bin bounded directly by the shared parent capacity the
 * graph is {@code O(n)}, so construction below returns effectively instantly.
 *
 * <p>If the cascade is ever reintroduced without caching, this test will hang rather than
 * complete — surfacing the regression instead of letting it reach Aerie.
 */
@ExtendWith(MerlinExtension.class)
@TestInstance(Lifecycle.PER_CLASS)
public class DataModelManyBinsTest {

  private static final int BIN_COUNT = 20;

  private final Data data;

  public DataModelManyBinsTest() {
    MutableResource<Discrete<Double>> dataRate = discreteResource(1e4);
    MutableResource<Discrete<Double>> maxVolume = discreteResource(1e10);
    // Construction with 20 bins is the operation that hung before the fix.
    this.data = new Data(Optional.of(asPolynomial(dataRate)), BIN_COUNT, asPolynomial(maxVolume));
  }

  /** A fresh 20-bin model constructs and every bin starts at zero volume. */
  @Test
  void testManyBinsConstructWithZeroVolume() {
    for (int i = 0; i < BIN_COUNT; ++i) {
      assertEquals(0.0, currentValue(data.getOnboardBin(i).volume),
          "onboard bin " + i + " should start empty");
    }
    assertEquals(0.0, currentValue(data.onboard.volume));
  }

  /** A receive into the lowest-priority bin still works with many bins present. */
  @Test
  void testReceiveIntoLastBin() {
    data.getOnboardBin(BIN_COUNT - 1).receive(100.0, Duration.of(10, SECOND));
    delayOneSecondPast(10);

    assertEquals(1000.0, currentValue(data.getOnboardBin(BIN_COUNT - 1).volume), 0.5);
    assertEquals(0.0,    currentValue(data.getOnboardBin(0).volume));
    assertEquals(1000.0, currentValue(data.onboard.volume), 0.5);
  }

  private static void delayOneSecondPast(int seconds) {
    gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay(seconds + 1, SECOND);
  }
}
