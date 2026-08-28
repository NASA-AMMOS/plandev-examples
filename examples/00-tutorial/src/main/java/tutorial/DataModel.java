package tutorial;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Reactions;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.Clock;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.ClockEffects;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad.map;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.asPolynomial;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.scale;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;

public class DataModel {

    public MutableResource<Discrete<Double>> RecordingRate; // Megabits/s

    public MutableResource<Discrete<MagDataCollectionMode>> MagDataMode;

    public Resource<Discrete<Double>> MagDataRate; // kbps

    public MutableResource<Discrete<Double>> SSR_Volume_Simple; // Gigabits

    public MutableResource<Discrete<Double>> SSR_Volume_Sampled; // Gigabits

    private final Duration INTEGRATION_SAMPLE_INTERVAL; // = Duration.duration(60, Duration.SECONDS);

    public MutableResource<Discrete<Double>> SSR_Volume_UponRateChange; // Gigabits

    private MutableResource<Clock> TimeSinceLastRateChange;

    private Double previousRecordingRate; // = 0.0;

    public Resource<Polynomial> SSR_Volume_Polynomial;  // Gigabits

    // private final Double SSR_MAX_CAPACITY = 250.0; // Gigabits

    public Resource<Polynomial> RecordingRate_UnitAware;  // Mbps
    public Resource<Polynomial> SSR_Volume_UnitAware;  // Gigabits

    public DataModel(Registrar registrar, Configuration config) {
        MagDataMode = resource(discrete(config.startingMagMode()));
        registrar.discrete("MagDataMode",MagDataMode, new EnumValueMapper<>(MagDataCollectionMode.class));

        MagDataRate = map(MagDataMode, MagDataCollectionMode::getDataRate);
        registrar.discrete("MagDataRate", MagDataRate, new DoubleValueMapper());

        RecordingRate = resource(discrete(currentValue(MagDataRate)/1e3));
        registrar.discrete("RecordingRate", RecordingRate, new DoubleValueMapper());
        previousRecordingRate = currentValue(RecordingRate);

        //
        // Integration Method 1 - Accumulate all volume at the end of the activity
        //
        SSR_Volume_Simple = resource(discrete(0.0));
        registrar.discrete("SSR_Volume_Simple", SSR_Volume_Simple, new DoubleValueMapper());

        //
        // Integration Method 2 - Sample-based integration
        //
        SSR_Volume_Sampled = resource(discrete(0.0));
        registrar.discrete("SSR_Volume_Sampled", SSR_Volume_Sampled, new DoubleValueMapper());
        INTEGRATION_SAMPLE_INTERVAL = Duration.duration(config.integrationSampleInterval(), Duration.SECONDS);

        //
        // Integration Method 3 - Accumulate data volume upon change to recording rate
        //
        TimeSinceLastRateChange = resource(Clock.clock(Duration.ZERO));

        SSR_Volume_UponRateChange = resource(discrete(0.0));
        registrar.discrete("SSR_Volume_UponRateChange", SSR_Volume_UponRateChange, new DoubleValueMapper());
        Reactions.wheneverUpdates(RecordingRate, this::uponRecordingRateUpdate);

        //
        // Integration Method 4 - Integrated resource
        //
        // Approach 1 - Simple Integrated Resource
//        SSR_Volume_Polynomial = scale(
//          PolynomialResources.integrate(asPolynomial(this.RecordingRate), 0.0), 1e-3); // Gbit
//        registrar.real( "SSR_Volume_Polynomial", PolynomialResources.assumeLinear(SSR_Volume_Polynomial));

        // Approach 2 - Integral with min/max bounds
        var clampedIntegrate = PolynomialResources.clampedIntegrate( scale(
          asPolynomial(this.RecordingRate), 1e-3),
          PolynomialResources.constant(0.0),
          PolynomialResources.constant(config.ssrMaxCapacity()),
          0.0);
        SSR_Volume_Polynomial = clampedIntegrate.integral();
        registrar.real( "SSR_Volume_Polynomial", PolynomialResources.assumeLinear(SSR_Volume_Polynomial));

        //
        // Unit Aware Resources
        //
    }

    public void uponRecordingRateUpdate() {
        // Determine time elapsed since last update
        Duration t = currentValue(TimeSinceLastRateChange);
        // Update volume only if time has actually elapsed
        if (!t.isZero()) {
            DiscreteEffects.increase(this.SSR_Volume_UponRateChange,
              previousRecordingRate * t.ratioOver(Duration.SECONDS) / 1000.0); // Mbit -> Gbit
        }
        previousRecordingRate = currentValue(RecordingRate);
        // Restart clock (set back to zero)
        ClockEffects.restart(TimeSinceLastRateChange);
    }

    // Integrate data volume in the SSR_Volume by sampling the value of the recording rate at a fixed interval
    // This implementation uses the "right" Riemann sum approach to numerical integration, but could easily
    // be modified to another method such as the Trapezoid rule by storing off the previous value of the
    // recording rate at each sample.
    public void integrateSampledSSR() {
        while(true) {
            delay(INTEGRATION_SAMPLE_INTERVAL);
            Double currentRecordingRate = currentValue(RecordingRate);
            DiscreteEffects.increase(SSR_Volume_Sampled, currentRecordingRate *
                INTEGRATION_SAMPLE_INTERVAL.ratioOver(Duration.SECONDS) / 1000.0); // Mbit -> Gbit
        }
    }
}
