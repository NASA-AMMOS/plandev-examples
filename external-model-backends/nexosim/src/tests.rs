//! Tests for the parts of this model that nothing else would catch.
//!
//! The generic half of the contract -- routing, defaults, the ValueSchema typechecker, the identity
//! hash, response validation -- belongs to `adapter_core` and is covered by
//! `../test_adapter_core.py`. The declaration as the HOST parses it is covered by
//! `test_nx_service.py`, which is also where the across-process checks live, because a Rust unit
//! test runs in one process and the failure mode it would have to catch is a `HashMap` reordering
//! itself between two.
//!
//! What is left is the model and the timeline, and it is where this adapter can be wrong in ways
//! nothing downstream would flag:
//!
//!   * WINDOW CLOSURE AND CONTINUITY. PlanDev evaluates a real profile as
//!     `initial + rate * elapsed`. A segment whose computed end misses the next segment's `initial`
//!     is a profile that contradicts itself, and nothing raises anything.
//!   * PLACEMENT. Activity edges land on exact microseconds and the cryocooler switches at instants
//!     no plan contains. Both have to appear as segment boundaries where they actually happened.
//!   * ATTRIBUTION. Computed attributes are counter differences across a span's own window, and a
//!     plan with two observations of the same target is where a sloppier scheme starts double
//!     counting.
//!   * THE THREE RUST HAZARDS -- a NaN that serializes as `null`, a count widened to a float, and a
//!     map that reorders itself.

use crate::decl;
use crate::run;
use crate::wire::{Directive, Profile, Request, Response, Span};
use serde_json::{Map, Value, json};

const US: i64 = 1_000_000;

// ---------- building a request the host could actually have sent ------------------------------------
/// The configuration as `adapter_core.effective_config` would resolve it: every declared parameter
/// present, defaults filled, overrides applied. A test that hand-rolled a partial map would be
/// exercising a request the host cannot produce.
fn config(overrides: Value) -> Map<String, Value> {
    let mut out = Map::new();
    for p in decl::declaration()["parameters"].as_array().unwrap() {
        out.insert(
            p["name"].as_str().unwrap().to_string(),
            p["default"].clone(),
        );
    }
    if let Value::Object(o) = overrides {
        out.extend(o);
    }
    out
}

/// A directive as `adapter_core.effective_args` would hand it over: declared names only, defaults
/// filled in.
fn directive(id: i64, typ: &str, start_us: i64, args: Value) -> Directive {
    let mut arguments = Map::new();
    for a in decl::declaration()["activityTypes"].as_array().unwrap() {
        if a["name"] == typ {
            for p in a["parameters"].as_array().unwrap() {
                if let Some(default) = p.get("default") {
                    arguments.insert(p["name"].as_str().unwrap().to_string(), default.clone());
                }
            }
        }
    }
    if let Value::Object(o) = args {
        arguments.extend(o);
    }
    Directive {
        id: json!(id),
        typ: typ.to_string(),
        start_offset: start_us,
        arguments,
    }
}

fn request(duration_us: i64, directives: Vec<Directive>, overrides: Value) -> Request {
    Request {
        plan_start: Some("2026-07-27T00:00:00Z".into()),
        duration: duration_us,
        configuration: config(overrides),
        directives,
    }
}

fn run(duration_us: i64, directives: Vec<Directive>, overrides: Value) -> Response {
    run::simulate(&request(duration_us, directives, overrides)).expect("simulate")
}

fn refusal(duration_us: i64, directives: Vec<Directive>, overrides: Value) -> String {
    run::simulate(&request(duration_us, directives, overrides))
        .expect_err("expected a refusal")
        .message()
        .to_string()
}

fn profile<'a>(response: &'a Response, name: &str) -> &'a Profile {
    response
        .real_profiles
        .get(name)
        .or_else(|| response.discrete_profiles.get(name))
        .unwrap_or_else(|| panic!("no profile for {name}"))
}

fn total_duration(profile: &Profile) -> i64 {
    profile.segments.iter().map(|s| s.duration).sum()
}

/// Segment boundaries, as absolute microseconds.
fn boundaries(profile: &Profile) -> Vec<i64> {
    let mut at = 0;
    let mut out = vec![0];
    for segment in &profile.segments {
        at += segment.duration;
        out.push(at);
    }
    out
}

/// A real profile evaluated the way PlanDev evaluates it.
fn value_at(profile: &Profile, t: i64) -> f64 {
    let mut at = 0i64;
    for segment in &profile.segments {
        if t < at + segment.duration {
            let initial = segment.dynamics["initial"].as_f64().unwrap();
            let rate = segment.dynamics["rate"].as_f64().unwrap();
            return initial + rate * ((t - at) as f64 / 1e6);
        }
        at += segment.duration;
    }
    let last = profile.segments.last().unwrap();
    last.dynamics["initial"].as_f64().unwrap()
        + last.dynamics["rate"].as_f64().unwrap() * (last.duration as f64 / 1e6)
}

/// The discrete value in force at `t`.
fn discrete_at(profile: &Profile, t: i64) -> &Value {
    let mut at = 0i64;
    for segment in &profile.segments {
        if t < at + segment.duration {
            return &segment.dynamics;
        }
        at += segment.duration;
    }
    &profile.segments.last().unwrap().dynamics
}

fn span(response: &Response, span_id: i64) -> &Span {
    response
        .spans
        .iter()
        .find(|s| s.span_id == span_id)
        .expect("span")
}

// ---------- the window ------------------------------------------------------------------------------
#[test]
fn every_profile_covers_the_whole_window_to_the_microsecond() {
    // Merlin's ingest gate rejects a profile that does not span the simulation. The failure is easy
    // to introduce and impossible to see: the last event is never the end of the plan, so a
    // conversion that stops at the last event is short by whatever was left over.
    let sim_us = 2 * 3600 * US + 123; // deliberately not a round number
    let response = run(
        sim_us,
        vec![directive(
            1,
            decl::OBSERVE,
            900 * US,
            json!({"duration": 600 * US}),
        )],
        json!({}),
    );
    for name in [
        decl::R_KELVIN,
        decl::R_LOAD,
        decl::R_COOLER,
        decl::R_FRAMES,
        decl::R_NEWEST,
        decl::R_TARGET,
    ] {
        assert_eq!(total_duration(profile(&response, name)), sim_us, "{name}");
    }
}

#[test]
fn each_temperature_segment_ends_exactly_where_the_next_one_begins() {
    // The secant rule. PlanDev computes a segment's end as `initial + rate * elapsed`; if that
    // misses the next segment's `initial`, the chart has a step in it the detector never took, and
    // no check anywhere in PlanDev looks for one.
    //
    // Only the temperature. /power/loadWatts is a step function and its segments are SUPPOSED to
    // disagree across a boundary -- that is what a load switching on looks like -- so holding it to
    // the same rule would be asserting that the cryocooler draws its 55 W gradually.
    let response = run(
        4 * 3600 * US + 7,
        vec![
            directive(1, decl::OBSERVE, 600 * US, json!({"duration": 1800 * US})),
            directive(2, decl::DOWNLINK, 3000 * US, json!({"duration": 600 * US})),
        ],
        json!({}),
    );
    let kelvin = profile(&response, decl::R_KELVIN);
    assert!(kelvin.segments.len() > 10);
    for pair in kelvin.segments.windows(2) {
        let end = pair[0].dynamics["initial"].as_f64().unwrap()
            + pair[0].dynamics["rate"].as_f64().unwrap() * (pair[0].duration as f64 / 1e6);
        let next = pair[1].dynamics["initial"].as_f64().unwrap();
        assert!((end - next).abs() < 1e-9, "{end} != {next}");
    }
}

#[test]
fn an_activity_edge_lands_on_the_microsecond_the_plan_asked_for() {
    // The whole argument for a discrete-event backend over a fixed-step one. A fixed-step simulator
    // has to snap this to its grid, and then the timeline and the profile disagree by up to a step
    // with nothing to explain the gap.
    let start = 1_234_567;
    let response = run(
        10 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            start,
            json!({"duration": 3 * US}),
        )],
        json!({}),
    );
    let edges = boundaries(profile(&response, decl::R_KELVIN));
    assert!(edges.contains(&start), "{edges:?}");
    assert!(edges.contains(&(start + 3 * US)), "{edges:?}");
    assert_eq!(span(&response, 1).start_offset, start);
}

#[test]
fn the_cryocooler_switches_at_instants_no_plan_contains() {
    // The behaviour PlanDev cannot express, and the reason the model is worth running at all. A
    // controller that was never re-armed would produce one long segment, which looks entirely
    // plausible.
    let response = run(4 * 3600 * US, vec![], json!({}));
    let cooler = profile(&response, decl::R_COOLER);
    let states: Vec<&str> = cooler
        .segments
        .iter()
        .map(|s| s.dynamics.as_str().unwrap())
        .collect();
    assert!(states.len() > 4, "{states:?}");
    assert!(states.contains(&decl::COOLER_ON) && states.contains(&decl::COOLER_OFF));
    // The detector starts above setpoint + deadband, so the very first segment is already cooling:
    // a controller that only settled on the first activity edge would open with a plateau instead.
    assert_eq!(states[0], decl::COOLER_ON);
    // and the temperature stays inside the band it is controlling to, once it has arrived.
    let kelvin = profile(&response, decl::R_KELVIN);
    for t in (600 * US..4 * 3600 * US).step_by(60 * US as usize) {
        let k = value_at(kelvin, t);
        assert!(
            (87.9..92.1).contains(&k),
            "at {t} us the detector was {k} K"
        );
    }
}

// ---------- placement and attribution -----------------------------------------------------------------
#[test]
fn an_observation_of_exactly_n_frame_periods_writes_n_frames() {
    // The boundary case, and the one that must not be decided by queue order: the fifth frame lands
    // on the same microsecond as the end of the observation.
    let response = run(
        120 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            10 * US,
            json!({"duration": 50 * US, "framePeriod": 10 * US}),
        )],
        json!({}),
    );
    let computed = span(&response, 1).computed_attributes.as_ref().unwrap();
    assert_eq!(computed["framesWritten"], json!(5));
    assert_eq!(computed["framesDropped"], json!(0));
}

#[test]
fn frames_are_attributed_to_the_observation_that_wrote_them() {
    // Two observations of the SAME target, which is where counting log rows by target -- the
    // obvious implementation -- starts giving each span the other's frames as well.
    let response = run(
        200 * US,
        vec![
            directive(
                1,
                decl::OBSERVE,
                0,
                json!({"duration": 30 * US, "framePeriod": 10 * US,
                                                  "targetName": "M31"}),
            ),
            directive(
                2,
                decl::OBSERVE,
                100 * US,
                json!({"duration": 70 * US,
                                                         "framePeriod": 10 * US,
                                                         "targetName": "M31"}),
            ),
        ],
        json!({}),
    );
    assert_eq!(
        span(&response, 1).computed_attributes.as_ref().unwrap()["framesWritten"],
        json!(3)
    );
    assert_eq!(
        span(&response, 2).computed_attributes.as_ref().unwrap()["framesWritten"],
        json!(7)
    );
}

#[test]
fn a_span_that_outlives_the_window_carries_neither_duration_nor_computed_attributes() {
    // Merlin discriminates a finished span from a running one by their presence, so an activity cut
    // off by the end of the plan that reported them would be stored as having completed.
    let response = run(
        60 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            30 * US,
            json!({"duration": 600 * US}),
        )],
        json!({}),
    );
    let span = span(&response, 1);
    assert!(span.duration.is_none());
    assert!(span.computed_attributes.is_none());
}

#[test]
fn a_directive_that_starts_after_the_window_is_not_reported_at_all() {
    // A span for an activity that never ran shows on the timeline exactly like one that did.
    let response = run(
        60 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            90 * US,
            json!({"duration": 10 * US}),
        )],
        json!({}),
    );
    assert!(response.spans.is_empty(), "{:?}", response.spans);
}

#[test]
fn an_instantaneous_retune_reports_the_setpoint_it_replaced() {
    // An activity with no `duration` parameter at all, which is the case an adapter that assumes
    // one only discovers on a real mission model.
    let response = run(
        600 * US,
        vec![
            directive(
                1,
                decl::SET_SETPOINT,
                100 * US,
                json!({"setpointKelvin": 80.0}),
            ),
            directive(
                2,
                decl::SET_SETPOINT,
                200 * US,
                json!({"setpointKelvin": 70.0}),
            ),
        ],
        json!({}),
    );
    assert_eq!(span(&response, 1).duration, Some(0));
    assert_eq!(
        span(&response, 1).computed_attributes.as_ref().unwrap()["previousSetpointKelvin"],
        json!(90.0)
    );
    assert_eq!(
        span(&response, 2).computed_attributes.as_ref().unwrap()["previousSetpointKelvin"],
        json!(80.0)
    );
}

#[test]
fn the_target_resource_follows_the_plan_and_goes_back_to_empty() {
    let response = run(
        300 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            100 * US,
            json!({"duration": 100 * US,
                                                          "targetName": "M31"}),
        )],
        json!({}),
    );
    let target = profile(&response, decl::R_TARGET);
    assert_eq!(discrete_at(target, 50 * US), &json!(""));
    assert_eq!(discrete_at(target, 150 * US), &json!("M31"));
    assert_eq!(discrete_at(target, 250 * US), &json!(""));
}

// ---------- the recorder ------------------------------------------------------------------------------
#[test]
fn the_newest_frame_carries_the_temperature_at_the_instant_it_was_exposed() {
    // The reason the recorder asks the cryostat over a requestor port rather than caching whatever
    // the cryostat last broadcast. Between thermal events the detector is RAMPING, so a cached
    // value is stale by however long ago the last event was -- minutes, in a quiet stretch -- and
    // every frame in that stretch carries the same wrong number, which looks like a stable detector.
    let response = run(
        3600 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            0,
            json!({"duration": 3000 * US,
                                                   "framePeriod": 1000 * US}),
        )],
        json!({}),
    );
    let kelvin = profile(&response, decl::R_KELVIN);
    let newest = profile(&response, decl::R_NEWEST);
    let stamped = discrete_at(newest, 2500 * US)["detectorKelvin"]
        .as_f64()
        .unwrap();
    // The frame in force at 2500 s is the one written at 2000 s, and the temperature profile says
    // what the detector was at 2000 s.
    let expected = value_at(kelvin, 2000 * US);
    assert!(
        (stamped - expected).abs() < 1e-9,
        "frame says {stamped}, profile says {expected}"
    );
    // and it is NOT the temperature at the previous thermal event, which is what a cached broadcast
    // would have supplied.
    assert!((stamped - value_at(kelvin, 0)).abs() > 1.0);
}

#[test]
fn the_recorder_saturates_at_capacity_instead_of_growing_without_bound() {
    let response = run(
        200 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            0,
            json!({"duration": 100 * US,
                                                   "framePeriod": 10 * US}),
        )],
        json!({"recorderCapacityFrames": 3}),
    );
    let computed = span(&response, 1).computed_attributes.as_ref().unwrap();
    assert_eq!(computed["framesWritten"], json!(3));
    assert_eq!(computed["framesDropped"], json!(7));
    let frames = profile(&response, decl::R_FRAMES);
    assert_eq!(
        frames
            .segments
            .iter()
            .map(|s| s.dynamics.as_i64().unwrap())
            .max(),
        Some(3)
    );
}

#[test]
fn a_downlink_cannot_send_frames_that_are_not_there() {
    // Saturating at zero rather than going negative. A negative frame count renders as a perfectly
    // plausible line on a chart, and the bug that produced it is a subtraction three files away.
    let response = run(
        200 * US,
        vec![directive(
            1,
            decl::DOWNLINK,
            0,
            json!({"duration": 100 * US,
                                                    "framePeriod": 10 * US}),
        )],
        json!({}),
    );
    let computed = span(&response, 1).computed_attributes.as_ref().unwrap();
    assert_eq!(computed["framesSent"], json!(0));
    assert_eq!(computed["framesRemaining"], json!(0));
}

#[test]
fn a_downlink_drains_what_an_earlier_observation_wrote() {
    let response = run(
        400 * US,
        vec![
            directive(
                1,
                decl::OBSERVE,
                0,
                json!({"duration": 100 * US, "framePeriod": 10 * US}),
            ),
            directive(
                2,
                decl::DOWNLINK,
                200 * US,
                json!({"duration": 40 * US,
                                                          "framePeriod": 10 * US}),
            ),
        ],
        json!({}),
    );
    let computed = span(&response, 2).computed_attributes.as_ref().unwrap();
    assert_eq!(computed["framesSent"], json!(4));
    assert_eq!(computed["framesRemaining"], json!(6));
}

// ---------- shared hardware ----------------------------------------------------------------------------
#[test]
fn overlapping_observations_are_refused_and_the_message_names_both() {
    // The instrument points at one target at a time, so two at once would have to pick one of the
    // two names for /instrument/target -- and whichever it picked would be recorded as though the
    // plan had said so.
    let message = refusal(
        1000 * US,
        vec![
            directive(7, decl::OBSERVE, 0, json!({"duration": 500 * US})),
            directive(9, decl::OBSERVE, 400 * US, json!({"duration": 100 * US})),
        ],
        json!({}),
    );
    assert!(message.contains('7') && message.contains('9'), "{message}");
}

#[test]
fn two_observations_that_merely_abut_are_allowed() {
    // The off-by-one a naive overlap check gets wrong, which would refuse an ordinary back-to-back
    // pair of observations.
    let response = run(
        1000 * US,
        vec![
            directive(
                1,
                decl::OBSERVE,
                0,
                json!({"duration": 400 * US, "targetName": "A"}),
            ),
            directive(
                2,
                decl::OBSERVE,
                400 * US,
                json!({"duration": 400 * US,
                                                         "targetName": "B"}),
            ),
        ],
        json!({}),
    );
    // and the second one's start beats the first one's end on the shared microsecond: ordered the
    // other way, the payload would be switched off for the whole of the second observation.
    assert_eq!(
        discrete_at(profile(&response, decl::R_TARGET), 500 * US),
        &json!("B")
    );
    assert!(value_at(profile(&response, decl::R_LOAD), 500 * US) >= 65.0);
}

#[test]
fn an_observation_and_a_downlink_may_overlap_and_their_loads_add() {
    // Different subsystems: the rule is about shared hardware, not about activities in general.
    let response = run(
        1000 * US,
        vec![
            directive(
                1,
                decl::OBSERVE,
                0,
                json!({"duration": 600 * US, "powerWatts": 45.0}),
            ),
            directive(
                2,
                decl::DOWNLINK,
                300 * US,
                json!({"duration": 600 * US,
                                                          "powerWatts": 30.0}),
            ),
        ],
        json!({}),
    );
    // bus 20 + instrument 45 + radio 30 + cooler draw 70
    assert!((value_at(profile(&response, decl::R_LOAD), 400 * US) - 165.0).abs() < 1e-9);
}

// ---------- refusals ---------------------------------------------------------------------------------
#[test]
fn a_frame_period_that_would_flood_the_recorder_is_refused_by_name() {
    // Unbounded work, refused before any of it is done. The message has to name `framePeriod`,
    // because that is the parameter the planner has to change.
    let message = refusal(
        3600 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            0,
            json!({"duration": 3600 * US, "framePeriod": 1}),
        )],
        json!({}),
    );
    assert!(message.contains("framePeriod"), "{message}");
}

#[test]
fn a_zero_deadband_is_refused_rather_than_chattering_forever() {
    // With no deadband the controller switches at every crossing: a run that never terminates, or
    // a profile of millions of segments if it did.
    let message = refusal(600 * US, vec![], json!({"deadbandKelvin": 0.0}));
    assert!(message.contains("deadbandKelvin"), "{message}");
}

#[test]
fn a_massless_detector_is_refused_rather_than_producing_an_infinite_rate() {
    // The path that ends in a NaN reaching PlanDev as a JSON null. Refused at the parameter that
    // caused it, where the message can be about the configuration rather than about arithmetic.
    let message = refusal(600 * US, vec![], json!({"thermalMassJPerK": 0.0}));
    assert!(message.contains("thermalMassJPerK"), "{message}");
}

// ---------- the three Rust hazards -----------------------------------------------------------------------
#[test]
fn an_integer_resource_never_serializes_with_a_decimal_point() {
    // Merlin's asInt() rejects `3.0` against an int schema, at ingest, with nothing pointing back at
    // the cast that widened it.
    let response = run(
        200 * US,
        vec![directive(
            1,
            decl::OBSERVE,
            0,
            json!({"duration": 100 * US,
                                                   "framePeriod": 10 * US}),
        )],
        json!({}),
    );
    for segment in &profile(&response, decl::R_FRAMES).segments {
        assert!(segment.dynamics.is_i64(), "{:?}", segment.dynamics);
    }
    for segment in &profile(&response, decl::R_NEWEST).segments {
        assert!(
            segment.dynamics["frameId"].is_i64(),
            "{:?}",
            segment.dynamics
        );
    }
    let computed = span(&response, 1).computed_attributes.as_ref().unwrap();
    assert!(computed["framesWritten"].is_i64());
    assert!(computed["framesDropped"].is_i64());
}

#[test]
fn no_resource_value_or_computed_attribute_is_ever_null() {
    // What a NaN looks like once serde_json has finished with it: `null`, which is legal JSON, so
    // the host's `check_response` -- which walks the response looking for non-finite NUMBERS --
    // finds no number left to object to and PlanDev stores the hole.
    //
    // Scoped to the values, not to the whole document: `parentId` is null on every root span and is
    // supposed to be.
    fn no_nulls(value: &Value, path: &str) {
        assert!(!value.is_null(), "{path} is null");
        match value {
            Value::Object(map) => {
                for (k, v) in map {
                    no_nulls(v, &format!("{path}.{k}"));
                }
            }
            Value::Array(items) => {
                for (i, v) in items.iter().enumerate() {
                    no_nulls(v, &format!("{path}[{i}]"));
                }
            }
            _ => {}
        }
    }
    let response = run(
        2 * 3600 * US,
        vec![
            directive(1, decl::OBSERVE, 600 * US, json!({"duration": 1800 * US})),
            directive(
                2,
                decl::SET_SETPOINT,
                100 * US,
                json!({"setpointKelvin": 60.0}),
            ),
        ],
        json!({}),
    );
    for profiles in [&response.real_profiles, &response.discrete_profiles] {
        for (name, profile) in profiles {
            for (i, segment) in profile.segments.iter().enumerate() {
                no_nulls(&segment.dynamics, &format!("{name}[{i}]"));
            }
        }
    }
    for span in &response.spans {
        if let Some(computed) = &span.computed_attributes {
            no_nulls(computed, &format!("span {}", span.span_id));
        }
    }
}

#[test]
fn the_same_plan_twice_produces_the_same_bytes() {
    // A randomized map, a multi-threaded executor, or an event ordering that depends on either
    // would all show up here and nowhere else: the difference between two runs is far too small to
    // see by eye.
    let plan = || {
        vec![
            directive(
                1,
                decl::OBSERVE,
                600 * US,
                json!({"duration": 1800 * US,
                                                         "framePeriod": 60 * US}),
            ),
            directive(2, decl::DOWNLINK, 3000 * US, json!({"duration": 600 * US})),
            directive(
                3,
                decl::SET_SETPOINT,
                120 * US,
                json!({"setpointKelvin": 85.0}),
            ),
        ]
    };
    let first = serde_json::to_string(&run(4 * 3600 * US, plan(), json!({}))).unwrap();
    let second = serde_json::to_string(&run(4 * 3600 * US, plan(), json!({}))).unwrap();
    assert_eq!(first, second);
}

// ---------- validate ---------------------------------------------------------------------------------
#[test]
fn deep_validation_reports_a_frame_period_that_could_never_run() {
    // The point of the third verb. Without it this is only discovered by simulating, which is the
    // one moment the planner is not looking at the form that caused it.
    let subjects: Vec<crate::wire::ValidateSubject> = serde_json::from_value(json!([
        {"type": decl::OBSERVE, "arguments": {"duration": 3600 * US, "framePeriod": 1,
                                              "targetName": "M31", "powerWatts": 45.0}},
        {"type": decl::OBSERVE, "arguments": {"duration": 600 * US, "framePeriod": 30 * US,
                                              "targetName": "", "powerWatts": 45.0}},
        {"type": decl::SET_SETPOINT, "arguments": {"setpointKelvin": -5.0}}
    ]))
    .unwrap();
    let notices = run::validate(&subjects);
    assert_eq!(notices["notices"][0].as_array().unwrap().len(), 1);
    assert_eq!(
        notices["notices"][0][0]["subjects"],
        json!(["duration", "framePeriod"])
    );
    assert_eq!(notices["notices"][1][0]["subjects"], json!(["targetName"]));
    assert_eq!(
        notices["notices"][2][0]["subjects"],
        json!(["setpointKelvin"])
    );
}

#[test]
fn deep_validation_says_nothing_about_an_activity_that_is_fine() {
    // A notice on a valid activity paints the editor red for no reason, which is worse than no deep
    // validation at all.
    let subjects: Vec<crate::wire::ValidateSubject> = serde_json::from_value(json!([
        {"type": decl::OBSERVE, "arguments": {"duration": 600 * US, "framePeriod": 30 * US,
                                              "targetName": "M31", "powerWatts": 45.0}}
    ]))
    .unwrap();
    assert_eq!(run::validate(&subjects)["notices"][0], json!([]));
}
