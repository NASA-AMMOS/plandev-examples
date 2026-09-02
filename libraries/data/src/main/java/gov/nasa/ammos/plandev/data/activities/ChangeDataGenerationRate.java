package gov.nasa.ammos.plandev.data.activities;

import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resources;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.contrib.metadata.Unit;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.data.Data;
import gov.nasa.ammos.plandev.data.DataMissionModel;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.set;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial.polynomial;

/**
 * Sets a bin's data flow to a constant rate, replacing whatever was flowing before.
 *
 * <p>A positive {@code rate} generates data into the bin; a <b>negative</b> rate removes it.
 * Either way both the receive and remove rates are overwritten, so any flow an earlier
 * activity started is discarded rather than added to.
 *
 * <p><strong>A rate of 0 does nothing.</strong> This activity returns immediately without
 * touching the bin, so it cannot be used to stop an ongoing flow.
 *
 * <p>Non-blocking: the rate is set and persists until something changes it again.
 *
 * @see <a href="https://github.com/NASA-AMMOS/plandev-examples/blob/main/libraries/data/docs/ModelBehaviorDescription.md">Data model behavior description</a>
 */
@ActivityType("ChangeDataGenerationRate")
@Subsystem("data")
public class ChangeDataGenerationRate {

  /**
   * The bin whose rate is changed
   */
  @Export.Parameter
  public int bin = 0;

  /**
   * The rate to instantly change
   */
  @Export.Parameter
  @Unit("bit/s")
  public double rate = 0.0;

  /**
   * Eliminates incoming and outgoing flows, only the new data rate is kept
   */
  @ActivityType.EffectModel
  public void run(DataMissionModel model) {
    Data data = model.getData();
    if (rate == 0.0) return;
    var binToChange = data.getOnboardBin(bin);

    if (rate > 0) {
      set((MutableResource<Polynomial>)binToChange.desiredReceiveRate, polynomial(rate));
      set((MutableResource<Polynomial>)binToChange.desiredRemoveRate, polynomial(0));
    } else {
      set((MutableResource<Polynomial>) binToChange.desiredReceiveRate, polynomial(0));
      set((MutableResource<Polynomial>) binToChange.desiredRemoveRate, polynomial(-rate));
    }
  }

}
