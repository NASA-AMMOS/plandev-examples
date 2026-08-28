package examples.data;

import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.data.Data;
import gov.nasa.ammos.plandev.data.DataMissionModel;

import java.util.Optional;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources.discreteResource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.*;

/**
 * Mission is the PlanDev mission model that is instantiated at the start of simulation.  This is where
 * resources are created and registered to be included in the simulation results.
 * <p/>
 * The DataMissionModel interface enables activities to access the Data object with the bins and resources.
 */
public class Mission implements DataMissionModel {

  /**
   * A resource specifying the spacecraft's data rate for playback to ground in bits per second.
   */
  public final MutableResource<Discrete<Double>> dataRate; // bps

  /**
   * This is a cap on the spacecraft's data storage.
   */
  public final MutableResource<Discrete<Double>> maxVolune; // bits

  /**
   * This is the interface to data Buckets and corresponding resources from the model package.
   */
  public Data data;

  public Mission(gov.nasa.ammos.plandev.merlin.framework.Registrar registrar, Configuration config) {
    Registrar newRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Throw);

    this.dataRate = discreteResource(config.initialDatarate()); // bps
    this.maxVolune = discreteResource(config.initialMaxVolume()); // bits

    // Two buckets/bins for the spacecraft and two for ground are created here by passing in 2 below.
    // The ground bins track how much data has been played back/downloaded from the spacecraft.
    // bin0 is higher priority than bin 1.
    // The parent bucket has a limit of 10Gb (by default from the Configuration).
    this.data = new Data(Optional.of(asPolynomial(dataRate)), 2, asPolynomial(maxVolune));
    data.registerStates(newRegistrar);
  }

  @Override
  public Data getData() {
    return data;
  }
}
