package examples.combined;

import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources.add;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad.map;

/**
 * Simplified power equipment list for the combined example.
 * Tracks camera and telecom power states and their loads.
 */
public class SimplePEL {

  public final MutableResource<Discrete<CameraState>> cameraState;
  public final Resource<Discrete<Double>> cameraLoad;

  public final MutableResource<Discrete<TelecomState>> telecomState;
  public final Resource<Discrete<Double>> telecomLoad;

  public final Resource<Discrete<Double>> totalLoad;

  public SimplePEL() {
    this.cameraState = MutableResource.resource(Discrete.discrete(CameraState.OFF));
    this.cameraLoad = map(cameraState, CameraState::getLoad);

    this.telecomState = MutableResource.resource(Discrete.discrete(TelecomState.OFF));
    this.telecomLoad = map(telecomState, TelecomState::getLoad);

    this.totalLoad = add(cameraLoad, telecomLoad);
  }

  public void registerStates(Registrar registrar) {
    registrar.discrete("/pel/cameraState", cameraState, new gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper<>(CameraState.class));
    registrar.discrete("/pel/cameraLoad", cameraLoad, new gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper());
    registrar.discrete("/pel/telecomState", telecomState, new gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper<>(TelecomState.class));
    registrar.discrete("/pel/telecomLoad", telecomLoad, new gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper());
    registrar.discrete("/pel/totalLoad", totalLoad, new gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper());
  }

  public enum CameraState {
    OFF(0.0), ON(48.0);
    private final double load;
    CameraState(double load) { this.load = load; }
    public double getLoad() { return load; }
  }

  public enum TelecomState {
    OFF(0.0), ON(35.0);
    private final double load;
    TelecomState(double load) { this.load = load; }
    public double getLoad() { return load; }
  }
}
