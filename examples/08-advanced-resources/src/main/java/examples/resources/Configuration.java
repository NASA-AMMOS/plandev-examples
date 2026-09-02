package examples.resources;

import static gov.nasa.ammos.plandev.merlin.framework.annotations.Export.Template;

/**
 * Mission model configuration.
 *
 * @param batteryCapacityWh  Battery capacity in watt-hours
 * @param initialSocPercent  Initial state of charge as a percentage (0-100)
 */
public record Configuration(
    double batteryCapacityWh,
    double initialSocPercent
) {
    public static @Template Configuration defaultConfiguration() {
        return new Configuration(100.0, 80.0);
    }
}
