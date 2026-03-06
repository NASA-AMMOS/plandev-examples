package examples.constraints.model;

import gov.nasa.jpl.aerie.contrib.streamline.core.MutableResource;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.Registrar;
import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.jpl.aerie.data.Data;
import gov.nasa.jpl.aerie.data.DataMissionModel;
import gov.nasa.jpl.aerie.power.BatteryModel;
import gov.nasa.jpl.aerie.power.GenericSolarArray;
import gov.nasa.jpl.aerie.power.PowerSource;

import java.time.Instant;
import java.util.Optional;

import static gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteResources.discreteResource;
import static gov.nasa.jpl.aerie.contrib.streamline.modeling.polynomial.PolynomialResources.asPolynomial;

/**
 * Simple spacecraft model for demonstrating constraints and scheduling.
 * Composes power and data subsystems, providing named resources that
 * constraint and scheduling procedures can query.
 */
public class Mission implements DataMissionModel {

  public final SimplePEL pel;
  public final PowerSource powerSource;
  public final BatteryModel battery;

  public final MutableResource<Discrete<Double>> dataRate;
  public final MutableResource<Discrete<Double>> maxVolume;
  public final Data data;

  public Mission(final gov.nasa.jpl.aerie.merlin.framework.Registrar registrar,
                 final Instant planStart,
                 final Configuration config) {
    final var reg = new Registrar(registrar, Registrar.ErrorBehavior.Log);

    // Power subsystem
    this.pel = new SimplePEL();
    var solarDistance = discreteResource(1.0);
    var arrayAngle = discreteResource(0.0);
    var eclipseFactor = discreteResource(1.0);
    this.powerSource = new GenericSolarArray(
        config.powerConfig().powerSourceConfig(), solarDistance, arrayAngle, eclipseFactor);
    this.battery = new BatteryModel("main", config.powerConfig().batteryConfig(),
        pel.totalLoad, powerSource.getPowerProduction());

    pel.registerStates(reg);
    powerSource.registerStates(reg);
    battery.registerStates(reg);

    // Data subsystem
    this.dataRate = discreteResource(config.initialDataRate());
    this.maxVolume = discreteResource(config.initialMaxVolume());
    this.data = new Data(Optional.of(asPolynomial(dataRate)), 2, asPolynomial(maxVolume));
    data.registerStates(reg);
  }

  @Override
  public Data getData() {
    return data;
  }
}
