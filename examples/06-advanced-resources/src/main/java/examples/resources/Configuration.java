package examples.resources;

import static gov.nasa.jpl.aerie.merlin.framework.annotations.Export.Template;

/**
 * Mission model configuration.
 *
 * @param batteryCapacityWh  Battery capacity in watt-hours
 * @param initialSocPercent  Initial state of charge as a percentage (0-100)
 * @param instrumentPowerW   Steady-state instrument power draw in watts
 */
public record Configuration(
    double batteryCapacityWh,
    double initialSocPercent,
    double instrumentPowerW
) {
    public static @Template Configuration defaultConfiguration() {
        return new Configuration(100.0, 80.0, 25.0);
    }
}
