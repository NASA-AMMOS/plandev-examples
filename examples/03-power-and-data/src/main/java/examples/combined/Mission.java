package examples.combined;

import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.data.Data;
import gov.nasa.ammos.plandev.data.DataMissionModel;
import gov.nasa.ammos.plandev.power.BatteryModel;
import gov.nasa.ammos.plandev.power.GenericSolarArray;
import gov.nasa.ammos.plandev.power.PowerSource;

import java.time.Instant;
import java.util.Optional;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources.discreteResource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.asPolynomial;

/**
 * Combined mission model demonstrating how to compose the power and data libraries.
 *
 * This model integrates:
 * - Power subsystem: PEL (power equipment list), solar array, battery
 * - Data subsystem: onboard storage buckets with playback to ground
 *
 * Activities like TakePicture affect both subsystems simultaneously:
 * the camera draws power while generating science data.
 */
public class Mission implements DataMissionModel {

  // Power subsystem
  public final SimplePEL pel;
  public final PowerSource powerSource;
  public final BatteryModel battery;

  // Data subsystem
  public final MutableResource<Discrete<Double>> dataRate;
  public final MutableResource<Discrete<Double>> maxVolume;
  public final Data data;

  public Mission(final gov.nasa.ammos.plandev.merlin.framework.Registrar registrar,
                 final Instant planStart,
                 final Configuration config) {
    final var reg = new Registrar(registrar, Registrar.ErrorBehavior.Log);

    // Initialize power subsystem
    this.pel = new SimplePEL();

    // Constant orbit parameters: 1 AU from Sun, array facing Sun, no eclipse
    var solarDistance = discreteResource(1.0);  // AU
    var arrayAngle = discreteResource(0.0);     // degrees
    var eclipseFactor = discreteResource(1.0);  // no eclipse

    this.powerSource = new GenericSolarArray(
        config.powerConfig().powerSourceConfig(), solarDistance, arrayAngle, eclipseFactor);
    this.battery = new BatteryModel("mainbattery", config.powerConfig().batteryConfig(),
        pel.totalLoad, powerSource.getPowerProduction());

    pel.registerStates(reg);
    powerSource.registerStates(reg);
    battery.registerStates(reg);

    // Initialize data subsystem
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
