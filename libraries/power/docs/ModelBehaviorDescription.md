# Power Model — Behavior Description

The equations behind
[`GenericSolarArray`](../src/main/java/gov/nasa/ammos/plandev/power/GenericSolarArray.java),
[`RtgPowerProduction`](../src/main/java/gov/nasa/ammos/plandev/power/RtgPowerProduction.java) and
[`BatteryModel`](../src/main/java/gov/nasa/ammos/plandev/power/BatteryModel.java), and the
clamping rules that govern battery state of charge.

This document is derived from the implementation in this repository.

## 1. Structure

The power model is three pieces wired together by the mission model:

```
   PowerSource (solar array or RTG)  ──┐
                                       ├──►  BatteryModel  ──►  batterySOC
   Total spacecraft load (from a PEL) ─┘
```

A `PowerSource` exposes one resource, `powerProduction` (W). `BatteryModel` takes that plus a
total-load resource and integrates the difference. Nothing in the library sums the PEL for you —
the mission model supplies `totalLoad`, typically from a generated `PELModel`.

## 2. Solar array power production

```
if deploymentState ≠ DEPLOYED:
    P = 0
else:
    P = (S / d²) · A_cell · η_static · cos(θ) · f_eclipse
```

| Symbol | Source | Meaning |
|---|---|---|
| `S` | constant `1360.8` | Solar irradiance at 1 AU (W/m²) |
| `d` | `solarDistance` resource | Spacecraft distance from the Sun (AU) |
| `A_cell` | `arrayMechArea × packingFactor` | Active cell area (m²) |
| `η_static` | `cellEfficiency × conversionEfficiency × otherLosses` | Combined static efficiency, computed once at construction |
| `θ` | `arrayToSunAngle` resource | Angle between the Sun and the array normal (degrees) |
| `f_eclipse` | `eclipseFactor` resource | Fraction of irradiance surviving eclipse; 1.0 = full Sun |

Three things to be aware of:

- **`cos(θ)` is not clamped.** An `arrayToSunAngle` beyond ±90° yields **negative** power
  production. The model assumes the caller supplies a sensible angle; a real off-pointing model
  should clamp at zero.
- **`solarDistance`, `arrayToSunAngle` and `eclipseFactor` are inputs, not computed here.** The
  library takes them as resources. Simple examples hold them constant (1 AU, Sun-facing, no
  eclipse); [`libraries/geometry`](../../geometry/) supplies real SPICE-derived values.
- **Deployment is binary.** There is no partial-deployment factor: undeployed produces exactly
  zero.

### Configuration defaults (`SolarArraySimConfig`)

| Parameter | Default | Meaning |
|---|---|---|
| `deploymentState` | `DEPLOYED` | Initial deployment state |
| `arrayMechArea` | 5.0 | Mechanical array area (m²) |
| `packingFactor` | 0.9 | Active cell area / mechanical area |
| `cellEfficiency` | 0.28 | Per-cell conversion efficiency |
| `conversionEfficiency` | 0.9 | Raw-to-usable power conversion loss |
| `otherLosses` | 1.0 | Shadowing, cell mismatch, cover glass, … |

## 3. RTG power production

Exponential decay from a beginning-of-life value:

```
P(t) = N · P_BOL · exp( −(k/100) · Δyears )
```

where `Δyears` is the elapsed time from `decayStart` to the current simulation instant, `k` is
`decayRate` **expressed as a percentage per year**, `N` is `numRTGs`, and `P_BOL` is
`bolPowerPerRTG`.

Note that `decayStart` is independent of plan start, so a plan beginning years after
`decayStart` correctly starts from an already-decayed value.

This is the library's one **black-box** (`Unstructured`) resource — it is a direct function of
time rather than an integral — and it is converted to a polynomial via `approximateAsLinear`
with a tolerance of `1e-4`. That approximation is why the registered profile is piecewise
linear rather than a true exponential.

## 4. Battery

### Current

```
I_unclamped = (P_production − P_demand) / V_bus          [A]
```

Positive current charges, negative discharges.

### Charge and state of charge

Charge is integrated in **amp-seconds** and clamped, then converted back to amp-hours:

```
batteryChargeSec = clampedIntegrate( I_unclamped,
                                     lower = 0,
                                     upper = C_Ah · 3600,
                                     initial = C_Ah · (SOC₀/100) · 3600 )

batteryCharge = batteryChargeSec / 3600                  [Ah]
batterySOC    = batteryCharge / C_Ah · 100               [%]
batteryFull   = batterySOC ≥ 100
batteryEmpty  = batterySOC ≤ 0
```

The factor of 3600 exists because streamline integrates in seconds while battery capacity is
quoted in amp-hours.

### The two current resources — an important subtlety

```
batteryCurrent = d(batteryChargeSec)/dt
```

`batteryCurrent` is the derivative of the **clamped** integral, so when the battery is full or
empty it reads **zero even though the unclamped current is not**. That is physically right — a
full battery accepts no more charge — but it means:

- Use **`batteryCurrent`** to see what the battery is actually doing.
- Use **`batteryCurrentUnclamped`** to see the true power imbalance. A large positive
  `batteryCurrentUnclamped` while `batteryCurrent` sits at zero means surplus generation is
  being **discarded** because the battery is full; a large negative one while `batteryFull` is
  false and `batteryEmpty` is true means the spacecraft is browning out.

Neither is an error signal on its own. The pair is what tells you the story.

### Battery capacity in watt-hours

`batteryCapacityWH = batteryCapacityAH × busVoltage` is exposed as a field for convenience. It
is not registered as a resource.

### Configuration defaults (`BatterySimConfig`)

| Parameter | Default | Meaning |
|---|---|---|
| `batteryCapacity` | 100.0 | Capacity (Ah) |
| `busVoltage` | 28.0 | Bus voltage (V) |
| `initialSOC` | 100.0 | Initial state of charge (%) |

## 5. Registered resources

`BatteryModel` prefixes its resources with the `name` given to its constructor. **If `name` is
blank the prefix is `battery.`; otherwise it is `<name>.`** — so a model constructed as
`new BatteryModel("mainbattery", …)` registers `mainbattery.batterySOC`, not
`battery.batterySOC`. This is the usual cause of a constraint referencing a resource that does
not exist.

| Resource | Unit |
|---|---|
| `<name>.batterySOC` | % |
| `<name>.batteryCharge` | Ah |
| `<name>.batteryChargeSec` | A-s |
| `<name>.batteryCurrent` | A |
| `<name>.batteryCurrentUnclamped` | A |
| `<name>.batteryFull` | bool |
| `<name>.batteryEmpty` | bool |
| `array.powerProduction` | W |
| `spacecraft.solarDistance` | AU |
| `spacecraft.arrayToSunAngle` | deg |
| `rtg.powerProduction` | W |

Note the solar array and RTG resource names are **not** prefixed by an instance name, so a model
with two arrays would collide.
