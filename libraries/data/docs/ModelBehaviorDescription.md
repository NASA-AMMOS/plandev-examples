# Data Model — Behavior Description

How [`Bucket`](../src/main/java/gov/nasa/ammos/plandev/data/Bucket.java) and
[`Data`](../src/main/java/gov/nasa/ammos/plandev/data/Data.java) actually behave: the rate
clamping rules, what happens when storage fills, and how downlink is allocated across bins.

This document is derived from the implementation in this repository. Where the behavior is
surprising, the reason is called out rather than smoothed over.

## 1. The Bucket abstraction

A `Bucket` is a container with a volume, an upper bound, and optionally a list of **child**
buckets. It is used for both onboard storage and the ground record of what has been downlinked.

- A bucket's volume **can never go negative**, and never exceeds its upper bound.
- A parent's `volume` is the **sum of its children's volumes**. The parent is not a separate
  store — it is a view over its children.
- Children are held in a `List` **in priority order**: index 0 is the highest priority.

`Data` builds two trees, both `numBuckets` wide:

| Tree | Parent | Children | Meaning |
|---|---|---|---|
| Onboard | `onboard` | `scBin0`, `scBin1`, … | Data currently stored on the spacecraft |
| Ground | `ground` | `gndBin0`, `gndBin1`, … | Data that has been downlinked |

Only `onboard` is given a maximum volume; `ground` is unbounded.

## 2. Desired vs. actual rates

Every bucket tracks two *desired* rates that activities manipulate, and derives an *actual*
rate from them:

```
desiredRate = desiredReceiveRate − desiredRemoveRate
```

`actualRate` is `desiredRate` clamped by the bin's current state:

```
if volume ≤ 0        →  actualRate = max(desiredRate, 0)      // an empty bin can only fill
else if volume ≥ ub  →  actualRate = min(desiredRate, 0)      // a full bin can only drain
else                 →  actualRate = desiredRate
```

Volume is then the integral of `actualRate`, clamped to `[0, volume_ub]`.

**The gap between desired and actual is the lost data.** The model keeps both:

- `receivedVolume` / `removedVolume` — what actually happened.
- `desiredReceivedVolume` / `desiredRemovedVolume` — what would have happened with no bounds.

`desiredReceivedVolume − receivedVolume` is therefore **the volume dropped because storage was
full**. Nothing is overwritten: once a bin is at its bound, incoming data is simply not stored.
If you need to know whether a plan lost science data, compare those two resources — a full
`onboard.volume` alone does not tell you *how much* was lost.

A discrepancy between `desiredRemovedVolume` and `removedVolume`, by contrast, indicates
**user error**: it means something tried to delete data that was not there.

## 3. Capacity sharing between bins

All children share the parent's capacity limit. There is **no per-bin reservation**: a child's
effective upper bound is `min(its own bound, the parent's bound)`, and total capacity is
enforced only through the parent's `volume = sum(children)` identity plus each child's own
empty/full rate clamp.

This means a low-priority bin can consume capacity that a high-priority bin later wants.
Priority governs **downlink order**, not storage reservation.

> **Why it works this way.** An earlier version derived each bin's bound from the previous one
> (`volume_ub[i] = min(own, volume_ub[i-1] − clampedVolume[i-1])`) so higher-priority bins
> consumed parent capacity first. That made `volume_ub[i]` reference `volume_ub[i-1]` twice —
> directly and via `clampedVolume[i-1]` — and because streamline's derived resources are not
> memoized across references, evaluating the deepest bin fanned out as **O(2^binCount)**. It hung
> model instantiation at realistic bin counts (the orbiter's 20 bins). Reintroducing
> priority-ordered reservation requires caching the intermediates (`Resources.cache`) to keep
> evaluation linear.

## 4. Downlink allocation

Downlink is the ground tree receiving what the onboard tree gives up. The allocation runs as a
**single pass in priority order** each time any input changes:

```
rateLeft = (a downlink is in progress) ? playbackDataRate : 0

for each bin i, in priority order (0 first):
    availableVolume = scBin[i].receivedVolume − gndBin[i].receivedVolume
    if scBin[i].volume ≤ 0 or availableVolume ≤ 0 or no downlink in progress:
        binRate = clamp(scBin[i].actualRate, 0, rateLeft)   // only pass through live inflow
    else:
        binRate = rateLeft                                  // take everything still available
    gndBin[i].desiredReceiveRate = binRate
    rateLeft −= binRate
```

Three consequences worth knowing:

1. **The highest-priority non-empty bin consumes the entire remaining downlink rate.** Lower
   bins get whatever is left, which is normally nothing. Downlink is strictly prioritized, not
   shared.
2. **"Available" means not yet downlinked**, computed as onboard `receivedVolume` minus ground
   `receivedVolume` — cumulative totals, not current volume. Data deleted from a bin before it
   was downlinked is simply never downlinked.
3. A bin that is empty but **actively receiving** still gets its inflow rate passed through, so
   data arriving during a pass can be downlinked in the same pass rather than waiting.

The recomputation is triggered by `wheneverDynamicsChange` on the playback rate, both downlink
goals, and every bin's `volume`, `receivedVolume` and `actualRate`.

### Downlink goals

`PlaybackData` sets one of two goal resources, and downlink continues while either is positive:

| Resource | Unit | Meaning |
|---|---|---|
| `volumeRequestedToDownlink` | bit | Volume still to be downlinked; decremented by the ground tree's actual rate |
| `durationRequestedToDownlink` | s | Time still to downlink for |

When both reach zero the allocation pass sets every bin's rate to zero.

## 5. Blocking vs. non-blocking effects

This is the most common source of double-counted activity durations.

| Method | Blocks? | Behavior |
|---|---|---|
| `receive(rate, duration)` | **Yes** — advances sim time by `duration` | Raises the receive rate, waits, lowers it |
| `remove(rate, duration)` | **Yes** | Same, for removal |
| `receive(amount)` | **Yes — 1 second** | Clamps `amount` to headroom, then receives at `amount`/second for exactly 1 s |
| `remove(amount)` | **Yes — 1 second** | Clamps to available volume, then removes over 1 s |
| `addReceiveRate(rate)` | No | Raises the rate and returns; **caller must lower it later** |
| `addRemoveRate(rate)` | No | Same, for removal |

Two traps:

- The blocking forms **both produce the data and consume the time**. An activity that calls
  `receive(rate, duration)` and then also `delay(duration)` will be twice as long as intended.
- The fixed-`amount` forms are **not instantaneous**. They deliver the amount as a one-second
  rate spike, so the volume is right but any rate-derived resource (downlink allocation
  included) sees a momentary spike of `amount` per second.

Passing a negative rate to any of these silently redirects to the opposite operation.

## 6. Registered resources

Every bucket registers under its own name; children register themselves recursively.

| Resource | Unit | Notes |
|---|---|---|
| `<bucket>.volume` | bit | Current stored volume |
| `<bucket>.maxVolume` | bit | **Only registered if an explicit upper bound was given** |
| `<bucket>.isEmpty` | bool | `volume ≤ 0` |
| `<bucket>.desiredReceiveRate` / `.desiredRemoveRate` / `.desiredRate` | bit/s | Before clamping |
| `<bucket>.actualRate` | bit/s | After clamping |
| `<bucket>.receivedVolume` / `.removedVolume` | bit | Cumulative actual |
| `<bucket>.desiredReceivedVolume` / `.desiredRemovedVolume` | bit | Cumulative desired |
| `<bucket>.clampedVolume` / `.correctedVolume` | bit | Intermediates; only on children |
| `volumeRequestedToDownlink` | bit | Downlink goal |
| `durationRequestedToDownlink` | s | Downlink goal |
| `playbackDataRate` | bit/s | The downlink rate resource |

With `Data`'s default naming these come out as `onboard.volume`, `onboard.maxVolume`,
`scBin0.volume`, `ground.volume`, `gndBin0.volume`, and so on. **These strings are what
constraints and scheduling goals must reference**, and they are not checked at compile time.

### Optional telemetry

`registerStates` does **not** register these; a mission model opts in via
`registerDownlinkTelemetry(registrar, groupSize)`. They are derived resources only and do not
affect simulation behavior.

| Resource | Meaning |
|---|---|
| `onboard.highestDownlinkPriority` | Index of the highest-priority non-empty bin — the one that downlinks next, or `-1` |
| `ground.currentDownlinkPriority` | Index of the bin currently downlinking, or `-1` |
| `onboard.binGroup_SS_EE.volume` | Adjacent bin volumes summed in blocks of `groupSize`, for a readable timeline when there are many bins |
