package hopper;

import gov.nasa.jpl.aerie.contrib.streamline.core.MutableResource;
import gov.nasa.jpl.aerie.contrib.streamline.core.Resource;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.Registrar;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.Discrete;

import static gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteResources.add;
import static gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad.map;

import hopper.SimplePEL.CameraState;
import hopper.SimplePEL.HopState;
import hopper.SimplePEL.TelecomState;

/**
 * Simplified power equipment list
 * Tracks activity and telecom power states and their loads.
 */
public class SimplePEL {

  public final MutableResource<Discrete<CameraState>> cameraState;
  public final Resource<Discrete<Double>> cameraLoad;

  public final MutableResource<Discrete<HopState>> hopState;
  public final Resource<Discrete<Double>> hopLoad;

  public final MutableResource<Discrete<TelecomState>> telecomState;
  public final Resource<Discrete<Double>> telecomLoad;

  public final Resource<Discrete<Double>> totalLoad;

  public SimplePEL() {
    this.cameraState = MutableResource.resource(Discrete.discrete(CameraState.OFF));
    this.cameraLoad = map(cameraState, CameraState::getLoad);
    
    this.hopState = MutableResource.resource(Discrete.discrete(HopState.OFF));
    this.hopLoad = map(hopState, HopState::getLoad);

    this.telecomState = MutableResource.resource(Discrete.discrete(TelecomState.OFF));
    this.telecomLoad = map(telecomState, TelecomState::getLoad);

    this.totalLoad = add(cameraLoad, hopLoad, telecomLoad);
  }

  public void registerStates(Registrar registrar) {
    registrar.discrete("/pel/cameraState", cameraState, new gov.nasa.jpl.aerie.contrib.serialization.mappers.EnumValueMapper<>(CameraState.class));
    registrar.discrete("/pel/cameraLoad", cameraLoad, new gov.nasa.jpl.aerie.contrib.serialization.mappers.DoubleValueMapper());
    registrar.discrete("/pel/hopState", hopState, new gov.nasa.jpl.aerie.contrib.serialization.mappers.EnumValueMapper<>(HopState.class));
    registrar.discrete("/pel/hopLoad", hopLoad, new gov.nasa.jpl.aerie.contrib.serialization.mappers.DoubleValueMapper());
    registrar.discrete("/pel/telecomState", telecomState, new gov.nasa.jpl.aerie.contrib.serialization.mappers.EnumValueMapper<>(TelecomState.class));
    registrar.discrete("/pel/telecomLoad", telecomLoad, new gov.nasa.jpl.aerie.contrib.serialization.mappers.DoubleValueMapper());
    registrar.discrete("/pel/totalLoad", totalLoad, new gov.nasa.jpl.aerie.contrib.serialization.mappers.DoubleValueMapper());
  }

  public enum CameraState {
    OFF(0.0), ON(48.0);
    private final double load;
    CameraState(double load) { this.load = load; }
    public double getLoad() { return load; }
  }
  
  public enum HopState {
    OFF(0.0), ON(100.0);
    private final double load;
    HopState(double load) { this.load = load; }
    public double getLoad() { return load; }
  }

  public enum TelecomState {
    OFF(0.0), ON(35.0);
    private final double load;
    TelecomState(double load) { this.load = load; }
    public double getLoad() { return load; }
  }
}
