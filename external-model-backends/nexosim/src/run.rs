//! Assembling the bench, running it, and turning what came back into profiles and spans.
//!
//! The run itself is three lines: schedule every directive edge at its absolute microsecond, call
//! `step_until` once, read the histories back. There is no sampling cadence and no step size,
//! because NeXosim advances to the next scheduled event and lands exactly on the deadline it is
//! given. Everything else in this file is the conversion between what a discrete-event simulator
//! produces (a value AT an instant) and what PlanDev stores (a value OVER an interval).

use nexosim::ports::{EventSource, QuerySource, UniRequestor};
use nexosim::simulation::{Mailbox, SimInit};
use nexosim::time::MonotonicTime;
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::time::Duration;

use crate::decl;
use crate::model::{Config, Cryostat, Recorder, RecorderRow, ThermalRow};
use crate::wire::{Directive, Fault, Profile, Request, Response, Segment, Span, caller, int, ramp,
                  real};

// ---------- reading the request -------------------------------------------------------------------
/// A configuration value `adapter_core` promised to send. Its absence is a broken host, not a
/// broken plan, so it is a `Model` fault and not a 400 aimed at the planner.
fn cfg_real(cfg: &Map<String, Value>, name: &str) -> Result<f64, Fault> {
    match cfg.get(name).and_then(Value::as_f64) {
        Some(v) if v.is_finite() => Ok(v),
        other => Err(Fault::Model(format!(
            "configuration parameter '{name}' should have arrived as a finite number, got {}",
            other.map(|_| "a non-finite number".into()).unwrap_or_else(|| format!(
                "{:?}",
                cfg.get(name)
            ))
        ))),
    }
}

fn cfg_int(cfg: &Map<String, Value>, name: &str) -> Result<i64, Fault> {
    cfg.get(name).and_then(Value::as_i64).ok_or_else(|| {
        Fault::Model(format!(
            "configuration parameter '{name}' should have arrived as an integer, got {:?}",
            cfg.get(name)
        ))
    })
}

/// Reads the configuration and refuses the settings that have no simulation, as opposed to a bad
/// one. Each of these is a planner's mistake, so each names the parameter that fixes it.
pub fn configuration(cfg: &Map<String, Value>) -> Result<Config, Fault> {
    let config = Config {
        initial_k: cfg_real(cfg, "initialKelvin")?,
        setpoint_k: cfg_real(cfg, "setpointKelvin")?,
        deadband_k: cfg_real(cfg, "deadbandKelvin")?,
        mass_j_per_k: cfg_real(cfg, "thermalMassJPerK")?,
        parasitic_w: cfg_real(cfg, "parasiticWatts")?,
        lift_w: cfg_real(cfg, "coolerLiftWatts")?,
        cooler_draw_w: cfg_real(cfg, "coolerDrawWatts")?,
        bus_w: cfg_real(cfg, "busLoadWatts")?,
        capacity_frames: cfg_int(cfg, "recorderCapacityFrames")?,
    };
    if config.mass_j_per_k <= 0.0 {
        return caller(format!(
            "configuration parameter 'thermalMassJPerK' must be > 0 (got {}); a massless detector \
             has an infinite temperature rate",
            config.mass_j_per_k
        ));
    }
    if config.deadband_k <= 0.0 {
        return caller(format!(
            "configuration parameter 'deadbandKelvin' must be > 0 (got {}); with no deadband the \
             cryocooler switches at every crossing and the run never terminates",
            config.deadband_k
        ));
    }
    for (name, kelvin) in [
        ("initialKelvin", config.initial_k),
        ("setpointKelvin", config.setpoint_k),
    ] {
        if kelvin <= 0.0 {
            return caller(format!(
                "configuration parameter '{name}' must be > 0 K (got {kelvin})"
            ));
        }
    }
    for (name, watts) in [
        ("parasiticWatts", config.parasitic_w),
        ("coolerLiftWatts", config.lift_w),
        ("coolerDrawWatts", config.cooler_draw_w),
        ("busLoadWatts", config.bus_w),
    ] {
        if watts < 0.0 {
            return caller(format!(
                "configuration parameter '{name}' must be >= 0 (got {watts})"
            ));
        }
    }
    if config.capacity_frames < 0 {
        return caller(format!(
            "configuration parameter 'recorderCapacityFrames' must be >= 0 (got {})",
            config.capacity_frames
        ));
    }
    Ok(config)
}

/// An argument `adapter_core` already typechecked against the declared schema. A mismatch here is
/// the host and this file disagreeing about the declaration, not a planner error.
fn arg_int(d: &Directive, name: &str) -> Result<i64, Fault> {
    d.arguments.get(name).and_then(Value::as_i64).ok_or_else(|| {
        Fault::Model(format!(
            "directive {} ({}) argument '{name}' should have arrived as an integer, got {:?}",
            d.id, d.typ, d.arguments.get(name)
        ))
    })
}

fn arg_real(d: &Directive, name: &str) -> Result<f64, Fault> {
    match d.arguments.get(name).and_then(Value::as_f64) {
        Some(v) if v.is_finite() => Ok(v),
        _ => Err(Fault::Model(format!(
            "directive {} ({}) argument '{name}' should have arrived as a finite number, got {:?}",
            d.id, d.typ, d.arguments.get(name)
        ))),
    }
}

fn arg_str(d: &Directive, name: &str) -> Result<String, Fault> {
    d.arguments
        .get(name)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| {
            Fault::Model(format!(
                "directive {} ({}) argument '{name}' should have arrived as a string, got {:?}",
                d.id, d.typ, d.arguments.get(name)
            ))
        })
}

// ---------- the plan ------------------------------------------------------------------------------
/// One directive, resolved against the simulation window.
struct Planned {
    directive: Directive,
    span_id: i64,
    start_us: i64,
    /// What the plan asked for. Zero for `SetCoolerSetpoint`, which has no duration parameter.
    duration_us: i64,
    /// How much of that falls inside the simulated window.
    window_us: i64,
    /// Whether the activity ENDED inside the window. Merlin discriminates a finished span from a
    /// running one by whether it carries a duration, so this is not cosmetic.
    finished: bool,
    /// The temperature a `SetCoolerSetpoint` asked for. `None` for everything else.
    setpoint: Option<f64>,
}

enum Action {
    Instrument(f64),
    Radio(f64),
    Setpoint(f64),
    BeginObservation(String, u64, i64),
    EndObservation,
    BeginDownlink(u64, i64),
}

struct Edge {
    at_us: i64,
    /// 0 for the edges that tear an activity down, 1 for the ones that set the next one up. Two
    /// activities that abut share a microsecond, and the one starting has to win: ordered the other
    /// way, the outgoing activity's "instrument off" lands after the incoming one's "instrument on"
    /// and the payload spends the whole second activity switched off.
    rank: u8,
    seq: usize,
    action: Action,
}

// ---------- simulation ----------------------------------------------------------------------------
pub fn simulate(req: &Request) -> Result<Response, Fault> {
    // `planStart` is deliberately unread. Everything this model reports is an offset from the start
    // of the window, so it never needs an absolute epoch -- which is why the contract makes
    // planStart optional in the first place.
    let sim_us = req.duration;
    let config = configuration(&req.configuration)?;

    let mut planned: Vec<Planned> = Vec::new();
    let mut edges: Vec<Edge> = Vec::new();
    let mut activity_events: i64 = 0;
    let mut next_span_id: i64 = 1;

    for directive in &req.directives {
        if directive.start_offset < 0 {
            return caller(format!(
                "directive {} ({}) starts at {} us, before the beginning of the plan",
                directive.id, directive.typ, directive.start_offset
            ));
        }
        // Past the end of the window there is nothing to simulate and nothing to report; a span
        // for an activity that never ran would show on the timeline as though it had.
        if directive.start_offset > sim_us {
            continue;
        }
        let start_us = directive.start_offset;
        let duration_us = match directive.typ.as_str() {
            decl::SET_SETPOINT => 0,
            _ => arg_int(directive, "duration")?,
        };
        if duration_us < 0 {
            return caller(format!(
                "directive {} ({}) has a duration of {duration_us} us",
                directive.id, directive.typ
            ));
        }
        let window_us = (start_us + duration_us).min(sim_us) - start_us;
        let span_id = next_span_id;
        next_span_id += 1;
        let mut setpoint = None;

        match directive.typ.as_str() {
            decl::OBSERVE | decl::DOWNLINK => {
                let period_us = arg_int(directive, "framePeriod")?;
                if period_us <= 0 {
                    return caller(format!(
                        "directive {} ({}) has a framePeriod of {period_us} us; it must be > 0",
                        directive.id, directive.typ
                    ));
                }
                let watts = arg_real(directive, "powerWatts")?;
                if watts < 0.0 {
                    return caller(format!(
                        "directive {} ({}) draws {watts} W",
                        directive.id, directive.typ
                    ));
                }
                let count = window_us / period_us;
                activity_events += count;
                // A zero-length window is an activity clipped away by the end of the plan, or one
                // the planner gave no duration. It has no edges at all -- emitting the setup and
                // teardown on the same microsecond would leave whichever ran last in effect.
                if window_us > 0 {
                    let (on, off) = if directive.typ == decl::OBSERVE {
                        (Action::Instrument(watts), Action::Instrument(0.0))
                    } else {
                        (Action::Radio(watts), Action::Radio(0.0))
                    };
                    let begin = if directive.typ == decl::OBSERVE {
                        Action::BeginObservation(
                            arg_str(directive, "targetName")?,
                            period_us as u64,
                            count,
                        )
                    } else {
                        Action::BeginDownlink(period_us as u64, count)
                    };
                    push(&mut edges, start_us, 1, on);
                    push(&mut edges, start_us, 1, begin);
                    push(&mut edges, start_us + window_us, 0, off);
                    if directive.typ == decl::OBSERVE {
                        push(&mut edges, start_us + window_us, 0, Action::EndObservation);
                    }
                }
            }
            decl::SET_SETPOINT => {
                let kelvin = arg_real(directive, "setpointKelvin")?;
                if kelvin <= 0.0 {
                    return caller(format!(
                        "directive {} asks for a setpoint of {kelvin} K, which is at or below \
                         absolute zero",
                        directive.id
                    ));
                }
                setpoint = Some(kelvin);
                push(&mut edges, start_us, 1, Action::Setpoint(kelvin));
            }
            other => {
                // adapter_core rejects an unknown activity type before the model is started, so
                // reaching this means the declaration and this match have drifted apart.
                return Err(Fault::Model(format!(
                    "activity type '{other}' is declared but not implemented"
                )));
            }
        }

        planned.push(Planned {
            directive: directive.clone(),
            span_id,
            start_us,
            duration_us,
            window_us,
            finished: start_us + duration_us <= sim_us,
            setpoint,
        });
    }

    refuse_overlaps(&planned, decl::OBSERVE, "instrument points at one target at a time")?;
    refuse_overlaps(&planned, decl::DOWNLINK, "there is one transmitter")?;

    if activity_events > decl::MAX_ACTIVITY_EVENTS {
        return caller(format!(
            "this plan would write and send {activity_events} frames, over the limit of {}; raise \
             'framePeriod' on the activities that are shortest relative to their duration",
            decl::MAX_ACTIVITY_EVENTS
        ));
    }

    // Teardown before setup at the same instant, then by the order the directives arrived, so that
    // two runs of the same plan produce the same event sequence.
    edges.sort_by_key(|e| (e.at_us, e.rank, e.seq));

    // -- the bench ---------------------------------------------------------------------------------
    let epoch = MonotonicTime::EPOCH;
    let cryostat_box = Mailbox::new();
    let recorder_box = Mailbox::new();
    let cryostat = Cryostat::new(&config, epoch, sim_us);
    let recorder = Recorder::new(
        &config,
        epoch,
        UniRequestor::new(Cryostat::peek_kelvin, &cryostat_box),
    );

    // ONE worker thread. With more, the executor is free to interleave the two models' events
    // differently from run to run; a mission model that answers the same plan two ways is not one
    // PlanDev can attest to, and the difference would be far too small to notice by eye.
    let mut bench = SimInit::with_num_threads(1);
    let start = EventSource::new()
        .connect(Cryostat::start, &cryostat_box)
        .register(&mut bench);
    let instrument = EventSource::new()
        .connect(Cryostat::set_instrument_watts, &cryostat_box)
        .register(&mut bench);
    let radio = EventSource::new()
        .connect(Cryostat::set_radio_watts, &cryostat_box)
        .register(&mut bench);
    let setpoint = EventSource::new()
        .connect(Cryostat::set_setpoint, &cryostat_box)
        .register(&mut bench);
    let begin_observation = EventSource::new()
        .connect(Recorder::begin_observation, &recorder_box)
        .register(&mut bench);
    let end_observation = EventSource::new()
        .connect(Recorder::end_observation, &recorder_box)
        .register(&mut bench);
    let begin_downlink = EventSource::new()
        .connect(Recorder::begin_downlink, &recorder_box)
        .register(&mut bench);
    let thermal_history = QuerySource::new()
        .connect(Cryostat::history, &cryostat_box)
        .register(&mut bench);
    let recorder_history = QuerySource::new()
        .connect(Recorder::history, &recorder_box)
        .register(&mut bench);

    let mut simu = bench
        .add_model(cryostat, cryostat_box, "cryostat")
        .add_model(recorder, recorder_box, "recorder")
        .init(epoch)
        .map_err(|e| Fault::Model(format!("could not initialize the simulation: {e}")))?;

    let fail = |e: nexosim::simulation::ExecutionError| {
        Fault::Model(format!("the simulation could not be run: {e}"))
    };
    simu.process_event(&start, ()).map_err(fail)?;

    // The scheduler refuses a deadline that is not in the future, so an effect at t=0 is PROCESSED
    // instead of scheduled. Same instant, same relative order.
    for edge in edges.iter().filter(|e| e.at_us == 0) {
        match &edge.action {
            Action::Instrument(w) => simu.process_event(&instrument, *w),
            Action::Radio(w) => simu.process_event(&radio, *w),
            Action::Setpoint(k) => simu.process_event(&setpoint, *k),
            Action::BeginObservation(t, p, n) => {
                simu.process_event(&begin_observation, (t.clone(), *p, *n))
            }
            Action::EndObservation => simu.process_event(&end_observation, ()),
            Action::BeginDownlink(p, n) => simu.process_event(&begin_downlink, (*p, *n)),
        }
        .map_err(fail)?;
    }

    let scheduler = simu.scheduler();
    for edge in edges.iter().filter(|e| e.at_us > 0) {
        let at = epoch + Duration::from_micros(edge.at_us as u64);
        match &edge.action {
            Action::Instrument(w) => scheduler.schedule_event(at, &instrument, *w),
            Action::Radio(w) => scheduler.schedule_event(at, &radio, *w),
            Action::Setpoint(k) => scheduler.schedule_event(at, &setpoint, *k),
            Action::BeginObservation(t, p, n) => {
                scheduler.schedule_event(at, &begin_observation, (t.clone(), *p, *n))
            }
            Action::EndObservation => scheduler.schedule_event(at, &end_observation, ()),
            Action::BeginDownlink(p, n) => scheduler.schedule_event(at, &begin_downlink, (*p, *n)),
        }
        .map_err(|e| {
            Fault::Model(format!(
                "could not schedule an edge at {} us: {e}",
                edge.at_us
            ))
        })?;
    }

    if sim_us > 0 {
        simu.step_until(epoch + Duration::from_micros(sim_us as u64))
            .map_err(fail)?;
    }
    let clock_us = simu.time().duration_since(epoch).as_micros() as i64;
    if clock_us != sim_us {
        // step_until documents that it lands exactly on the deadline. If it ever does not, every
        // profile below is short by the difference and merlin's gate rejects the lot with no
        // explanation; better to say so here.
        return Err(Fault::Model(format!(
            "the simulation stopped at {clock_us} us instead of {sim_us} us"
        )));
    }

    let (thermal, chattered) = simu.process_query(&thermal_history, ()).map_err(fail)?;
    let recorded: Vec<RecorderRow> = simu.process_query(&recorder_history, ()).map_err(fail)?;
    if chattered {
        return caller(format!(
            "the cryocooler switched more than {} times; raise 'deadbandKelvin' or lower the heat \
             into the detector",
            decl::MAX_COOLER_SWITCHES
        ));
    }

    Ok(Response {
        real_profiles: real_profiles(&thermal, sim_us)?,
        discrete_profiles: discrete_profiles(&thermal, &recorded, sim_us)?,
        spans: spans(&planned, &thermal, &recorded, config.setpoint_k)?,
    })
}

fn push(edges: &mut Vec<Edge>, at_us: i64, rank: u8, action: Action) {
    let seq = edges.len();
    edges.push(Edge {
        at_us,
        rank,
        seq,
        action,
    });
}

/// Refuses two activities of one type whose windows overlap.
///
/// Not a general rule about activities -- an Observe and a Downlink overlapping is ordinary, and
/// their loads add. It is a rule about SHARED HARDWARE: two observations at once would have to
/// choose one of two target names for `/instrument/target`, and whichever the model picked would be
/// recorded as though the plan had said so.
fn refuse_overlaps(planned: &[Planned], typ: &str, why: &str) -> Result<(), Fault> {
    let mut windows: Vec<(i64, i64, &Value)> = planned
        .iter()
        .filter(|p| p.directive.typ == typ && p.window_us > 0)
        .map(|p| (p.start_us, p.start_us + p.window_us, &p.directive.id))
        .collect();
    windows.sort_by_key(|w| w.0);
    for pair in windows.windows(2) {
        if pair[1].0 < pair[0].1 {
            return caller(format!(
                "directives {} and {} are overlapping {typ} activities, and {why}",
                pair[0].2, pair[1].2
            ));
        }
    }
    Ok(())
}

// ---------- samples -> segments ---------------------------------------------------------------------
/// Linear segments from a temperature history, covering [0, sim_us] exactly.
///
/// RATE IS THE SECANT between consecutive rows, never the model's instantaneous derivative. PlanDev
/// evaluates a real profile as `initial + rate * elapsedSeconds`, so a segment's computed end value
/// has to equal the next segment's `initial`. Here the two happen to agree -- the heat balance is
/// constant between events, so the temperature really is linear across each row pair -- but writing
/// the derivative would put that agreement at the mercy of the model, and the first saturating or
/// nonlinear channel added later would break it silently.
fn ramp_segments(times: &[i64], values: &[f64], sim_us: i64) -> Vec<(i64, f64, f64)> {
    let mut out = Vec::new();
    for i in 0..times.len().saturating_sub(1) {
        let span_us = times[i + 1] - times[i];
        let rate = (values[i + 1] - values[i]) / (span_us as f64 / 1e6);
        out.push((span_us, values[i], rate));
    }
    // Close the window. The last row is at the last EVENT, which is generally not the end of the
    // plan, and merlin's ingest gate rejects a profile that does not cover the simulation. Held
    // flat: past the final row there is no data and a hold is the only statement that invents none.
    if let (Some(&last_t), Some(&last_v)) = (times.last(), values.last()) {
        if sim_us > last_t {
            out.push((sim_us - last_t, last_v, 0.0));
        }
    }
    coalesce_real(out)
}

/// Segments from a step function -- a value that JUMPS at each row rather than ramping to the next.
/// Feeding electrical load through `ramp_segments` would slope it between two steady levels, which
/// on a chart is a load that does not exist.
fn held_segments(times: &[i64], values: &[f64], sim_us: i64) -> Vec<(i64, f64, f64)> {
    let mut out = Vec::new();
    for i in 0..times.len().saturating_sub(1) {
        out.push((times[i + 1] - times[i], values[i], 0.0));
    }
    if let (Some(&last_t), Some(&last_v)) = (times.last(), values.last()) {
        if sim_us > last_t {
            out.push((sim_us - last_t, last_v, 0.0));
        }
    }
    coalesce_real(out)
}

/// Merges adjacent FLAT segments holding the same value.
///
/// Restricted to `rate == 0` deliberately. A zero-rate segment evaluates to its `initial`
/// everywhere, so merging two with a bit-identical initial is exactly equivalent. Merging sloped
/// ones would assert that `i + r*(d1+d2) == i + r*d1 + r*d2`, which floating-point addition does not
/// guarantee.
fn coalesce_real(segments: Vec<(i64, f64, f64)>) -> Vec<(i64, f64, f64)> {
    let mut out: Vec<(i64, f64, f64)> = Vec::new();
    for segment in segments {
        match out.last_mut() {
            Some(previous) if previous.2 == 0.0 && segment.2 == 0.0 && previous.1 == segment.1 => {
                previous.0 += segment.0;
            }
            _ => out.push(segment),
        }
    }
    out
}

fn real_profile(segments: Vec<(i64, f64, f64)>, name: &str) -> Result<Profile, Fault> {
    let mut out = Vec::with_capacity(segments.len());
    let mut at_us = 0i64;
    for (duration, initial, rate) in segments {
        out.push(Segment {
            duration,
            dynamics: ramp(initial, rate, &format!("resource '{name}' at {at_us} us"))?,
        });
        at_us += duration;
    }
    Ok(Profile {
        schema: json!({"type": "real"}),
        segments: out,
    })
}

/// Piecewise-constant segments, coalesced. Exact by definition, and the difference between a target
/// profile of a few entries and one of fifty thousand.
fn discrete_profile(
    times: &[i64],
    values: Vec<Value>,
    sim_us: i64,
    schema: Value,
) -> Result<Profile, Fault> {
    let mut segments: Vec<Segment> = Vec::new();
    let mut push = |duration: i64, dynamics: Value| match segments.last_mut() {
        Some(last) if last.dynamics == dynamics => last.duration += duration,
        _ => segments.push(Segment { duration, dynamics }),
    };
    for i in 0..times.len().saturating_sub(1) {
        push(times[i + 1] - times[i], values[i].clone());
    }
    if let (Some(&last_t), Some(last_v)) = (times.last(), values.last()) {
        if sim_us > last_t {
            push(sim_us - last_t, last_v.clone());
        }
    }
    Ok(Profile { schema, segments })
}

fn real_profiles(
    thermal: &[ThermalRow],
    sim_us: i64,
) -> Result<BTreeMap<String, Profile>, Fault> {
    let times: Vec<i64> = thermal.iter().map(|r| r.at_us).collect();
    let kelvin: Vec<f64> = thermal.iter().map(|r| r.kelvin).collect();
    let load: Vec<f64> = thermal.iter().map(|r| r.load_w).collect();
    let mut out = BTreeMap::new();
    out.insert(
        decl::R_KELVIN.to_string(),
        real_profile(ramp_segments(&times, &kelvin, sim_us), decl::R_KELVIN)?,
    );
    out.insert(
        decl::R_LOAD.to_string(),
        real_profile(held_segments(&times, &load, sim_us), decl::R_LOAD)?,
    );
    Ok(out)
}

fn discrete_profiles(
    thermal: &[ThermalRow],
    recorded: &[RecorderRow],
    sim_us: i64,
) -> Result<BTreeMap<String, Profile>, Fault> {
    let thermal_times: Vec<i64> = thermal.iter().map(|r| r.at_us).collect();
    let recorder_times: Vec<i64> = recorded.iter().map(|r| r.at_us).collect();
    let mut out = BTreeMap::new();

    out.insert(
        decl::R_COOLER.to_string(),
        discrete_profile(
            &thermal_times,
            thermal
                .iter()
                .map(|r| json!(if r.cooling { decl::COOLER_ON } else { decl::COOLER_OFF }))
                .collect(),
            sim_us,
            json!({"type": "variant", "variants": [
                {"key": decl::COOLER_OFF, "label": decl::COOLER_OFF},
                {"key": decl::COOLER_ON, "label": decl::COOLER_ON}]}),
        )?,
    );
    out.insert(
        decl::R_FRAMES.to_string(),
        discrete_profile(
            &recorder_times,
            // int(), not real(). A count widened to f64 arrives as `2.0` and merlin's asInt()
            // rejects the profile at ingest, hours of simulation later.
            recorded.iter().map(|r| int(r.frames)).collect(),
            sim_us,
            json!({"type": "int"}),
        )?,
    );
    out.insert(
        decl::R_TARGET.to_string(),
        discrete_profile(
            &recorder_times,
            recorded.iter().map(|r| json!(r.target)).collect(),
            sim_us,
            json!({"type": "string"}),
        )?,
    );
    let mut newest = Vec::with_capacity(recorded.len());
    for row in recorded {
        // A struct is CLOSED: exactly these three fields, no more and no fewer, or merlin's gate
        // rejects the value against the declared schema.
        newest.push(json!({
            "frameId": int(row.newest.id),
            "target": row.newest.target,
            "detectorKelvin": real(
                row.newest.kelvin,
                &format!("resource '{}' at {} us", decl::R_NEWEST, row.at_us))?,
        }));
    }
    out.insert(
        decl::R_NEWEST.to_string(),
        discrete_profile(
            &recorder_times,
            newest,
            sim_us,
            json!({"type": "struct", "items": {
                "frameId": {"type": "int"},
                "target": {"type": "string"},
                "detectorKelvin": {"type": "real"}}}),
        )?,
    );
    Ok(out)
}

// ---------- spans -----------------------------------------------------------------------------------
/// The temperature at an arbitrary instant, read off the profile the way PlanDev would read it.
///
/// Interpolated along the same secant the segment carries, rather than recomputed from the heat
/// balance: a computed attribute that disagreed with the chart it was derived from would be a
/// discrepancy with nowhere to look.
fn kelvin_at(rows: &[ThermalRow], t: i64) -> f64 {
    if rows.is_empty() {
        return 0.0;
    }
    let i = match rows.binary_search_by_key(&t, |r| r.at_us) {
        Ok(i) => i,
        Err(0) => 0,
        Err(i) => i - 1,
    };
    if i + 1 >= rows.len() {
        return rows[i].kelvin;
    }
    let (a, b) = (&rows[i], &rows[i + 1]);
    let span = (b.at_us - a.at_us) as f64;
    if span <= 0.0 {
        return a.kelvin;
    }
    a.kelvin + (b.kelvin - a.kelvin) * ((t - a.at_us) as f64 / span)
}

/// The warmest the detector got over a window. Piecewise linear, so the maximum is at one of the
/// window's ends or at a row inside it -- there is nothing to sample and nothing to miss.
fn peak_kelvin(rows: &[ThermalRow], from: i64, to: i64) -> f64 {
    let mut peak = kelvin_at(rows, from).max(kelvin_at(rows, to));
    for row in rows.iter().filter(|r| r.at_us > from && r.at_us < to) {
        peak = peak.max(row.kelvin);
    }
    peak
}

fn counter_at(rows: &[RecorderRow], t: i64, pick: fn(&RecorderRow) -> i64) -> i64 {
    rows.iter().rev().find(|r| r.at_us <= t).map(pick).unwrap_or(0)
}

fn spans(
    planned: &[Planned],
    thermal: &[ThermalRow],
    recorded: &[RecorderRow],
    configured_setpoint: f64,
) -> Result<Vec<Span>, Fault> {
    let previous_setpoint = previous_setpoints(planned, configured_setpoint);
    let mut out = Vec::with_capacity(planned.len());
    for plan in planned {
        let directive = &plan.directive;
        let span = Span::running(
            plan.span_id,
            directive.id.clone(),
            &directive.typ,
            plan.start_us,
            directive.arguments.clone(),
        );
        if !plan.finished {
            // Neither duration nor computedAttributes: an activity still running when the window
            // closed has not produced its final values, and merlin reads a span carrying them with
            // no duration as finished-with-no-end.
            out.push(span);
            continue;
        }
        let (from, to) = (plan.start_us, plan.start_us + plan.window_us);
        let mut computed = Map::new();
        match directive.typ.as_str() {
            decl::OBSERVE => {
                computed.insert(
                    "framesWritten".into(),
                    int(counter_at(recorded, to, |r| r.written)
                        - counter_at(recorded, from, |r| r.written)),
                );
                computed.insert(
                    "framesDropped".into(),
                    int(counter_at(recorded, to, |r| r.dropped)
                        - counter_at(recorded, from, |r| r.dropped)),
                );
                computed.insert(
                    "peakDetectorKelvin".into(),
                    real(
                        peak_kelvin(thermal, from, to),
                        &format!("span {} peakDetectorKelvin", plan.span_id),
                    )?,
                );
            }
            decl::DOWNLINK => {
                computed.insert(
                    "framesSent".into(),
                    int(counter_at(recorded, to, |r| r.sent)
                        - counter_at(recorded, from, |r| r.sent)),
                );
                computed.insert(
                    "framesRemaining".into(),
                    int(counter_at(recorded, to, |r| r.frames)),
                );
            }
            decl::SET_SETPOINT => {
                computed.insert(
                    "previousSetpointKelvin".into(),
                    real(
                        previous_setpoint
                            .get(&plan.span_id)
                            .copied()
                            .unwrap_or(configured_setpoint),
                        &format!("span {} previousSetpointKelvin", plan.span_id),
                    )?,
                );
            }
            _ => {}
        }
        out.push(span.finished(plan.duration_us, computed));
    }
    Ok(out)
}

/// What each retune replaced, by span id.
///
/// Resolved by START TIME, with ties broken the same way the event queue breaks them, rather than
/// by position in the request: merlin serializes directives in whatever order it read them out of
/// the plan, so the last one in the list is not necessarily the last one to happen.
fn previous_setpoints(planned: &[Planned], configured: f64) -> BTreeMap<i64, f64> {
    let mut retunes: Vec<(i64, i64, f64)> = planned
        .iter()
        .filter_map(|p| p.setpoint.map(|k| (p.start_us, p.span_id, k)))
        .collect();
    retunes.sort_by_key(|r| (r.0, r.1));
    let mut out = BTreeMap::new();
    let mut previous = configured;
    for (_, span_id, kelvin) in retunes {
        out.insert(span_id, previous);
        previous = kelvin;
    }
    out
}

// ---------- validate ----------------------------------------------------------------------------------
/// The model-specific half of `/validate`: the checks no ValueSchema can express.
///
/// A third verb, which `ExecBackend` does not define. Without it a model in another process has no
/// way to answer `/validate` beyond what the declaration alone says, so every semantic mistake --
/// a frame period that would flood the recorder, a setpoint below absolute zero -- goes unreported
/// until someone runs the plan.
pub fn validate(subjects: &[crate::wire::ValidateSubject]) -> Value {
    let mut out = Vec::with_capacity(subjects.len());
    for subject in subjects {
        let mut notices: Vec<Value> = Vec::new();
        let args = &subject.arguments;
        let note = |notices: &mut Vec<Value>, subjects: &[&str], message: String| {
            notices.push(json!({"subjects": subjects, "message": message}));
        };
        // Anything the generic layer already rejected on TYPE is read as absent here: it has
        // reported that notice itself, and a second complaint about the same field is noise.
        let duration = args.get("duration").and_then(Value::as_i64);
        let period = args.get("framePeriod").and_then(Value::as_i64);
        let watts = args.get("powerWatts").and_then(Value::as_f64);

        if let Some(d) = duration {
            if d < 0 {
                note(&mut notices, &["duration"], format!("'duration' must be >= 0 (got {d})"));
            }
        }
        if let Some(p) = period {
            if p <= 0 {
                note(
                    &mut notices,
                    &["framePeriod"],
                    format!("'framePeriod' must be > 0 us (got {p})"),
                );
            }
        }
        if let Some(w) = watts {
            if w < 0.0 {
                note(
                    &mut notices,
                    &["powerWatts"],
                    format!("'powerWatts' must be >= 0 (got {w})"),
                );
            }
        }
        if let (Some(d), Some(p)) = (duration, period) {
            if d >= 0 && p > 0 && d / p > decl::MAX_ACTIVITY_EVENTS {
                note(
                    &mut notices,
                    &["duration", "framePeriod"],
                    format!(
                        "this would move {} frames, over the per-plan limit of {}; raise \
                         'framePeriod'",
                        d / p,
                        decl::MAX_ACTIVITY_EVENTS
                    ),
                );
            }
        }
        if subject.typ == decl::OBSERVE {
            if let Some(name) = args.get("targetName").and_then(Value::as_str) {
                if name.trim().is_empty() {
                    note(
                        &mut notices,
                        &["targetName"],
                        "'targetName' is what the recorder stamps on every frame; it cannot be \
                         blank"
                            .to_string(),
                    );
                }
            }
        }
        if subject.typ == decl::SET_SETPOINT {
            if let Some(k) = args.get("setpointKelvin").and_then(Value::as_f64) {
                if k <= 0.0 {
                    note(
                        &mut notices,
                        &["setpointKelvin"],
                        format!("'setpointKelvin' must be > 0 K (got {k})"),
                    );
                }
            }
        }
        out.push(Value::Array(notices));
    }
    json!({ "notices": out })
}
