package gov.nasa.ammos.plandev.data.activities;

import gov.nasa.ammos.plandev.contrib.streamline.core.Resources;
import gov.nasa.ammos.plandev.merlin.framework.ModelActions;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.contrib.metadata.Unit;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.data.Data;
import gov.nasa.ammos.plandev.data.DataMissionModel;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.*;

/**
 * Moves data from one onboard bin to another, changing the priority it will downlink at.
 *
 * <p>The amount moved is clamped both by what {@code bin} holds and by the headroom left in
 * {@code newBin}, so an oversized request moves what it can instead of failing.
 *
 * <p>The removal and the receipt are spawned as parallel tasks, so this activity itself
 * completes immediately while the transfer settles over the following second.
 *
 * @see <a href="https://github.com/NASA-AMMOS/plandev-examples/blob/main/libraries/data/docs/ModelBehaviorDescription.md">Data model behavior description</a>
 */
@ActivityType("ReprioritizeData")
@Subsystem("data")
public class ReprioritizeData {
  /**
   * The volume to reprioritize
   */
  @Export.Parameter
  @Unit("bit")
  public double volume; // bits

  /**
   * The bin whose data is to be reprioritized; i.e. the old priority
   */
  @Export.Parameter
  public int bin = 0;

  /**
   * The bin receiving the reprioritized data; i.e., the new priority
   */
  @Export.Parameter
  public int newBin = 1;

  @ActivityType.EffectModel
  public void run(DataMissionModel model) {
    Data data = model.getData();
    var fromBin = data.getOnboardBin(bin);
    var toBin = data.getOnboardBin(newBin);

    double currentVolume = currentValue(fromBin.volume);
    double receivableVolume = currentValue(toBin.volume_ub) - currentValue(toBin.volume);
    double actualVolumeReprioritized = Math.max(0.0, Math.min(volume, Math.min(currentVolume, receivableVolume)));

    System.out.println("ReprioritizeData(" + Resources.currentTime() + "): actualVolumeReprioritized = " + actualVolumeReprioritized);

    ModelActions.spawn(() -> fromBin.remove(actualVolumeReprioritized));
    ModelActions.spawn(() -> toBin.receive(actualVolumeReprioritized));
  }
}
