package examples.patterns;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.IntegerValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.Clock;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;

import java.time.Instant;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.ClockResources.clock;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.polynomialResource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.integrate;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.assumeLinear;

public class Mission {

    public final MutableResource<Discrete<InstrumentMode>> instrumentMode;
    public final MutableResource<Discrete<Double>> powerDraw;
    public final MutableResource<Discrete<Integer>> operationCount;
    /** Highest powerDraw the monitoring branch has observed. Written only by that branch. */
    public final MutableResource<Discrete<Double>> peakPowerDraw;
    public final Resource<Polynomial> dataVolume;
    public final MutableResource<Polynomial> dataRate;
    public final Resource<Clock> simulationClock;
    public final Configuration configuration;

    public Mission(final gov.nasa.ammos.plandev.merlin.framework.Registrar registrar,
                   final Instant planStart,
                   final Configuration config) {

        this.configuration = config;
        this.instrumentMode = resource(discrete(InstrumentMode.IDLE));
        this.powerDraw = resource(discrete(0.0));
        this.operationCount = resource(discrete(0));
        this.peakPowerDraw = resource(discrete(0.0));
        this.dataRate = polynomialResource(0);
        this.dataVolume = integrate(this.dataRate, config.initialDataVolumeMb());
        this.simulationClock = clock();

        final var errorRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Log);
        errorRegistrar.discrete("instrumentMode", instrumentMode, new EnumValueMapper<>(InstrumentMode.class));
        errorRegistrar.discrete("powerDraw", powerDraw, new DoubleValueMapper());
        errorRegistrar.discrete("operationCount", operationCount, new IntegerValueMapper());
        errorRegistrar.discrete("peakPowerDraw", peakPowerDraw, new DoubleValueMapper());
        errorRegistrar.real("dataRate", assumeLinear(dataRate));
        errorRegistrar.real("dataVolume", assumeLinear(dataVolume));
    }
}
