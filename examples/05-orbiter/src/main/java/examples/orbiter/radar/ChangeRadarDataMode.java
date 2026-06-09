package examples.orbiter.radar;

import gov.nasa.jpl.aerie.contrib.streamline.modeling.discrete.DiscreteEffects;
import gov.nasa.jpl.aerie.merlin.framework.annotations.ActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Subsystem;
import gov.nasa.jpl.aerie.merlin.framework.annotations.Export;
import examples.orbiter.Mission;
import gov.nasa.jpl.aerie.data.activities.ChangeDataGenerationRate;

import static examples.orbiter.generated.ActivityActions.call;

@ActivityType("ChangeRadarDataMode")
@Subsystem("radar")
public class ChangeRadarDataMode {

  @Export.Parameter
  public RadarDataCollectionMode mode = RadarDataCollectionMode.LOW_RES;

  public ChangeRadarDataMode() {}

  public ChangeRadarDataMode(RadarDataCollectionMode radarDataCollectionMode) {
    this.mode = radarDataCollectionMode;
  }

  @ActivityType.EffectModel
  public void run(Mission model) {
    // Start generating data into a random onboard bin at the mode's rate.
    double newRate = mode.getDataRate();
    int bin = model.getRandom().nextInt(model.data.onboardBuckets.size());
    var change = new ChangeDataGenerationRate();
    change.bin = bin;
    change.rate = newRate * 1e6;
    call(model, change);

    DiscreteEffects.set(model.radarModel.RadarDataMode, mode);
  }
}
