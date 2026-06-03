package gov.nasa.jpl.aerie.telecom;

import gov.nasa.jpl.aerie.contrib.streamline.core.Resource;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.jpl.aerie.contrib.streamline.unit_aware.UnitAware;
import gov.nasa.jpl.aerie.merlin.framework.junit.MerlinExtension;
import gov.nasa.jpl.aerie.merlin.protocol.types.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.extension.ExtendWith;

import java.time.Instant;
import java.util.List;

import static gov.nasa.jpl.aerie.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.jpl.aerie.contrib.streamline.unit_aware.Quantities.quantity;
import static gov.nasa.jpl.aerie.contrib.streamline.unit_aware.StandardUnits.MEGABIT_PER_SECOND;
import static gov.nasa.jpl.aerie.contrib.streamline.unit_aware.StandardUnits.METER;
import static gov.nasa.jpl.aerie.contrib.streamline.unit_aware.StandardUnits.WATT;
import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;
import static gov.nasa.jpl.aerie.telecom.TelecomModel.Band.KA_BAND;
import static gov.nasa.jpl.aerie.telecom.TelecomModel.Band.X_BAND;
import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Pins the Friis link-equation arithmetic in {@link TelecomModel}: builds a spacecraft
 * (HGA + LGA) and 6 DSN ground stations, then asserts the X-band bit-rate capability
 * between HGA and DSN-CANBERRA-70m after the daemon ticks.
 *
 * <p>Uses a tiny inline {@link GeometryModel} stub (fixed 384,000 km distance, always
 * visible) so the daemon's geometry lookups don't NPE. The real long-term integration
 * — wiring telecom to {@code libraries/geometry}'s SPICE-backed geometry — is tracked
 * in the library README.
 */
@ExtendWith(MerlinExtension.class)
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class TelecomModelTest {
  private final TelecomModel telecomModel;
  private final Resource<Discrete<Double>> hgaToCanberra70mAtXBandMbps;

  /** Minimal stand-in for a real geometry model so the daemon can run. */
  static final class FixedDistanceGeometry implements GeometryModel<String> {
    private final UnitAware<Double> distance = quantity(384_000_000, METER);

    @Override public UnitAware<Double> getDistanceBetween(String b1, String b2) { return distance; }
    @Override public boolean isVisible(String b1, String b2) { return true; }
    @Override public List<ViewPeriod> getViewPeriods(
        String b1, String b2, Instant start, Duration duration, UnitAware<Double> minElevation) {
      return List.of();
    }
  }

  public TelecomModelTest() {
    telecomModel = new TelecomModel(new FixedDistanceGeometry(), List.of(
        new TelecomValueMappers.AntennaConfig<>(
            "HGA",
            TelecomValueMappers.AntennaType.HIGH_GAIN,
            quantity(1, METER),
            List.of(new TelecomValueMappers.BandPower(X_BAND, quantity(100, WATT))),
            "ENDURANCE"),
        new TelecomValueMappers.AntennaConfig<>(
            "LGA",
            TelecomValueMappers.AntennaType.LOW_GAIN,
            quantity(1, METER),
            List.of(new TelecomValueMappers.BandPower(KA_BAND, quantity(10, WATT))),
            "ENDURANCE")
    ), List.of(
        new TelecomValueMappers.AntennaConfig<>(
            "DSN-CANBERRA-70m",
            TelecomValueMappers.AntennaType.HIGH_GAIN,
            quantity(70, METER),
            List.of(
                new TelecomValueMappers.BandPower(X_BAND,  quantity(1000, WATT)),
                new TelecomValueMappers.BandPower(KA_BAND, quantity(100,  WATT))
            ),
            "CANBERRA"),
        new TelecomValueMappers.AntennaConfig<>(
            "DSN-CANBERRA-34m",
            TelecomValueMappers.AntennaType.HIGH_GAIN,
            quantity(34, METER),
            List.of(
                new TelecomValueMappers.BandPower(X_BAND,  quantity(800, WATT)),
                new TelecomValueMappers.BandPower(KA_BAND, quantity(79,  WATT))
            ),
            "CANBERRA"),
        new TelecomValueMappers.AntennaConfig<>(
            "DSN-MADRID-70m",
            TelecomValueMappers.AntennaType.HIGH_GAIN,
            quantity(70, METER),
            List.of(
                new TelecomValueMappers.BandPower(X_BAND,  quantity(1000, WATT)),
                new TelecomValueMappers.BandPower(KA_BAND, quantity(100,  WATT))
            ),
            "MADRID"),
        new TelecomValueMappers.AntennaConfig<>(
            "DSN-MADRID-34m",
            TelecomValueMappers.AntennaType.HIGH_GAIN,
            quantity(34, METER),
            List.of(
                new TelecomValueMappers.BandPower(X_BAND,  quantity(800, WATT)),
                new TelecomValueMappers.BandPower(KA_BAND, quantity(79,  WATT))
            ),
            "MADRID"),
        new TelecomValueMappers.AntennaConfig<>(
            "DSN-GOLDSTONE-70m",
            TelecomValueMappers.AntennaType.HIGH_GAIN,
            quantity(70, METER),
            List.of(
                new TelecomValueMappers.BandPower(X_BAND,  quantity(1000, WATT)),
                new TelecomValueMappers.BandPower(KA_BAND, quantity(100,  WATT))
            ),
            "GOLDSTONE"),
        new TelecomValueMappers.AntennaConfig<>(
            "DSN-GOLDSTONE-34m",
            TelecomValueMappers.AntennaType.HIGH_GAIN,
            quantity(34, METER),
            List.of(
                new TelecomValueMappers.BandPower(X_BAND,  quantity(800, WATT)),
                new TelecomValueMappers.BandPower(KA_BAND, quantity(79,  WATT))
            ),
            "GOLDSTONE")
    ));

    // Cache the unit-stripped resource in init context — value(unit) allocates a derived
    // resource cell each call, which is illegal during simulation.
    var config = new TelecomModel.CommunicationConfiguration("HGA", "DSN-CANBERRA-70m", X_BAND);
    this.hgaToCanberra70mAtXBandMbps = telecomModel.downlinkBitRateCapability.get(config).value(MEGABIT_PER_SECOND);

    // Force the Resources class to initialize now (init context) — its <clinit>
    // allocates resources, which is illegal once simulation starts.
    currentValue(hgaToCanberra70mAtXBandMbps);
  }

  /**
   * Regression baseline for the Friis arithmetic in {@link TelecomModel#computeBitRate}.
   * The expected value is what the current library produces for the configured inputs at
   * the stub geometry's fixed 384,000 km distance; we don't have a separately validated
   * reference (the upstream test's hard-coded 1700.42 Mbps was set before geometryModel
   * was ever passed in, and that test never ran to completion).
   */
  @Test
  void testHgaToCanberra70mBitRateAtXBand() {
    delay(10, Duration.SECONDS);
    assertEquals(1.6605699601350263, currentValue(hgaToCanberra70mAtXBandMbps));
  }
}
