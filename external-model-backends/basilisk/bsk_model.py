#!/usr/bin/env python3
"""A spacecraft in low Earth orbit, modeled with Basilisk (AVS Lab, ISC licensed).

Real orbital mechanics propagated against SPICE ephemerides, Earth-shadow eclipse geometry, a solar
array whose output follows the true sun angle, a battery integrating net power, an instrument
filling a storage unit, and a transmitter that drains it only while a ground station is genuinely in
view.

Nothing in this file knows about PlanDev. `bsk_service.py` owns the wire contract; this file owns the
physics, and the seam between them is deliberately narrow:

    sc = Spacecraft(config, epoch)
    sc.schedule(timeline)      # [(time_us, {knob: value}), ...] -- already snapped to the grid
    sc.run(stop_us)
    sc.times_us, sc.channels   # aligned samples, one array per channel

The adapter turns overlapping activities into that piecewise-constant knob timeline, so this file
never learns what an activity is.

TIME. Basilisk's clock only exists on multiples of the task step: `ConfigureStopTime` halts at the
last step at or before the requested time, and a `conditionTime` event fires at the first step at or
after its time. That quantization is real and cannot be hidden -- the adapter compensates for it
explicitly rather than papering over it. Everything here is therefore in whole microseconds on that
grid, and `Spacecraft` refuses a step that is not a whole number of microseconds.
"""
import math
from datetime import timezone

import numpy as np
import Basilisk
from Basilisk.architecture import sysModel
from Basilisk.simulation import (eclipse, groundLocation, simpleBattery, simpleInstrument,
                                 simplePowerSink, simpleSolarPanel, simpleStorageUnit,
                                 spaceToGroundTransmitter, spacecraft)
from Basilisk.utilities import (RigidBodyKinematics, SimulationBaseClass, macros, orbitalMotion,
                                simIncludeGravBody)

BASILISK_VERSION = getattr(Basilisk, "__version__", "unknown")
US_PER_S = 1_000_000
NS_PER_US = 1_000
SECONDS_PER_HOUR = 3600.0
#: WGS-84. Only used for the periapsis sanity check, which runs before any Basilisk body exists;
#: everything downstream uses Basilisk's own `radEquator`.
EARTH_EQUATORIAL_RADIUS_M = 6_378_136.6

#: Every continuously-variable input a plan can drive. The adapter reduces the whole directive set to
#: a piecewise-constant timeline over exactly these names; concurrent activities SUM into one value,
#: which is why the knobs are absolute settings rather than on/off toggles. Two overlapping
#: observations really are two instruments drawing power and filling the recorder at once.
KNOBS = ("instrumentBaudRate", "instrumentPowerWatts",
         "transmitterBaudRate", "transmitterPowerWatts")

#: Recorded channels, by the name the adapter refers to them by. Deliberately raw: unit conversion
#: and derived quantities (state of charge, altitude) happen in `channels`, close to the arrays.
_SPICE_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                 "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def spice_utc(dt):
    """A datetime as the SPICE calendar string Basilisk wants: `2026 JUL 27 00:00:00.000000 (UTC)`.

    The month is looked up in a fixed table rather than taken from `strftime("%b")`, which is
    locale-dependent -- under a non-English locale that silently produces a string SPICE cannot parse
    and the ephemeris load fails somewhere much less obvious than here.
    """
    dt = dt.astimezone(timezone.utc)
    return "%04d %s %02d %02d:%02d:%02d.%06d (UTC)" % (
        dt.year, _SPICE_MONTHS[dt.month - 1], dt.day, dt.hour, dt.minute, dt.second, dt.microsecond)


class ConfigError(ValueError):
    """A configuration the physics cannot accept. The adapter turns this into a 400."""


class GimballedArray(sysModel.SysModel):
    """Re-points the solar array at the sun every step: a two-axis gimballed array.

    Without this the array is body-fixed, and this model has no attitude control -- so whether it
    generates any power at all depends on which side of the vehicle the sun happens to sit on at the
    plan's epoch. That is not a property of any real spacecraft, it is an artefact of leaving
    attitude out of the model, and it is the difference between a battery that cycles with the orbit
    and one that flatlines at zero on some dates and not others. A gimballed array is both ubiquitous
    in flight and the assumption that makes the power model epoch-independent.

    The normal is rotated into the body frame through the spacecraft's own attitude rather than
    assuming the two frames coincide. They do coincide here (no torques, zero initial MRP), but that
    is an assumption a future version of this model would silently break.
    """

    def __init__(self, panel, sun_message, state_message):
        super().__init__()
        self.ModelTag = "arrayGimbal"
        self._panel = panel
        self._sun = sun_message
        self._state = state_message

    def UpdateState(self, current_sim_nanos):
        to_sun = np.array(self._sun.read().PositionVector) - np.array(self._state.read().r_BN_N)
        distance = np.linalg.norm(to_sun)
        if distance == 0.0:
            return
        dcm_BN = RigidBodyKinematics.MRP2C(np.array(self._state.read().sigma_BN))
        self._panel.nHat_B = (dcm_BN @ (to_sun / distance)).tolist()


class Spacecraft:
    """One configured vehicle plus its simulation.

    Built fresh per request. Basilisk holds module state in C++ objects registered with a
    process-wide messaging system, so a `Spacecraft` is emphatically not reusable across plans and
    two of them must not run at once -- `bsk_service.py` holds a lock for exactly that reason.
    """

    def __init__(self, config, epoch):
        step_s = float(config["timeStepSeconds"])
        if not (step_s > 0.0) or not math.isfinite(step_s):
            raise ConfigError("timeStepSeconds must be a positive finite number, got %r" % step_s)
        step_us = round(step_s * US_PER_S)
        if abs(step_s * US_PER_S - step_us) > 1e-6 or step_us <= 0:
            # PlanDev's clock is integer microseconds. A step that lands between two of them would
            # put every recorder sample -- and therefore every profile segment boundary -- on a time
            # PlanDev cannot represent, and the rounding would accumulate across a week-long plan.
            raise ConfigError(
                "timeStepSeconds must be a whole number of microseconds, got %r "
                "(PlanDev's timeline is microsecond-resolution)" % step_s)
        self.step_us = int(step_us)

        self.capacity_ws = float(config["batteryCapacityWattHours"]) * SECONDS_PER_HOUR
        if self.capacity_ws <= 0:
            raise ConfigError("batteryCapacityWattHours must be > 0")
        self.data_capacity_bits = float(config["dataCapacityBits"])
        if self.data_capacity_bits <= 0:
            raise ConfigError("dataCapacityBits must be > 0")
        self.charge_fraction = float(config["initialChargeFraction"])
        if not 0.0 <= self.charge_fraction <= 1.0:
            raise ConfigError("initialChargeFraction must be between 0 and 1, got %r"
                              % self.charge_fraction)
        # Every check that can be made from the numbers alone happens BEFORE any Basilisk object is
        # constructed. Two reasons: a rejected configuration should not leave a half-built simulation
        # registered with the process-wide messaging system, and the checks stay reachable without
        # SPICE kernels on disk -- which is what lets them be tested anywhere.
        self._earth_radius_m = EARTH_EQUATORIAL_RADIUS_M
        periapsis_m = (float(config["semiMajorAxisKm"]) * 1000.0
                       * (1.0 - float(config["eccentricity"])))
        if periapsis_m <= self._earth_radius_m:
            raise ConfigError(
                "the orbit's periapsis is inside the Earth (a=%s km, e=%s): the spacecraft would "
                "start underground and the propagator diverges"
                % (config["semiMajorAxisKm"], config["eccentricity"]))

        self._sim = SimulationBaseClass.SimBaseClass()
        process = self._sim.CreateNewProcess("dynamics")
        process.addTask(self._sim.CreateNewTask("task", macros.sec2nano(step_s)))

        self._build_orbit(config, epoch)
        self._build_power(config)
        self._build_data(config)
        self._build_ground(config)
        self._build_recorders()
        self._initialized = False

    # -- construction ------------------------------------------------------------------------------
    def _build_orbit(self, config, epoch):
        self._sc = spacecraft.Spacecraft()
        self._sc.ModelTag = "sat"

        gravity = simIncludeGravBody.gravBodyFactory()
        bodies = gravity.createBodies(["earth", "sun"])
        bodies["earth"].isCentralBody = True
        # Basilisk's own figure, now that a real body exists; EARTH_EQUATORIAL_RADIUS_M was only
        # standing in for the pre-construction periapsis check.
        self._earth_radius_m = bodies["earth"].radEquator
        # The epoch is the PLAN's start, so eclipse seasons, beta angle and ground-station geometry
        # are those of the dates the planner is actually working on -- not a fixture date.
        self._spice = gravity.createSpiceInterface(time=spice_utc(epoch))
        gravity.addBodiesTo(self._sc)
        self._sim.AddModelToTask("task", self._spice, 100)
        self._sim.AddModelToTask("task", self._sc, 99)

        elements = orbitalMotion.ClassicElements()
        elements.a = float(config["semiMajorAxisKm"]) * 1000.0
        elements.e = float(config["eccentricity"])
        elements.i = float(config["inclinationDeg"]) * macros.D2R
        elements.Omega = float(config["rightAscensionDeg"]) * macros.D2R
        elements.omega = float(config["argumentOfPeriapsisDeg"]) * macros.D2R
        elements.f = float(config["trueAnomalyDeg"]) * macros.D2R
        r_N, v_N = orbitalMotion.elem2rv(bodies["earth"].mu, elements)
        self._sc.hub.r_CN_NInit = r_N
        self._sc.hub.v_CN_NInit = v_N

        self._eclipse = eclipse.Eclipse()
        self._eclipse.addSpacecraftToModel(self._sc.scStateOutMsg)
        self._eclipse.addPlanetToModel(self._spice.planetStateOutMsgs[0])
        self._eclipse.sunInMsg.subscribeTo(self._spice.planetStateOutMsgs[1])
        self._sim.AddModelToTask("task", self._eclipse)

    def _build_power(self, config):
        self._panel = simpleSolarPanel.SimpleSolarPanel()
        self._panel.ModelTag = "array"
        self._panel.stateInMsg.subscribeTo(self._sc.scStateOutMsg)
        self._panel.sunEclipseInMsg.subscribeTo(self._eclipse.eclipseOutMsgs[0])
        self._panel.sunInMsg.subscribeTo(self._spice.planetStateOutMsgs[1])
        self._panel.setPanelParameters([1, 0, 0],
                                       float(config["solarPanelAreaSquareMeters"]),
                                       float(config["solarPanelEfficiency"]))
        # The gimbal is added FIRST so it runs first: models at equal priority execute in insertion
        # order, and a normal computed after the panel has already drawn power is a normal one step
        # stale. At a 5-second step that is invisible; at a 5-minute one it is not.
        self._gimbal = GimballedArray(self._panel, self._spice.planetStateOutMsgs[1],
                                      self._sc.scStateOutMsg)
        self._sim.AddModelToTask("task", self._gimbal)
        self._sim.AddModelToTask("task", self._panel)

        # One sink per knob, plus the always-on bus. Because the adapter has already summed
        # overlapping activities into a single value per knob, one sink each is enough -- no sink is
        # ever contended between two concurrent activities.
        self._bus = self._sink("bus", -abs(float(config["busPowerWatts"])))
        self._instrument_power = self._sink("instrumentPower", 0.0)
        self._transmitter_power = self._sink("transmitterPower", 0.0)

        self._battery = simpleBattery.SimpleBattery()
        self._battery.ModelTag = "battery"
        self._battery.storageCapacity = self.capacity_ws
        self._battery.storedCharge_Init = self.capacity_ws * self.charge_fraction
        for node in (self._panel, self._bus, self._instrument_power, self._transmitter_power):
            self._battery.addPowerNodeToModel(node.nodePowerOutMsg)
        self._sim.AddModelToTask("task", self._battery)

    def _sink(self, tag, watts):
        sink = simplePowerSink.SimplePowerSink()
        sink.ModelTag = tag
        sink.nodePowerOut = watts
        self._sim.AddModelToTask("task", sink)
        return sink

    def _build_data(self, config):
        self._instrument = simpleInstrument.SimpleInstrument()
        self._instrument.ModelTag = "instrument"
        self._instrument.nodeBaudRate = 0.0
        self._instrument.nodeDataName = "science"
        self._sim.AddModelToTask("task", self._instrument)

        self._transmitter = spaceToGroundTransmitter.SpaceToGroundTransmitter()
        self._transmitter.ModelTag = "transmitter"
        self._transmitter.nodeBaudRate = 0.0
        self._transmitter.nodeDataName = "science"
        self._transmitter.packetSize = -1.0e6
        self._transmitter.numBuffers = 1
        self._sim.AddModelToTask("task", self._transmitter)

        self._storage = simpleStorageUnit.SimpleStorageUnit()
        self._storage.ModelTag = "storage"
        self._storage.storageCapacity = self.data_capacity_bits
        self._storage.addDataNodeToModel(self._instrument.nodeDataOutMsg)
        self._storage.addDataNodeToModel(self._transmitter.nodeDataOutMsg)
        self._sim.AddModelToTask("task", self._storage)
        self._transmitter.addStorageUnitToTransmitter(self._storage.storageUnitDataOutMsg)

    def _build_ground(self, config):
        self._station = groundLocation.GroundLocation()
        self._station.ModelTag = "groundStation"
        self._station.planetRadius = self._earth_radius_m
        self._station.specifyLocation(float(config["groundStationLatitudeDeg"]) * macros.D2R,
                                      float(config["groundStationLongitudeDeg"]) * macros.D2R,
                                      float(config["groundStationAltitudeMeters"]))
        self._station.planetInMsg.subscribeTo(self._spice.planetStateOutMsgs[0])
        self._station.minimumElevation = float(config["groundStationMinElevationDeg"]) * macros.D2R
        self._station.addSpacecraftToModel(self._sc.scStateOutMsg)
        self._sim.AddModelToTask("task", self._station)
        # The transmitter gates itself on this: with no access it emits no negative baud, so a
        # Downlink scheduled out of view moves exactly zero bits. That is the point -- the model
        # reports what physically happened and PlanDev's constraint engine judges the plan.
        self._transmitter.addAccessMsgToTransmitter(self._station.accessOutMsgs[-1])

    def _build_recorders(self):
        self._recorders = {
            "eclipse": self._eclipse.eclipseOutMsgs[0].recorder(),
            "array": self._panel.nodePowerOutMsg.recorder(),
            "battery": self._battery.batPowerOutMsg.recorder(),
            "storage": self._storage.storageUnitDataOutMsg.recorder(),
            "access": self._station.accessOutMsgs[-1].recorder(),
            "state": self._sc.scStateOutMsg.recorder(),
            # Earth's own position, recorded on the same task so it is sampled at the same instants.
            # Needed because `scStateOutMsg.r_BN_N` is expressed in the SPICE inertial frame, whose
            # origin is the solar-system BARYCENTRE, not the central body: |r_BN_N| is about
            # 1.52e8 km (Earth's heliocentric distance), not the orbital radius. The dynamics are
            # unaffected -- the gravity effector works in absolute positions and the orbit really is
            # the requested 7000 km one -- but any geometry DERIVED here has to subtract Earth first.
            "earth": self._spice.planetStateOutMsgs[0].recorder(),
        }
        for recorder in self._recorders.values():
            self._sim.AddModelToTask("task", recorder)

    # -- driving -----------------------------------------------------------------------------------
    def schedule(self, timeline):
        """Apply `[(time_us, {knob: value}), ...]`, each an ABSOLUTE setting for every knob.

        Times must already be on the step grid; `bsk_service` snaps them, because the snapping is
        also what the reported span offsets have to agree with, and doing it in two places is how
        those two drift apart.
        """
        for index, (time_us, knobs) in enumerate(timeline):
            if time_us % self.step_us:
                raise ConfigError("knob change at %dus is off the %dus step grid"
                                  % (time_us, self.step_us))
            unknown = set(knobs) - set(KNOBS)
            if unknown:
                raise ConfigError("unknown knobs %s" % sorted(unknown))
            # `settings=knobs` binds this iteration's dict; a bare closure over `knobs` would leave
            # every event applying the last one.
            self._sim.createNewEvent(
                "knobs_%d" % index, self.step_us * NS_PER_US, True,
                conditionTime=time_us * NS_PER_US,
                actionFunction=lambda _sim, settings=knobs: self._apply(settings))

    def _apply(self, knobs):
        self._instrument.nodeBaudRate = float(knobs["instrumentBaudRate"])
        self._instrument_power.nodePowerOut = -abs(float(knobs["instrumentPowerWatts"]))
        # A transmitter DRAINS the storage unit, so its baud rate is negative by convention. The
        # adapter deals in positive downlink rates because that is what a planner types.
        self._transmitter.nodeBaudRate = -abs(float(knobs["transmitterBaudRate"]))
        self._transmitter_power.nodePowerOut = -abs(float(knobs["transmitterPowerWatts"]))

    def run(self, stop_us):
        """Propagate to `stop_us`. Basilisk stops at the last step at or before it; the adapter
        closes the remaining sliver of the plan window itself."""
        self._sim.InitializeSimulation()
        self._initialized = True
        self._sim.ConfigureStopTime(stop_us * NS_PER_US)
        self._sim.ExecuteSimulation()

    # -- results -----------------------------------------------------------------------------------
    @property
    def times_us(self):
        """Sample offsets in microseconds, one per task step, shared by every channel.

        All recorders sit on the same task at the same rate, so their sample arrays are aligned by
        construction -- but that is an assumption worth checking rather than trusting, because a
        misaligned channel would silently shift a resource in time with no error anywhere.
        """
        times_ns = [int(t) for t in self._recorders["battery"].times()]
        for name, recorder in self._recorders.items():
            count = len(recorder.times())
            if count != len(times_ns):
                raise ConfigError("recorder '%s' produced %d samples, battery produced %d"
                                  % (name, count, len(times_ns)))
        offsets = []
        for t in times_ns:
            if t % NS_PER_US:
                raise ConfigError("recorder sample at %dns is not a whole microsecond" % t)
            offsets.append(t // NS_PER_US)
        return offsets

    @property
    def channels(self):
        """Every recorded channel as a plain float list, keyed by the adapter's resource names.

        Unit conversion lives here so the adapter never does arithmetic on raw Basilisk output:
        joules to watt-hours, metres to kilometres, a shadow factor to a three-way eclipse state.
        """
        # Earth-relative, not barycentre-relative -- see the "earth" recorder in _build_recorders.
        radius_m = np.linalg.norm(np.array(self._recorders["state"].r_BN_N)
                                  - np.array(self._recorders["earth"].PositionVector), axis=1)
        shadow = np.array(self._recorders["eclipse"].shadowFactor, dtype=float)
        charge_ws = np.array(self._recorders["battery"].storageLevel, dtype=float)
        access = np.array(self._recorders["access"].hasAccess, dtype=float)
        return {
            "solarArrayWatts": np.array(self._recorders["array"].netPower, dtype=float),
            "netPowerWatts": np.array(self._recorders["battery"].currentNetPower, dtype=float),
            "batteryWattHours": charge_ws / SECONDS_PER_HOUR,
            "stateOfCharge": charge_ws / self.capacity_ws,
            "storedBits": np.array(self._recorders["storage"].storageLevel, dtype=float),
            "sunlightFraction": shadow,
            "altitudeKm": (radius_m - self._earth_radius_m) / 1000.0,
            # `shadowFactor` is 1 in full sun, 0 in umbra and strictly between the two in penumbra.
            # Reporting the three states, rather than a sunlit boolean, is the difference between a
            # constraint that can say "no imaging in penumbra" and one that cannot.
            "eclipseState": ["Sunlight" if f >= 1.0 else "Umbra" if f <= 0.0 else "Penumbra"
                             for f in shadow],
            "groundStationInView": [bool(a) for a in access],
        }
