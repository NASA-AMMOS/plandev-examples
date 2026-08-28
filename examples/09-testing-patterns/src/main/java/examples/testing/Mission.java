package examples.testing;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.IntegerValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;

public final class Mission {

  public final MutableResource<Discrete<Double>> batterySOC;
  public final MutableResource<Discrete<Integer>> dataVolume;

  public Mission(final gov.nasa.ammos.plandev.merlin.framework.Registrar registrar, final Configuration config) {
    final var errorRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Log);

    this.batterySOC = resource(discrete(config.initialSOC()));
    errorRegistrar.discrete("BatterySOC", this.batterySOC, new DoubleValueMapper());

    this.dataVolume = resource(discrete(config.initialDataVolume()));
    errorRegistrar.discrete("DataVolume", this.dataVolume, new IntegerValueMapper());
  }
}
