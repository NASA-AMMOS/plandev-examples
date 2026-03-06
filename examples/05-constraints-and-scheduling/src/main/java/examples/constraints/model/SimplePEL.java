package examples.constraints.model;

import gov.nasa.jpl.aerie.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.jpl.aerie.contrib.serialization.mappers.EnumValueMapper;
import gov.nasa.jpl.aerie.contrib.streamline.core.MutableResource;
import gov.nasa.jpl.aerie.contrib.streamline.core.Resource;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.Registrar;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.Discrete;

import static gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteResources.add;
import static gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad.map;

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
    registrar.discrete("/pel/cameraState", cameraState, new EnumValueMapper<>(CameraState.class));
    registrar.discrete("/pel/cameraLoad", cameraLoad, new DoubleValueMapper());
    registrar.discrete("/pel/telecomState", telecomState, new EnumValueMapper<>(TelecomState.class));
    registrar.discrete("/pel/telecomLoad", telecomLoad, new DoubleValueMapper());
    registrar.discrete("/pel/totalLoad", totalLoad, new DoubleValueMapper());
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
