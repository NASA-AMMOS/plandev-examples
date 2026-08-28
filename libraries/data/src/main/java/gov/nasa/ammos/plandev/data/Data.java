package gov.nasa.ammos.plandev.data;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.IntegerValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.Polynomial;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources;

import java.util.*;

import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.set;
import static gov.nasa.ammos.plandev.contrib.streamline.core.Reactions.wheneverDynamicsChange;
import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.*;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.polynomial.PolynomialResources.*;
import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.spawn;


/**
 * The Data class is the main interface for using the data model.  A mission model can construct a Data object
 * containing data volume bins and the parent storage with the storage limit.  See the
 * [Model Behavior Description]({@docRoot}/docs/ModelBehaviorDesc.md) for a description of how {@link Bucket}
 * (bin) resources are updated.  That functionality is implemented by this class.  This class also automatically
 * registers resources for the bins.
 */
public class Data {
  /**
   * The onboard storage device of the spacecraft, a parent of the bins, {@link #onboardBuckets}.
   */
  public Bucket onboard;

  /**
   * The parent container for ground storage, representing the data that has been played back/downlinked overall
   * and for each bin through its children, {@link #groundBuckets}.
   */
  public Bucket ground;

  /**
   * A playbackdatarate resource provided by the user; if unspecified in the Data constructor,
   * a default value will be used.
   */
  public Resource<Polynomial> dataRate;  // bps

  /**
   * When a {@link gov.nasa.ammos.plandev.data.activities.PlaybackData} activity has a volume goal, this resource tracks
   * how much volume is left before the goal has been met.
   */
  public MutableResource<Polynomial> volumeRequestedToDownlink = polynomialResource(0.0);

  /**
   * When a {@link gov.nasa.ammos.plandev.data.activities.PlaybackData} activity has a duration goal, this resource tracks
   * how much time is left before the goal has been met.
   */
  public MutableResource<Polynomial> durationRequestedToDownlink = polynomialResource(0.0);

  /**
   * The storage bins/categories, which are children of {@link #onboard}.  Lower indices in the array are higher priority
   */
  public ArrayList<Bucket> onboardBuckets = new ArrayList<>();

  /**
   * The ground storage bins corresponding to the onboard bins, tracking how much data has been downlinked for each bin
   */
  public ArrayList<Bucket> groundBuckets = new ArrayList<>();

  /**
   * Get the onboard bin by index, starting from 0
   */
  public Bucket getOnboardBin(int bin) {
    return onboardBuckets.get(bin);
  }

  /**
   * Get the ground bin by index, starting from 0
   */
  public Bucket getGroundBin(int bin) {
    return groundBuckets.get(bin);
  }

  /**
   * Construct a Data object, instantiating a specified number of onboard and corresponding ground bins and
   * using an externally defined data rate and storage limit (max volume) for the total onboard storage.
   * @param dataRate the data rate resource, specified external to the data model, such as by a telecom subsystem model
   * @param numBuckets the number of prioritized bins/categories of data
   * @param maxVolume the onboard storage limit as a resource that is defined set external to the data model
   */
  public Data(Optional<Resource<Polynomial>> dataRate, int numBuckets, Resource<Polynomial> maxVolume) {

    for (int i = 0; i < numBuckets; ++i) {
      Bucket scBin = new Bucket("scBin" + i, true, Collections.emptyList());
      onboardBuckets.add(scBin);
      Bucket gBin = new Bucket("gndBin" + i, true, Collections.emptyList());
      groundBuckets.add(gBin);
    }

    onboard = new Bucket("onboard", false, onboardBuckets, maxVolume); // 10Gb

    ground = new Bucket("ground", false, groundBuckets);

    if (dataRate.isPresent()) {
      this.dataRate = dataRate.get();
    } else {
      this.dataRate = polynomialResource(1.0);
    }

    // Allocate the available downlink rate to bins in priority order, in a single
    // pass on each input change.
    Runnable computeDownlinkRates = () -> {
      boolean done = currentValue(volumeRequestedToDownlink) <= 0 &&
                     currentValue(durationRequestedToDownlink) <= 0;
      double rateLeft = done ? 0.0 : currentValue(this.dataRate);

      for (int i = 0; i < onboard.children.size(); ++i) {
        Bucket scBin = onboard.children.get(i);
        Bucket gBin = ground.children.get(i);

        double availableVolume = currentValue(scBin.received) - currentValue(gBin.received);
        boolean binIsEmpty = currentValue(scBin.volume) <= 0 || availableVolume <= 0 || done;

        double binRate;
        if (binIsEmpty) {
          binRate = Math.max(0, Math.min(currentValue(scBin.actualRate), rateLeft));
        } else {
          binRate = rateLeft;
        }

        set((MutableResource<Polynomial>) gBin.desiredReceiveRate, Polynomial.polynomial(binRate));
        rateLeft -= binRate;
      }
    };

    wheneverDynamicsChange(this.dataRate, r -> computeDownlinkRates.run());
    wheneverDynamicsChange(volumeRequestedToDownlink, r -> computeDownlinkRates.run());
    wheneverDynamicsChange(durationRequestedToDownlink, r -> computeDownlinkRates.run());
    for (int i = 0; i < onboard.children.size(); ++i) {
      Bucket scBin = onboard.children.get(i);
      Bucket gBin = ground.children.get(i);
      wheneverDynamicsChange(scBin.volume, r -> computeDownlinkRates.run());
      wheneverDynamicsChange(scBin.received, r -> computeDownlinkRates.run());
      wheneverDynamicsChange(scBin.actualRate, r -> computeDownlinkRates.run());
      wheneverDynamicsChange(gBin.received, r -> computeDownlinkRates.run());
    }

    wheneverDynamicsChange(ground.actualRate, r -> {
      if (currentValue(volumeRequestedToDownlink) > 0)
        set(volumeRequestedToDownlink, Polynomial.polynomial(currentValue(volumeRequestedToDownlink), -data(r).extract()));
    });

    spawn(computeDownlinkRates);
  }

  /**
   * Register bin and other resources with PlanDev to record them in the simulation results and see them in the UI.
   * @param registrar the built-in Registrar object used to register resources
   */
  public void registerStates(Registrar registrar) {
    onboard.registerStates(registrar);
    ground.registerStates(registrar);
    registrar.real("volumeRequestedToDownlink", assumeLinear(volumeRequestedToDownlink), "bit");
    registrar.real("durationRequestedToDownlink", assumeLinear(durationRequestedToDownlink), "s");
    registrar.real("playbackDataRate", assumeLinear(dataRate), "bit/s");
  }

  // ---------------------------------------------------------------------------------------------
  // Optional downlink-priority telemetry.
  //
  // These register *derived* resources that expose the prioritized-downlink behaviour for the UI;
  // they do not change simulation behaviour. registerStates() does NOT call them by default — a
  // mission model opts in via registerDownlinkTelemetry(...) (or the individual methods below).
  // They double as a compact worked example of derived resources (reduce over a list of resources).
  // ---------------------------------------------------------------------------------------------

  /**
   * Register all optional downlink-priority telemetry: {@code onboard.highestDownlinkPriority},
   * {@code ground.currentDownlinkPriority}, and grouped onboard bin volumes
   * ({@code onboard.binGroup_SS_EE.volume}, summed in blocks of {@code groupSize}).
   *
   * @param groupSize adjacent bins to sum per grouped-volume resource (e.g. 5). Useful when there
   *                  are many bins and one timeline line per bin would be cluttered.
   */
  public void registerDownlinkTelemetry(Registrar registrar, int groupSize) {
    registerHighestDownlinkPriority(registrar);
    registerCurrentDownlinkPriority(registrar);
    registerGroupedBinVolumes(registrar, groupSize);
  }

  /**
   * Register {@code onboard.highestDownlinkPriority}: the index of the highest-priority
   * (lowest-index) non-empty onboard bin — the bin that will downlink next, or -1 if all empty.
   */
  public void registerHighestDownlinkPriority(Registrar registrar) {
    List<Resource<Discrete<Map.Entry<Boolean, Integer>>>> indexed = new ArrayList<>();
    // Build from lowest priority (highest index) to highest (index 0) so that, folding left, a
    // lower-index (higher-priority) non-empty bin overrides a higher-index one.
    for (int i = onboard.children.size() - 1; i >= 0; --i) {
      final int idx = i;
      indexed.add(DiscreteResourceMonad.map(onboard.children.get(i).isEmpty, empty -> Map.entry(empty, idx)));
    }
    Resource<Discrete<Map.Entry<Boolean, Integer>>> highest = DiscreteResourceMonad.reduce(
        indexed, Map.entry(false, -1),
        (first, second) -> !second.getKey() ? second : first);
    registrar.discrete(onboard.name + ".highestDownlinkPriority",
        DiscreteResourceMonad.map(highest, Map.Entry::getValue), new IntegerValueMapper());
  }

  /**
   * Register {@code ground.currentDownlinkPriority}: the index of the bin currently being
   * downlinked (its ground bin has a positive receive rate), or -1 if none.
   */
  public void registerCurrentDownlinkPriority(Registrar registrar) {
    List<Resource<Discrete<Map.Entry<Boolean, Integer>>>> indexed = new ArrayList<>();
    for (int i = ground.children.size() - 1; i >= 0; --i) {
      final int idx = i;
      Resource<Discrete<Boolean>> isDownlinking = PolynomialResources.greaterThan(ground.children.get(i).actualRate, 0);
      indexed.add(DiscreteResourceMonad.map(isDownlinking, dl -> Map.entry(dl, idx)));
    }
    Resource<Discrete<Map.Entry<Boolean, Integer>>> current = DiscreteResourceMonad.reduce(
        indexed, Map.entry(false, -1),
        (first, second) -> second.getKey() ? second : first);
    registrar.discrete(ground.name + ".currentDownlinkPriority",
        DiscreteResourceMonad.map(current, Map.Entry::getValue), new IntegerValueMapper());
  }

  /**
   * Register grouped onboard bin-volume resources for a compact UI view: bins are summed in blocks
   * of {@code groupSize} and registered as {@code onboard.binGroup_SS_EE.volume}.
   */
  public void registerGroupedBinVolumes(Registrar registrar, int groupSize) {
    int numBins = onboardBuckets.size();
    int numGroups = (numBins + groupSize - 1) / groupSize; // ceiling division
    for (int g = 0; g < numGroups; g++) {
      int startBin = g * groupSize;
      int endBin = Math.min(startBin + groupSize, numBins);
      List<Resource<Polynomial>> groupVolumes = new ArrayList<>();
      for (int i = startBin; i < endBin; i++) {
        groupVolumes.add(onboardBuckets.get(i).volume);
      }
      Resource<Polynomial> groupTotal = groupVolumes.stream()
          .reduce(PolynomialResources::add)
          .orElse(polynomialResource(0.0));
      String groupName = String.format("%s.binGroup_%02d_%02d.volume", onboard.name, startBin, endBin - 1);
      registrar.real(groupName, assumeLinear(groupTotal), "bit");
    }
  }

}
