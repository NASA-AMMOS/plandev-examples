package gov.nasa.ammos.plandev.data.activities;

import gov.nasa.ammos.plandev.contrib.streamline.core.Resources;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.contrib.metadata.Unit;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.data.Data;
import gov.nasa.ammos.plandev.data.DataMissionModel;

import java.util.Optional;

/**
 * Generates data into an onboard bin over a span of time.
 *
 * <p><strong>Specify at least two of {@code rate}, {@code volume} and {@code duration};</strong>
 * the third is derived from them. Supplying all three is allowed, but if they disagree the
 * model quietly reduces one of them to the most conservative consistent value rather than
 * failing — see {@link #derivedValues()}.
 *
 * <p><strong>Blocking:</strong> this activity occupies {@code duration} of simulation time, so
 * it both produces the data and provides the activity's length.
 *
 * <p>Data arriving when the bin (or total onboard storage) is full is <em>dropped, not
 * overwritten</em>. Compare {@code desiredReceivedVolume} against {@code receivedVolume} to see
 * how much was lost.
 *
 * @see <a href="https://github.com/NASA-AMMOS/plandev-examples/blob/main/libraries/data/docs/ModelBehaviorDescription.md">Data model behavior description</a>
 */
@ActivityType("GenerateData")
@Subsystem("data")
public class GenerateData {
  /**
   * The bin to generate data in
   */
  @Export.Parameter
  public int bin = 0;

  /**
   * The rate of data generation
   */
  @Export.Parameter
  @Unit("bit/s")
  public Optional<Double> rate = Optional.of(0.0);

  /**
   * The volume of data generation
   */
  @Export.Parameter
  @Unit("bit")
  public Optional<Double> volume = Optional.of(0.0);

  /**
   * The duration of data generation
   */
  @Export.Parameter
  public Optional<Duration> duration = Optional.of(Duration.of(1, Duration.SECOND));

  /**
   * At least two of the above parameters above need to be specified
   */
  @Export.Validation("Two or three downlink goals must be specified: rate, volume, and/or duration.")
  @Export.Validation.Subject({"rate", "volume", "duration"})
  public boolean validateNonEmptyGoal() {
    return (rate.isPresent() ? 1 : 0) +
      (volume.isPresent() ? 1 : 0) +
      (duration.isPresent() ? 1 : 0)
      >= 2;
  }

  @ActivityType.EffectModel
  public void run(DataMissionModel model) {
    derivedValues();
    var binToChange = model.getData().getOnboardBin(bin);
    System.out.println("GenerateData(" + Resources.currentTime() + "): rate = " + rate.get() + ", duration = " + duration.get());
    binToChange.receive(rate.get(), duration.get());
  }

  /**
   * Computes the missing value if one of rate, volume, or duration is not specified. If all are specified,
   * checks to ensure that the values agree, otherwise, computes and replaces one of the parameters
   */
  void derivedValues() {
    if (rate.isPresent() && volume.isPresent() && duration.isEmpty()) {
      Double seconds = volume.get() / rate.get();
      duration = Optional.of(Duration.of(seconds.longValue(), Duration.SECONDS));
    } else if (rate.isPresent() && volume.isEmpty() && duration.isPresent()) {
      Double bits = rate.get() * duration.get().in(Duration.SECONDS);
      volume = Optional.of(bits);
    } else if (rate.isEmpty() && volume.isPresent() && duration.isPresent()) {
      Double bps = volume.get() / duration.get().in(Duration.SECONDS);
      rate = Optional.of(bps);
    } else if (rate.isPresent() && volume.isPresent() && duration.isPresent()) {
      Double seconds = volume.get() / rate.get();
      Double bits = rate.get() * duration.get().in(Duration.SECONDS);
      Double bps = volume.get() / duration.get().in(Duration.SECONDS);
      if (seconds < duration.get().in(Duration.SECONDS)) {
        duration = Optional.of(Duration.of(seconds.longValue(), Duration.SECONDS));
      } else if (bits < volume.get()) {
        volume = Optional.of(bits);
      } else if (bps < rate.get()) {
        rate = Optional.of(bps);
      }
    } else {
      throw new RuntimeException("Two or three downlink goals must be specified: rate, volume, and/or duration.");
    }
  }
}
