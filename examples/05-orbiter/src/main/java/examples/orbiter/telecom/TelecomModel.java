package examples.orbiter.telecom;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;

import static gov.nasa.ammos.plandev.contrib.metadata.UnitRegistrar.withUnit;
import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;

/**
 * Simplified telecom model stub.
 *
 * Tracks downlink bit rate as a simple discrete resource. For a full telecom model
 * with DSN antenna configurations, link budget calculations, and geometry-driven
 * view periods, see the telecom library ({@code gov.nasa.ammos.plandev.telecom.TelecomModel}).
 */
public class TelecomModel {

  public MutableResource<Discrete<Double>> downlinkBitRate;

  public TelecomModel() {
    this.downlinkBitRate = resource(discrete(0.0));
  }

  public void registerResources(final Registrar registrar) {
    registrar.discrete("downlinkBitRate", downlinkBitRate, withUnit("bps", new DoubleValueMapper()));
  }
}
