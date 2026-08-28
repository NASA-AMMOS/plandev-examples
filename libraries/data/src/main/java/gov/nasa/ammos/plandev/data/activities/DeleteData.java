package gov.nasa.ammos.plandev.data.activities;

import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.contrib.metadata.Unit;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.data.Data;
import gov.nasa.ammos.plandev.data.DataMissionModel;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.*;
import static java.lang.Math.max;

@ActivityType("DeleteData")
@Subsystem("data")
public class DeleteData {
  /**
   * The maximum volume to delete depending on {@link #limitToSentData} and the volume of the bin
   */
  @Export.Parameter
  @Unit("bit")
  public double volume; // bits

  /**
   * Whether to limit the amount deleted to that which has been downlinked
   */
  @Export.Parameter
  public boolean limitToSentData = true;

  /**
   * The bin whose data is to be deleted
   */
  @Export.Parameter
  public int bin = 0;

  public DeleteData() {}

  public DeleteData(double volume, boolean limitToSentData, int bin) {
    this.volume = volume;
    this.limitToSentData = limitToSentData;
    this.bin = bin;
  }

  @ActivityType.EffectModel
  public void run(DataMissionModel model) {
    Data data = model.getData();
    var binToChange = data.getOnboardBin(bin);
    var groundBin = data.getGroundBin(bin);

    double currentVolume = currentValue(binToChange.volume);
    double MAX = Double.MAX_VALUE;
    double remainingNotYetDownlinked = groundBin == null ? MAX :
      Math.min(currentVolume,  currentValue(binToChange.received) - currentValue(groundBin.received));
    double remainingAlreadyDownlinked = max(0.0, currentVolume - remainingNotYetDownlinked);
    double actualVolumeDeleted =
      Math.min(volume, Math.min(currentVolume, limitToSentData ? remainingAlreadyDownlinked : MAX));

    binToChange.remove(actualVolumeDeleted);
  }

}
