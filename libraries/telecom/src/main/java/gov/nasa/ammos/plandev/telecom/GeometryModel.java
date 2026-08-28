package gov.nasa.ammos.plandev.telecom;

import gov.nasa.ammos.plandev.contrib.streamline.unit_aware.UnitAware;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import java.time.Instant;
import java.util.List;

public interface GeometryModel<BodyId> {
//    Resource<UnitAware<Double>> distanceBetweenResource(BodyId body1, BodyId body2);
    UnitAware<Double> getDistanceBetween(BodyId body1, BodyId body2);

    // Activity 1 -> claim(Camera, 1)
    // Activity 2 -> claim(Camera, 2)

    // Shared resources across models?

    // MutableResource vs Resourcet

    boolean isVisible(BodyId name, BodyId name1);

    List<ViewPeriod> getViewPeriods(BodyId body1, BodyId body2, Instant startTime, Duration duration, UnitAware<Double> minElevation);

    // A view period is whenever two antennae are within line-of-sight of each other
    // This "time" may be different for each antenna, since it occurs at two different sites
    // This does NOT take into account antenna pointing - the assumption is that with enough advance notice, the antenna can be pointed in the right direction in time to communicate
    record ViewPeriod(Instant startTimeTransmitter, Instant startTimeReceiver, Duration duration, UnitAware<Double> averageDistance) {}

    // Observer vs Target. Define view period from perspective of "Observer"
    // TODO Minimum elevation (different for transmit/receive), + horizon mask
}
