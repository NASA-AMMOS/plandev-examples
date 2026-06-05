package examples.orbiter;

import gov.nasa.jpl.aerie.merlin.framework.annotations.Export;
import examples.orbiter.data.DataModelSimConfig;
import gov.nasa.jpl.aerie.power.ArrayDeploymentStates;
import gov.nasa.jpl.aerie.power.BatterySimConfig;
import gov.nasa.jpl.aerie.power.PowerModelSimConfig;
import gov.nasa.jpl.aerie.power.SolarArraySimConfig;

import java.nio.file.Path;
import java.util.Map;

import static gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Template;

public record Configuration(Integer spiceSpacecraftId,
                            PowerModelSimConfig powerConfig,
                            DataModelSimConfig dataConfig,
                            Double offPointAngle) {

  public static final Integer DEFAULT_SPICE_SCID = -74; // MRO

  // Representative Mars-orbiter power configuration: a ~16 m^2 array and 94.5 Ah battery.
  // Uses the library power types but keeps orbiter-specific values rather than the library's
  // generic defaults (5 m^2 / 100 Ah). Order: deploymentState, mechArea, packingFactor,
  // cellEfficiency, conversionEfficiency, otherLosses; battery: capacity(Ah), busVoltage(V), SOC(%).
  public static final PowerModelSimConfig POWER_CONFIG = new PowerModelSimConfig(
      new BatterySimConfig(94.5, 28.0, 100.0),
      new SolarArraySimConfig(ArrayDeploymentStates.DEPLOYED, 16.0, 1.0, 0.295, 0.9, 0.9));

  public static final DataModelSimConfig DATA_CONFIG = DataModelSimConfig.defaultConfiguration();

  public static final Double DEFAULT_OFF_POINT_ANGLE = 70.0; // Worst case off point

  public static @Template Configuration defaultConfiguration() {
    return new Configuration(DEFAULT_SPICE_SCID, POWER_CONFIG, DATA_CONFIG, DEFAULT_OFF_POINT_ANGLE);
  }
}
