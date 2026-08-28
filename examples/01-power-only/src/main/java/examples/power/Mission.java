package examples.power;


import examples.power.models.pel.PELModel;
import gov.nasa.ammos.plandev.merlin.framework.ModelActions;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;

import gov.nasa.ammos.plandev.power.BatteryModel;
import gov.nasa.ammos.plandev.power.GenericSolarArray;
import gov.nasa.ammos.plandev.power.PowerSource;
import gov.nasa.ammos.plandev.power.RtgPowerProduction;

import java.time.Instant;

public class Mission {

    public final PELModel pel;
    public DistAndAngleCalculator calculator;
    public PowerSource powerSource;
    public final BatteryModel cbebattery;
    public final BatteryModel mevbattery;

    public final Registrar errorRegistrar;

    public Mission(final gov.nasa.ammos.plandev.merlin.framework.Registrar registrar, final Instant planStart, final Configuration config) {
        this.calculator = new DistAndAngleCalculator();
        ModelActions.spawn(calculator::run);

        // Initialize Power States and Loads
        this.pel = new PELModel();
        // Initialize Power Source
        this.powerSource = new GenericSolarArray(config.powerConfig().powerSourceConfig(), calculator.distance, calculator.angle, calculator.eclipseFactor);
        // this.powerSource = new RtgPowerProduction(config.powerConfig().powerSourceConfig(), planStart);
        this.cbebattery = new BatteryModel("cbebattery", config.powerConfig().batteryConfig(), pel.cbeTotalLoad, powerSource.getPowerProduction());
        this.mevbattery = new BatteryModel("mevbattery", config.powerConfig().batteryConfig(), pel.mevTotalLoad, powerSource.getPowerProduction());

        this.errorRegistrar = new Registrar(registrar, Registrar.ErrorBehavior.Log);

        pel.registerStates(this.errorRegistrar);
        powerSource.registerStates(this.errorRegistrar);
        cbebattery.registerStates(this.errorRegistrar);
        mevbattery.registerStates(this.errorRegistrar);

    }
}
