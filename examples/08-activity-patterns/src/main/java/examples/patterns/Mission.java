package examples.patterns;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.IntegerValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;

import java.time.Instant;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;

public class Mission {

    public final MutableResource<Discrete<InstrumentMode>> instrumentMode;
    public final MutableResource<Discrete<Double>> powerDraw;
    public final MutableResource<Discrete<Integer>> operationCount;

    public Mission(final gov.nasa.ammos.plandev.merlin.framework.Registrar registrar,
                   final Instant planStart,
                   final Configuration config) {

        this.instrumentMode = resource(discrete(InstrumentMode.IDLE));
        this.powerDraw = resource(discrete(0.0));
        this.operationCount = resource(discrete(0));

        final var errorRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Log);
        errorRegistrar.discrete("instrumentMode", instrumentMode, new EnumValueMapper<>(InstrumentMode.class));
        errorRegistrar.discrete("powerDraw", powerDraw, new DoubleValueMapper());
        errorRegistrar.discrete("operationCount", operationCount, new IntegerValueMapper());
    }
}
