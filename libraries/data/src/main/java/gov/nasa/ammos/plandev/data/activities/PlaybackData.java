package gov.nasa.ammos.plandev.data.activities;

import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.merlin.framework.Condition;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Export;
import gov.nasa.ammos.plandev.contrib.metadata.Unit;
import gov.nasa.ammos.plandev.merlin.framework.annotations.Subsystem;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;
import gov.nasa.ammos.plandev.merlin.protocol.types.RealDynamics;
import gov.nasa.ammos.plandev.data.DataMissionModel;

import java.util.Optional;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.*;
import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.set;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialEffects.restore;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.waitUntil;

/**
 * Downlinks stored data to the ground, draining onboard bins in priority order.
 *
 * <p>Give it a {@code volume} goal, a {@code duration} goal, or both; with neither it downlinks
 * until something else stops it. The requested volume <strong>may not be achieved</strong> if
 * the data simply is not there.
 *
 * <p><strong>Blocking:</strong> waits until the goal is met before completing.
 *
 * <p><strong>Only one PlaybackData may run at a time</strong> — a second overlapping one throws.
 * Bins are drained strictly by priority: the highest-priority non-empty bin consumes the entire
 * available rate, rather than sharing it.
 *
 * @see <a href="https://github.com/NASA-AMMOS/plandev-examples/blob/main/libraries/data/docs/ModelBehaviorDescription.md">Data model behavior description</a>
 */
@ActivityType("PlaybackData")
@Subsystem("data")
public class PlaybackData {
  /**
   * Desired volume of data to downlink.  May not be achieved if data is not present.
   */
  @Export.Parameter
  @Unit("bit")
  public Optional<Double> volume = Optional.empty(); // bits
  @Export.Parameter
  public Optional<Duration> duration = Optional.empty();

  public PlaybackData() {}

  public PlaybackData(Duration duration) {
    this.duration = Optional.of(duration);
  }

  @ActivityType.EffectModel
  public void run(DataMissionModel model) {
    var ground = model.getData().ground;

    if (volume.isPresent() && volume.get() == 0.0) return;
    if (duration.isPresent() && duration.get().isEqualTo(Duration.ZERO)) return;

    if (currentValue(ground.receiveRate) > 0) {
      throw new RuntimeException("Only one PlaybackData activity at a time!");
    }

    final var targetGroundReceivedValue = volume.isEmpty() ? Double.MAX_VALUE : currentValue(ground.received) + volume.get();
    if (volume.isPresent()) {
      restore(model.getData().volumeRequestedToDownlink, volume.get());
    }
    if (duration.isPresent()) {
      set(model.getData().durationRequestedToDownlink, Polynomial.polynomial(duration.get().in(Duration.SECONDS), -1));
    }
    waitUntil(Condition.and(
      volume.isEmpty() ? Condition.TRUE : isBetween(ground.received, targetGroundReceivedValue, targetGroundReceivedValue * 2),
      duration.isEmpty() ? Condition.TRUE : isBetween(model.getData().durationRequestedToDownlink, -2.0, 0)));
    if (volume.isPresent()) {
      set(model.getData().volumeRequestedToDownlink, Polynomial.polynomial(0, 0));
    }
    if (duration.isPresent()) {
      set(model.getData().durationRequestedToDownlink, Polynomial.polynomial(0, 0));
    }
  }

  private Condition isBetween(Resource<Polynomial> r, final double lower, final double upper) {
    return (positive, atEarliest, atLatest) -> {
      final var p = r.getDynamics().getOrThrow().data();

      if (p.coefficients().length > 2) throw new RuntimeException("isBetween condition only for linear polynomials: resource = " + r);
      RealDynamics dynamics = RealDynamics.linear(p.getCoefficient(0), p.getCoefficient(1));

      return (positive)
        ? dynamics.whenBetween(lower, upper, atEarliest, atLatest)
        : dynamics.whenNotBetween(lower, upper, atEarliest, atLatest);
    };
  }

}
