package gov.nasa.ammos.plandev.data;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.BooleanValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.merlin.protocol.types.Duration;

import java.util.List;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.*;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialEffects.*;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.delay;
import static gov.nasa.ammos.plandev.contrib.streamline.core.Reactions.wheneverDynamicsChange;
import static gov.nasa.ammos.plandev.contrib.streamline.core.monads.ResourceMonad.map;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.DiscreteResources.choose;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial.polynomial;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.*;

/**
 * A container or category representing volume and constant & linear changes in the volume of something (e.g., data).
 * A Bucket has an upper bound on volume.  A Bucket may also have child buckets, whose volumes sum to the parent's
 * volume.  Thus, children can be indirectly limited in volume.  Children are prioritized by their order in a List.
 * This ordering affects rates of change when the parent has reached its limit.  A Bucket cannot have a negative volume.
 */
public class Bucket {
  /**
   * A human-usable name associated with this {@link Bucket}
   */
  String name;
  /**
   * The actual rate of change of volume after clamping the desired rate, {@link #desiredRate}, based on the upper bound, {@link #volume_ub}
   */
  public Resource<Polynomial> actualRate = null;
  /**
   * The volume in this {@link Bucket}
   */
  public Resource<Polynomial> volume;
  /**
   * The desired net rate of change of the volume equal to {@link #desiredReceiveRate} minus {@link #desiredRemoveRate}
   */
  public Resource<Polynomial> desiredRate = null;
  /**
   * As separate resource matching {@code volume}, needed for handling circular dependencies
   */
  private Resource<Polynomial> correctedVolume;

  /**
   * {@link Bucket}s which categorize (or constitute) the volume in this {@link Bucket} in order of priority
   */
  public List<Bucket> children;

  /**
   * An intermediate computation of the volume after clamping based on the upper bound, {@link #volume_ub}, and
   * an implicit lower bound of zero for an empty {@link Bucket}
   */
  Resource<Polynomial> clampedVolume = null;
  /**
   * The upper bound on the volume, either specified by the user or computed from the parent's upper bound and
   * those of higher priority siblings
   */
  public Resource<Polynomial> volume_ub;

  /**
   * The volume actually received, given that some desired amount could not be stored due to {@link #volume_ub}
   */
  public MutableResource<Polynomial> received;
  /**
   * The volume that would have been received if there were no upper bound
   */
  private Resource<Polynomial> desiredReceived;  // The difference with received is lost volume.
  /**
   * The rate of incoming volume desired to be received/stored
   */
  public Resource<Polynomial> desiredReceiveRate;
  /**
   * The volume actually removed, given that some desired amount was not always available to remove
   */
  public MutableResource<Polynomial> removed;
  /**
   * The volume that would have been removed if the volume were always available to remove as desired
   */
  private Resource<Polynomial> desiredRemoved;  // This should be the same as removed; otherwise, it is user error.
  /**
   * The rate of volume desired to be removed/deleted from this {@link Bucket}
   */
  public Resource<Polynomial> desiredRemoveRate;
  /**
   * The rate of volume actually received, given that some desired amount could not be stored due to {@link #volume_ub}
   */
  public Resource<Polynomial> receiveRate;
  /**
   * The rate of volume actually removed/deleted, given that some desired amount may not have been available to delete
   */
  public Resource<Polynomial> removeRate;

  /**
   * Discrete signal that is {@code true} when {@link #volume} is at or below zero.
   */
  public Resource<Discrete<Boolean>> isEmpty;

  private static Resource<Polynomial> max_bound = constant(Double.MAX_VALUE);

  /**
   * Create a {@link Bucket} without an explicit upper bound on its volume
   * @param name the name of the {@link Bucket}
   * @param isChild whether or not this {@link Bucket} is a child of another
   * @param children the child {@link Bucket}s in priority order
   */
  public Bucket(String name, boolean isChild, List<Bucket> children) {
    this(name, isChild, children, max_bound);
  }

  /**
   * Create a {@link Bucket} without an explicit upper bound on its volume
   * @param name the name of the {@link Bucket}
   * @param isChild whether or not this {@link Bucket} is a child of another
   * @param children the child {@link Bucket}s in priority order
   * @param upperBound an explicit upper bound on this {@link Bucket}, implicitly imposed on any children
   */
  public Bucket(String name, boolean isChild, List<Bucket> children, Resource<Polynomial> upperBound) {
    this.name = name;
    this.desiredReceiveRate = polynomialResource(0.0);
    this.desiredRemoveRate = polynomialResource(0.0);
    this.received = polynomialResource(0.0);
    this.removed = polynomialResource(0.0);
    this.volume = polynomialResource(0.0);
    this.volume_ub = upperBound;
    this.isEmpty = lessThanOrEquals(volume, 0);

    this.correctedVolume = null;

    this.children = children;

    // All children share the parent's capacity limit (no cascading per-bin reservations).
    // Total capacity is enforced by the parent's volume = sum(children.volume); per-child rate
    // is clamped via choose() on isEmpty/isFull.
    //
    // NOTE: an earlier version derived each bin's bound from the previous bin
    // (volume_ub[i] = min(own, volume_ub[i-1] - clampedVolume[i-1])) to make higher-priority
    // bins consume parent capacity first. That made volume_ub[i] reference volume_ub[i-1] twice
    // (directly, and via clampedVolume[i-1]); since streamline derived resources aren't memoized
    // across references, evaluating the deepest bin's dynamics fanned out as O(2^binCount) and
    // hung model instantiation at high bin counts (e.g. the orbiter's 20 bins). If priority-
    // ordered capacity reservation is ever needed, reintroduce the cascade with cached
    // intermediates (Resources.cache) to keep evaluation O(n).
    for (int i = 0; i < this.children.size(); ++i) {  // TODO -- what if a child has children?
      Bucket child = this.children.get(i);

      child.volume_ub = child.volume_ub.equals(max_bound) ? volume_ub : min(child.volume_ub, volume_ub);

      child.clampedVolume = clamp(child.volume, constant(0), child.volume_ub);

      child.desiredRate = subtract(child.desiredReceiveRate, child.desiredRemoveRate);

      // Clamp rate so an empty bin can only receive and a full bin can only remove.
      var childIsEmpty = lessThanOrEquals(child.volume, 0);
      var childIsFull = greaterThanOrEquals(child.volume, child.volume_ub);
      child.actualRate = choose(childIsEmpty,
          max(child.desiredRate, constant(0)),
          choose(childIsFull,
              min(child.desiredRate, constant(0)),
              child.desiredRate));

      child.correctedVolume = map(child.clampedVolume, child.actualRate, (v, r) -> r.integral(v.extract()));
      forward(eraseExpiry(child.correctedVolume), (MutableResource<Polynomial>) child.volume);

      child.finishInit();
    }

    if (!this.children.isEmpty()) {
      this.volume = sum(children.stream().map(b -> b.volume));
      this.isEmpty = lessThanOrEquals(this.volume, 0);
      actualRate = sum(children.stream().map(b -> b.actualRate));
      desiredReceiveRate = sum(children.stream().map(b -> b.desiredReceiveRate));
      desiredRemoveRate = sum(children.stream().map(b -> b.desiredRemoveRate));
    }
    if (!isChild) {
      finishInit();
    }
  }

  /**
   * A part of the initialization done at different times for the parent and children since they are codependent
   */
  public void finishInit() {
    // make sure desiredRate is defined
    if (desiredRate == null) desiredRate = subtract(desiredReceiveRate, desiredRemoveRate);

    // keep track of how much would be received and how much would be deleted if there were no bounds
    desiredReceived = map(desiredReceiveRate, r -> r.integral(0.0));
    desiredRemoved = map(desiredRemoveRate, r -> r.integral(0.0));

    // make sure actualRate is defined
    if (actualRate == null) actualRate = desiredRate;

    // define actual receive and remove rates
    receiveRate = subtract(desiredReceiveRate, max(subtract(desiredRate, actualRate), constant(0.0)));
    removeRate = subtract(desiredRemoveRate, max(subtract(actualRate, desiredRate), constant(0.0)));

    // define actual total volume received and actual total volume removed
    wheneverDynamicsChange(receiveRate, r -> MutableResource.set(received, polynomial(currentValue(received), data(r).extract())));
    wheneverDynamicsChange(removeRate, r -> MutableResource.set(removed, polynomial(currentValue(removed), data(r).extract())));
  }

  /**
   * Specify what resource data to collect for display
   * @param registrar
   */
  public void registerStates(Registrar registrar) {
    registrar.real(name + ".desiredReceiveRate", assumeLinear(desiredReceiveRate), "bit/s");
    registrar.real(name + ".desiredRemoveRate", assumeLinear(desiredRemoveRate), "bit/s");
    registrar.real(name + ".desiredRate", assumeLinear(desiredRate), "bit/s");
    registrar.real(name + ".actualRate", assumeLinear(actualRate), "bit/s");
    registrar.real(name + ".desiredReceivedVolume", assumeLinear(desiredReceived), "bit");
    registrar.real(name + ".desiredRemovedVolume", assumeLinear(desiredRemoved), "bit");
    registrar.real(name + ".receivedVolume", assumeLinear(received), "bit");
    registrar.real(name + ".removedVolume", assumeLinear(removed), "bit");
    registrar.real(name + ".volume", assumeLinear(volume), "bit");
    registrar.discrete(name + ".isEmpty", isEmpty, new BooleanValueMapper());
    if (clampedVolume != null) registrar.real(name + ".clampedVolume", assumeLinear(clampedVolume), "bit");
    if (correctedVolume != null) registrar.real(name + ".correctedVolume", assumeLinear(correctedVolume), "bit");
    if (!volume_ub.equals(max_bound)) {
      registrar.real(name + ".maxVolume", assumeLinear(volume_ub), "bit");
    }
    for (Bucket child : this.children) {
      child.registerStates(registrar);
    }
  }


  /**
   * Receive volume at the given rate for the given duration: raises the desired receive rate by
   * {@code rate}, waits {@code duration}, then lowers it back down.
   *
   * <p><strong>This call blocks, advancing simulation time by {@code duration}.</strong> It both
   * produces the data and consumes the time, so callers should not add their own {@code delay} for
   * the same window (doing so doubles the activity's length). To raise the rate without waiting,
   * use {@link #addReceiveRate(double)} instead.
   *
   * @param rate desired rate of volume to receive (volume units per second)
   * @param duration the duration over which the volume is received; simulation time advances by this amount
   */
  public void receive(double rate, Duration duration) {
    if (duration.isEqualTo(Duration.ZERO)) return; // TODO -- warning?
    if (rate == 0) return;
    if (rate > 0) {
      restore((MutableResource<Polynomial>) desiredReceiveRate, rate);
      delay(duration);
      consume((MutableResource<Polynomial>) desiredReceiveRate, rate);
    } else {
      // TODO -- put a warning here?
      remove(-rate, duration);
    }
  }

  /**
   * Remove/delete volume at the given rate for the given duration: raises the desired remove rate by
   * {@code rate}, waits {@code duration}, then lowers it back down.
   *
   * <p><strong>This call blocks, advancing simulation time by {@code duration}.</strong> To raise the
   * remove rate without waiting, use {@link #addRemoveRate(double)} instead.
   *
   * @param rate desired rate of volume to remove (volume units per second)
   * @param duration the duration over which the volume is removed; simulation time advances by this amount
   */
  public void remove(double rate, Duration duration) {
    if (duration.isEqualTo(Duration.ZERO)) return; // TODO -- warning?
    if (rate == 0) return;
    if (rate > 0) {
      restore((MutableResource<Polynomial>) desiredRemoveRate, rate);
      delay(duration);
      consume((MutableResource<Polynomial>) desiredRemoveRate, rate);
    } else {
      // TODO -- put a warning here?
      receive(-rate, duration);
    }
  }

  /**
   * Add an incoming rate of volume to the existing {@link #desiredReceiveRate}.
   *
   * <p>Non-blocking: sets the rate and returns immediately. The rate persists until something
   * changes it again, so the caller is responsible for later lowering it (e.g. via
   * {@link #addReceiveRate(double)} with a negative rate). Contrast with the blocking
   * {@link #receive(double, Duration)}, which turns the rate off for you after a duration.
   *
   * @param rate the rate of volume to add to the desired receive rate (volume units per second)
   */
  public void addReceiveRate(double rate) {
    if (rate == 0) return;
    if (rate > 0) {
      restore((MutableResource<Polynomial>) desiredReceiveRate, rate);
    } else {
      // TODO -- put a warning here?
      restore((MutableResource<Polynomial>) desiredRemoveRate, -rate);
    }
  }
  /**
   * Add a rate to remove/delete volume to the existing {@link #desiredRemoveRate}.
   *
   * <p>Non-blocking: sets the rate and returns immediately. The rate persists until something
   * changes it again. Contrast with the blocking {@link #remove(double, Duration)}, which turns the
   * rate off for you after a duration.
   *
   * @param rate the rate of volume to add to the desired remove rate (volume units per second)
   */
  public void addRemoveRate(double rate) {
    if (rate == 0) return;
    if (rate > 0) {
      restore((MutableResource<Polynomial>) desiredRemoveRate, rate);
    } else {
      // TODO -- put a warning here?
      restore((MutableResource<Polynomial>) desiredReceiveRate, -rate);
    }
  }

  /**
   * Receive a fixed {@code amount} of volume, delivered over a 1-second window.
   *
   * <p><strong>This is not instantaneous: it blocks for 1 second of simulation time.</strong> The
   * amount is first clamped to the current headroom ({@code volume_ub - volume}), then passed as the
   * <em>rate</em> to {@link #receive(double, Duration)} with a 1-second duration. Because delivered
   * volume is {@code rate * duration}, the stored volume equals {@code amount} only because the
   * window is exactly one second -- during that second the receive rate spikes to {@code amount} per
   * second, which is visible to rate-derived resources (e.g. downlink allocation).
   *
   * @param amount the volume to receive, clamped to available headroom
   */
  public void receive(double amount) {
    if (amount == 0) return;
    if (amount < 0) {
      remove(-amount);
    } else {
      double actualAmount = Math.min(amount, currentValue(volume_ub) - currentValue(volume));
      var duration = Duration.of(1, Duration.SECOND);
      receive(actualAmount, duration);
    }
  }

  /**
   * Remove a fixed {@code amount} of volume, taken over a 1-second window.
   *
   * <p><strong>This is not instantaneous: it blocks for 1 second of simulation time.</strong> The
   * amount is first clamped to the currently available volume, then passed as the <em>rate</em> to
   * {@link #remove(double, Duration)} with a 1-second duration. The removed volume equals
   * {@code amount} only because the window is exactly one second; during that second the remove rate
   * spikes to {@code amount} per second. See {@link #receive(double)} for the same caveats.
   *
   * @param amount the volume to remove, clamped to the available volume
   */
  public void remove(double amount) {
    if (amount == 0) return;
    if (amount < 0) {
      receive(-amount);
    } else {
      double actualAmount = Math.min(amount, currentValue(volume));
      var duration = Duration.of(1, Duration.SECOND);
      remove(actualAmount, duration);
    }
  }

}
