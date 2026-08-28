package examples.orbiter.radar;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import examples.orbiter.Configuration;

import static gov.nasa.ammos.plandev.contrib.metadata.UnitRegistrar.withUnit;
import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad.map;

public class RadarModel {

  public MutableResource<Discrete<RadarDataCollectionMode>> RadarDataMode;

  public Resource<Discrete<Double>> RadarDataRate; // kbps

  public RadarModel(Registrar registrar, Configuration config) {
    RadarDataMode = resource(discrete(RadarDataCollectionMode.OFF));
    registrar.discrete("RadarDataMode",RadarDataMode, new EnumValueMapper<>(RadarDataCollectionMode.class));

    RadarDataRate = map(RadarDataMode, RadarDataCollectionMode::getDataRate);
    registrar.discrete("RadarDataRate", RadarDataRate, withUnit("Mbps", new DoubleValueMapper()));
  }

}
