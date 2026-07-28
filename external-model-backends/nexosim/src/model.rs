//! The model: a cryocooled imager, as two NeXosim components.
//!
//! `Cryostat` integrates the detector's heat balance and runs a bang-bang cryocooler. `Recorder`
//! holds the frames an observation writes and drains them on downlink. They are connected by a
//! requestor port, because a frame has to be stamped with the temperature at the instant it was
//! exposed and the detector is ramping between thermal events.
//!
//! Nothing here samples on a grid. Every model writes one history row per event it processes, at
//! the microsecond that event occurred, and the adapter turns those rows into segments. That is the
//! whole reason to put a discrete-event simulator behind this contract: a fixed-step backend has to
//! choose a step, and then every activity edge and every autonomous switch gets quantized to it.

use nexosim::model::{Context, Model, schedulable};
use nexosim::ports::UniRequestor;
use nexosim::simulation::EventKey;
use nexosim::time::MonotonicTime;
use serde::{Deserialize, Serialize};
use std::time::Duration;

use crate::decl::MAX_COOLER_SWITCHES;

/// The simulation configuration, already defaulted and typechecked by `adapter_core`.
#[derive(Clone, Debug)]
pub struct Config {
    pub initial_k: f64,
    pub setpoint_k: f64,
    pub deadband_k: f64,
    pub mass_j_per_k: f64,
    pub parasitic_w: f64,
    pub lift_w: f64,
    pub cooler_draw_w: f64,
    pub bus_w: f64,
    pub capacity_frames: i64,
}

// ---------- cryostat ------------------------------------------------------------------------------
/// The detector's state at one instant. One row per event, never one row per tick.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ThermalRow {
    pub at_us: i64,
    pub kelvin: f64,
    pub cooling: bool,
    pub load_w: f64,
}

/// The cold end of the instrument: a thermal mass with a parasitic leak, whatever the payload is
/// dissipating, and a cryocooler under hysteresis control.
///
/// The cooler is the part PlanDev cannot express. Nothing in the plan turns it on; it switches when
/// the detector crosses `setpoint +/- deadband`, at an instant computed from the current heat
/// balance, and it re-times itself whenever an activity changes that balance.
#[derive(Serialize, Deserialize)]
pub struct Cryostat {
    epoch: MonotonicTime,
    /// When the temperature was last integrated. Every port advances to `cx.time()` FIRST and
    /// changes the rate second; doing it the other way round applies the new rate retroactively to
    /// the interval that ran under the old one.
    last: MonotonicTime,
    /// End of the simulated window. A crossing beyond it is not scheduled -- partly because there
    /// is no point, and partly because a near-zero heat rate puts the crossing 10^12 seconds out,
    /// where the microsecond count no longer fits in the integer that would carry it.
    horizon_us: i64,
    kelvin: f64,
    cooling: bool,
    instrument_w: f64,
    radio_w: f64,
    setpoint_k: f64,
    deadband_k: f64,
    mass_j_per_k: f64,
    parasitic_w: f64,
    lift_w: f64,
    cooler_draw_w: f64,
    bus_w: f64,
    switch_key: Option<EventKey>,
    switches: u32,
    /// Set when the controller has switched more times than any plan could justify. The run is not
    /// aborted from inside the model -- a NeXosim input port has nowhere to return an error to --
    /// so the flag comes back with the history and the adapter refuses there.
    pub chattered: bool,
    log: Vec<ThermalRow>,
}

#[Model]
impl Cryostat {
    pub fn new(cfg: &Config, epoch: MonotonicTime, horizon_us: i64) -> Self {
        let mut cryostat = Cryostat {
            epoch,
            last: epoch,
            horizon_us,
            kelvin: cfg.initial_k,
            cooling: false,
            instrument_w: 0.0,
            radio_w: 0.0,
            setpoint_k: cfg.setpoint_k,
            deadband_k: cfg.deadband_k,
            mass_j_per_k: cfg.mass_j_per_k,
            parasitic_w: cfg.parasitic_w,
            lift_w: cfg.lift_w,
            cooler_draw_w: cfg.cooler_draw_w,
            bus_w: cfg.bus_w,
            switch_key: None,
            switches: 0,
            chattered: false,
            log: Vec::new(),
        };
        // t=0 has to be in the log before anything runs: a profile that does not start at the
        // beginning of the window is rejected by merlin's ingest gate, and the first activity might
        // be hours in.
        cryostat.log.push(ThermalRow {
            at_us: 0,
            kelvin: cryostat.kelvin,
            cooling: cryostat.cooling,
            load_w: cryostat.load_w(),
        });
        cryostat
    }

    /// Net heat into the detector, as a temperature rate. Negative while the cooler wins.
    fn rate_k_per_s(&self) -> f64 {
        let cooling = if self.cooling { self.lift_w } else { 0.0 };
        (self.parasitic_w + self.instrument_w - cooling) / self.mass_j_per_k
    }

    /// Total electrical load. The cooler's DRAW is not its heat LIFT: it pulls 55 W off the bus to
    /// move 40 W out of the cold end, which is why turning it on shows up on two resources at once.
    fn load_w(&self) -> f64 {
        let cooler = if self.cooling { self.cooler_draw_w } else { 0.0 };
        self.bus_w + self.instrument_w + self.radio_w + cooler
    }

    fn now_us(&self, now: MonotonicTime) -> i64 {
        now.duration_since(self.epoch).as_micros() as i64
    }

    fn advance(&mut self, now: MonotonicTime) {
        let dt = now.duration_since(self.last).as_secs_f64();
        if dt > 0.0 {
            self.kelvin += self.rate_k_per_s() * dt;
        }
        self.last = now;
    }

    fn record(&mut self, now: MonotonicTime) {
        let at_us = self.now_us(now);
        let row = ThermalRow {
            at_us,
            kelvin: self.kelvin,
            cooling: self.cooling,
            load_w: self.load_w(),
        };
        match self.log.last_mut() {
            // Several events legitimately land on the same microsecond -- one activity ending as
            // the next begins, a cooler switch coinciding with either. Only the state after all of
            // them is a segment boundary; keeping the intermediate rows emits zero-duration
            // segments, which merlin stores as profile entries no query can ever land inside.
            Some(last) if last.at_us == at_us => *last = row,
            _ => self.log.push(row),
        }
    }

    fn flip(&mut self) {
        self.cooling = !self.cooling;
        self.switches += 1;
        if self.switches > MAX_COOLER_SWITCHES {
            self.chattered = true;
        }
    }

    /// Re-derives the cooler state and the instant of its next switch, after something changed the
    /// heat balance.
    ///
    /// The pending switch is CANCELLED and recomputed rather than left alone. It was scheduled for
    /// a crossing computed from the old rate, and an activity starting in between makes that
    /// instant wrong -- the cooler would then switch at a time nothing in the plan explains, on a
    /// profile self-consistent enough that nothing flags it.
    fn settle(&mut self, cx: &Context<Self>) {
        if let Some(key) = self.switch_key.take() {
            key.cancel();
        }
        if self.chattered {
            return;
        }
        // At most one immediate flip is possible: with a positive deadband, being past one
        // threshold puts the temperature strictly on the near side of the other.
        let past_upper = !self.cooling && self.kelvin >= self.setpoint_k + self.deadband_k;
        let past_lower = self.cooling && self.kelvin <= self.setpoint_k - self.deadband_k;
        if past_upper || past_lower {
            self.flip();
            if self.chattered {
                return;
            }
        }
        self.rearm(cx);
    }

    /// Schedules the next threshold crossing, if the current heat balance reaches one.
    fn rearm(&mut self, cx: &Context<Self>) {
        let target = if self.cooling {
            self.setpoint_k - self.deadband_k
        } else {
            self.setpoint_k + self.deadband_k
        };
        // Non-finite when the rate is zero, negative when the balance runs the other way: either
        // means the controller simply never switches again, which is a legitimate steady state and
        // not an error.
        let seconds = (target - self.kelvin) / self.rate_k_per_s();
        if !seconds.is_finite() || seconds <= 0.0 {
            return;
        }
        // CEIL to the next whole microsecond. PlanDev's timeline is microseconds; NeXosim's is
        // nanoseconds. Switching at a nanosecond instant would put the event between two
        // microseconds, and the segment boundary -- which is the event time truncated -- would then
        // disagree with the event by up to a microsecond, in the direction that reports the cooler
        // coming on before it did.
        // A float-to-int cast saturates in Rust rather than wrapping, so a crossing 10^12 seconds
        // out lands on i64::MAX here; `checked_add` is what keeps that from overflowing into a
        // deadline in the past.
        let after_us = (seconds * 1e6).ceil() as i64;
        if after_us < 1 {
            return;
        }
        match self.now_us(cx.time()).checked_add(after_us) {
            Some(at_us) if at_us <= self.horizon_us => {}
            _ => return,
        }
        if let Ok(key) = cx.schedule_keyed_event(
            Duration::from_micros(after_us as u64),
            schedulable!(Self::switch_cooler),
            (),
        ) {
            self.switch_key = Some(key);
        }
    }

    /// The cryocooler crossing its own threshold. Not in any plan.
    ///
    /// The `()` argument is not decoration: a schedulable's LAST parameter is its context and the
    /// one before it is the event payload, so a method that takes only a context is read as one
    /// whose payload is the context.
    #[nexosim(schedulable)]
    async fn switch_cooler(&mut self, _: (), cx: &Context<Self>) {
        self.advance(cx.time());
        self.switch_key = None; // this key just fired
        // Flipped unconditionally rather than by re-testing the threshold. The temperature at this
        // instant is at the threshold to within the microsecond the deadline was rounded up by, and
        // a re-test that came out a hair short would reschedule one microsecond later and do it
        // again -- a busy loop that only ends at the horizon.
        self.flip();
        if !self.chattered {
            self.rearm(cx);
        }
        self.record(cx.time());
    }

    /// What the payload is dissipating at the cold end [W] -- input port.
    pub async fn set_instrument_watts(&mut self, watts: f64, cx: &Context<Self>) {
        self.advance(cx.time());
        self.instrument_w = watts;
        self.settle(cx);
        self.record(cx.time());
    }

    /// What the transmitter is drawing [W] -- input port. Bus load only: it does not heat the
    /// detector, which is the entire reason it is a separate channel from the instrument's.
    pub async fn set_radio_watts(&mut self, watts: f64, cx: &Context<Self>) {
        self.advance(cx.time());
        self.radio_w = watts;
        self.settle(cx);
        self.record(cx.time());
    }

    /// Retunes the cryocooler [K] -- input port.
    pub async fn set_setpoint(&mut self, kelvin: f64, cx: &Context<Self>) {
        self.advance(cx.time());
        self.setpoint_k = kelvin;
        self.settle(cx);
        self.record(cx.time());
    }

    /// Settles the controller at t=0 -- input port.
    ///
    /// A detector that starts warmer than `setpoint + deadband` must already be cooling in the
    /// first segment. Without this the cooler stays off until the first activity happens to call
    /// something else, and the profile opens with a plateau the physics does not have.
    pub async fn start(&mut self, _: (), cx: &Context<Self>) {
        self.settle(cx);
        self.record(cx.time());
    }

    /// The detector temperature right now -- replier port, for the recorder.
    pub async fn peek_kelvin(&mut self, _: (), cx: &Context<Self>) -> f64 {
        self.advance(cx.time());
        self.kelvin
    }

    /// Everything that happened -- replier port, for the adapter.
    pub async fn history(&mut self, _: (), cx: &Context<Self>) -> (Vec<ThermalRow>, bool) {
        self.advance(cx.time());
        self.record(cx.time());
        (self.log.clone(), self.chattered)
    }
}

// ---------- recorder ------------------------------------------------------------------------------
/// The metadata PlanDev sees for the most recent stored frame. `id` 0 means no frame yet: a struct
/// resource has no null, because merlin's gate rejects a struct value missing a declared field.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Frame {
    pub id: i64,
    pub target: String,
    pub kelvin: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RecorderRow {
    pub at_us: i64,
    pub frames: i64,
    pub target: String,
    pub newest: Frame,
    /// Cumulative and monotonic, all three. A span's computed attributes are the DIFFERENCE of a
    /// counter across its window, which is what makes them correct for a plan with several
    /// observations of the same target: an attempt to count log rows instead has to decide which
    /// activity each row belonged to, and the rows do not say.
    pub written: i64,
    pub dropped: i64,
    pub sent: i64,
}

/// The solid-state recorder. Frames arrive one per integration period during an observation and
/// leave one per period during a downlink.
#[derive(Serialize, Deserialize)]
pub struct Recorder {
    epoch: MonotonicTime,
    capacity: i64,
    frames: i64,
    target: String,
    newest: Frame,
    written: i64,
    dropped: i64,
    sent: i64,
    frame_period_us: u64,
    send_period_us: u64,
    detector_kelvin: UniRequestor<(), f64>,
    log: Vec<RecorderRow>,
}

#[Model]
impl Recorder {
    pub fn new(cfg: &Config, epoch: MonotonicTime, detector_kelvin: UniRequestor<(), f64>) -> Self {
        let newest = Frame {
            id: 0,
            target: String::new(),
            kelvin: cfg.initial_k,
        };
        let mut recorder = Recorder {
            epoch,
            capacity: cfg.capacity_frames,
            frames: 0,
            target: String::new(),
            newest: newest.clone(),
            written: 0,
            dropped: 0,
            sent: 0,
            frame_period_us: 0,
            send_period_us: 0,
            detector_kelvin,
            log: Vec::new(),
        };
        recorder.log.push(RecorderRow {
            at_us: 0,
            frames: 0,
            target: String::new(),
            newest,
            written: 0,
            dropped: 0,
            sent: 0,
        });
        recorder
    }

    fn now_us(&self, now: MonotonicTime) -> i64 {
        now.duration_since(self.epoch).as_micros() as i64
    }

    fn record(&mut self, now: MonotonicTime) {
        let at_us = self.now_us(now);
        let row = RecorderRow {
            at_us,
            frames: self.frames,
            target: self.target.clone(),
            newest: self.newest.clone(),
            written: self.written,
            dropped: self.dropped,
            sent: self.sent,
        };
        match self.log.last_mut() {
            Some(last) if last.at_us == at_us => *last = row,
            _ => self.log.push(row),
        }
    }

    /// Begins an observation: `(target, frame period [us], frames to write)`.
    ///
    /// The COUNT is fixed by the adapter and counted down in the event's own payload, rather than
    /// the chain being stopped by the end-of-observation edge. An observation of exactly N frame
    /// periods has its Nth frame land on the same microsecond as its end, and which of those two
    /// the queue runs first is not something the frame count should depend on.
    pub async fn begin_observation(
        &mut self,
        (target, period_us, count): (String, u64, i64),
        cx: &Context<Self>,
    ) {
        self.frame_period_us = period_us;
        self.target = target.clone();
        self.arm_frame(target, count, cx);
        self.record(cx.time());
    }

    fn arm_frame(&mut self, target: String, remaining: i64, cx: &Context<Self>) {
        if remaining <= 0 || self.frame_period_us == 0 {
            return;
        }
        // Unkeyed, so there is nothing to cancel: the count already guarantees no frame is
        // scheduled past the window. A cancellable chain would let a NEXT observation beginning on
        // the same microsecond as this one's last frame cancel that frame, purely on queue order.
        let _ = cx.schedule_event(
            Duration::from_micros(self.frame_period_us),
            schedulable!(Self::write_frame),
            (target, remaining),
        );
    }

    #[nexosim(schedulable)]
    async fn write_frame(&mut self, (target, remaining): (String, i64), cx: &Context<Self>) {
        // Asked for over a requestor port instead of read from a value the cryostat pushed
        // earlier. Between two thermal events the detector is RAMPING, so the last broadcast
        // temperature is stale by however long ago it was sent -- and the frame would carry the
        // temperature the detector had at the previous cooler switch, which can be minutes off.
        let kelvin = self.detector_kelvin.send(()).await;
        if self.frames < self.capacity {
            self.frames += 1;
            self.written += 1;
            // The target comes from the event, not from `self.target`. The end-of-observation edge
            // can clear `self.target` on the same microsecond this frame is written, and a frame
            // labelled with the empty string is a frame no one can attribute.
            self.newest = Frame {
                id: self.written,
                target: target.clone(),
                kelvin,
            };
        } else {
            self.dropped += 1;
        }
        self.arm_frame(target, remaining - 1, cx);
        self.record(cx.time());
    }

    /// Ends an observation -- input port. Only clears what the instrument is pointing at; the frame
    /// chain stops on its own count.
    pub async fn end_observation(&mut self, _: (), cx: &Context<Self>) {
        self.target = String::new();
        self.record(cx.time());
    }

    /// Begins a downlink: `(frame period [us], frames to send)` -- input port.
    pub async fn begin_downlink(&mut self, (period_us, count): (u64, i64), cx: &Context<Self>) {
        self.send_period_us = period_us;
        self.arm_send(count, cx);
        self.record(cx.time());
    }

    fn arm_send(&mut self, remaining: i64, cx: &Context<Self>) {
        if remaining <= 0 || self.send_period_us == 0 {
            return;
        }
        let _ = cx.schedule_event(
            Duration::from_micros(self.send_period_us),
            schedulable!(Self::send_frame),
            remaining,
        );
    }

    #[nexosim(schedulable)]
    async fn send_frame(&mut self, remaining: i64, cx: &Context<Self>) {
        // A downlink of an empty recorder moves nothing. Saturating rather than going negative:
        // `framesStored` is what PlanDev charts, and a negative frame count is a modelling bug that
        // renders as a plausible-looking line.
        if self.frames > 0 {
            self.frames -= 1;
            self.sent += 1;
        }
        self.arm_send(remaining - 1, cx);
        self.record(cx.time());
    }

    /// Everything that happened -- replier port, for the adapter.
    pub async fn history(&mut self, _: (), cx: &Context<Self>) -> Vec<RecorderRow> {
        self.record(cx.time());
        self.log.clone()
    }
}
