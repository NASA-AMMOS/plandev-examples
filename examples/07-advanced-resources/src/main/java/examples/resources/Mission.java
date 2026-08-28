package examples.resources;

import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.core.monads.ResourceMonad;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.Clock;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.clocks.ClockResources;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.linear.Linear;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.BooleanValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.serialization.mappers.EnumValueMapper;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import java.time.Instant;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources.discreteResource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.*;

/**
 * Mission model demonstrating all 5 Streamline resource types:
 *
 * 1. Discrete    - instrumentState (ON/OFF enum)
 * 2. Polynomial  - instrumentPowerDraw (continuous power as polynomial)
 * 3. Linear      - dataVolume (accumulates at constant rate while ON)
 * 4. Clock       - instrumentUptime (elapsed time since last power-on)
 * 5. Derived     - totalPower, batterySOC (computed from other resources)
 */
public class Mission {

    // --- Discrete resource: instrument state ---
    public final MutableResource<Discrete<InstrumentState>> instrumentState;

    // --- Polynomial resource: instrument power draw (W) ---
    // When ON, power draw is modeled as a polynomial (e.g. constant + linear warmup term)
    public final MutableResource<Polynomial> instrumentPowerDraw;

    // --- Polynomial resource used for integration: data volume (Mb) ---
    // Data rate feeds into a clamped integral to produce accumulated volume
    public final MutableResource<Polynomial> dataRate;
    public final Resource<Polynomial> dataVolume;

    // --- Clock resource: instrument uptime ---
    public final MutableResource<Clock> instrumentUptime;

    // --- Derived resources ---
    // Baseline (quiescent) spacecraft power
    public final Resource<Polynomial> basePower;
    // Total power = base + instrument
    public final Resource<Polynomial> totalPower;
    // Battery SOC computed from net power consumption
    public final Resource<Polynomial> batterySOC;
    public final Resource<Discrete<Boolean>> batteryLow;

    public Mission(final gov.nasa.ammos.plandev.merlin.framework.Registrar registrar,
                   final Instant planStart,
                   final Configuration config) {

        final var errorRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Log);

        // ========== 1. Discrete: Instrument State ==========
        // A simple enumerated state that changes instantaneously
        this.instrumentState = discreteResource(InstrumentState.OFF);

        // ========== 2. Polynomial: Instrument Power Draw ==========
        // Polynomial resources can represent values that change continuously.
        // coefficients are [value, rate, acceleration, ...] in units of seconds.
        // Start at 0 W (instrument off). Activities set this to e.g. polynomial(25.0, 0.001)
        // meaning 25 W + 0.001 W/s warmup rate.
        this.instrumentPowerDraw = polynomialResource(0.0);

        // ========== 3. Polynomial + Integration: Data Volume ==========
        // Data rate in Mbps; 0 when instrument is off.
        // Activities set this to a constant rate when instrument is on.
        this.dataRate = polynomialResource(0.0);

        // Integrate data rate to get accumulated data volume (Mb).
        // Rate is in Mb/s, integration over seconds gives Mb.
        // Clamped between 0 and 1,000,000 Mb.
        var clampedData = PolynomialResources.clampedIntegrate(
                this.dataRate,
                constant(0.0),
                constant(1_000_000.0),
                0.0);
        this.dataVolume = clampedData.integral();

        // ========== 4. Clock: Instrument Uptime ==========
        // Tracks elapsed time since last power-on.
        // Clock automatically advances with simulation time.
        this.instrumentUptime = resource(Clock.clock(Duration.ZERO));

        // ========== 5. Derived: Total Power and Battery SOC ==========
        // Base spacecraft power: constant 50 W for avionics, heaters, etc.
        this.basePower = constant(50.0);

        // Total power = base + instrument (sum of polynomials)
        this.totalPower = add(this.basePower, this.instrumentPowerDraw);

        // Battery SOC: integrate negative power to simulate discharge.
        // Convert W to Wh by dividing by 3600 (integration is in seconds).
        // SOC = initialCharge - integral(totalPower / 3600)
        // Using clamped integrate: charge decreases from initial, clamped to [0, capacity]
        double initialChargeWh = config.batteryCapacityWh() * config.initialSocPercent() / 100.0;
        var batteryIntegral = PolynomialResources.clampedIntegrate(
                negate(scale(this.totalPower, 1.0 / 3600.0)),
                constant(0.0),
                constant(config.batteryCapacityWh()),
                initialChargeWh);

        // SOC as percentage
        this.batterySOC = multiply(
                batteryIntegral.integral(),
                constant(100.0 / config.batteryCapacityWh()));

        // Derived boolean: battery low when SOC < 20%
        this.batteryLow = PolynomialResources.lessThan(this.batterySOC, 20.0);

        // ========== Register all resources for the PlanDev UI ==========
        registerResources(errorRegistrar, config);
    }

    private void registerResources(Registrar registrar, Configuration config) {
        // Discrete resources need a ValueMapper
        registrar.discrete("instrumentState", instrumentState,
                new EnumValueMapper<>(InstrumentState.class));

        // Polynomial resources must be converted to Linear for registration.
        // assumeLinear works when the polynomial is at most degree 1.
        registrar.real("instrumentPowerDraw",
                assumeLinear(instrumentPowerDraw));

        registrar.real("dataRate",
                assumeLinear(dataRate));

        registrar.real("dataVolume",
                approximateAsLinear(dataVolume));

        // Clock -> Linear conversion using asLinear with a unit
        registrar.real("instrumentUptime_seconds",
                ClockResources.asLinear(instrumentUptime, Duration.SECOND));

        // Derived resources
        registrar.real("totalPower",
                assumeLinear(totalPower));

        registrar.real("batterySOC",
                approximateAsLinear(batterySOC));

        registrar.discrete("batteryLow", batteryLow,
                new BooleanValueMapper());
    }
}
