//! The declaration: activity types, resource types and configuration, in the JSON shape
//! `adapter_core.declaration_from_json` parses.
//!
//! `/introspect` has no field for a default, but this document does, because a default is what
//! makes a parameter optional and what `effectiveArguments` is built from. A parameter with no
//! `default` key is required.
//!
//! Two things about this file are load-bearing and neither is obvious:
//!
//! PARAMETER ORDER IS PART OF THE MODEL. Merlin assigns each parameter an `order` from its index in
//! this array, persists it, reads activity types back sorted by it, and plandev-ui lays the
//! argument form out in that sequence. It is also hashed in declaration order, so reordering this
//! list is drift the identity hash is supposed to catch. Parameters therefore live in JSON ARRAYS,
//! never in a map -- a Rust `HashMap` would reorder them on every process restart and hand merlin a
//! different attestation each time the adapter came up.
//!
//! THE DOCUMENT IS THE ATTESTATION. `adapter_core` re-canonicalizes what it parses before hashing,
//! so object key order inside this file does not move the hash -- but array order does, and so does
//! every default, every `computedAttributesSchema`, and the required/optional split.

use serde_json::{Value, json};

pub const MODEL_KEY: &str = "cryo";
pub const MODEL_NAME: &str = "cryo";
pub const MODEL_VERSION: &str = "1.0.0";

pub const OBSERVE: &str = "Observe";
pub const DOWNLINK: &str = "Downlink";
pub const SET_SETPOINT: &str = "SetCoolerSetpoint";

pub const R_KELVIN: &str = "/thermal/detectorKelvin";
pub const R_COOLER: &str = "/thermal/cryocooler";
pub const R_LOAD: &str = "/power/loadWatts";
pub const R_FRAMES: &str = "/recorder/framesStored";
pub const R_NEWEST: &str = "/recorder/newestFrame";
pub const R_TARGET: &str = "/instrument/target";

pub const COOLER_OFF: &str = "Off";
pub const COOLER_ON: &str = "Cooling";

pub const US_PER_S: i64 = 1_000_000;

/// The most frame and downlink events one request may schedule, across all of its directives.
///
/// Not a performance tuning knob: a `framePeriod` of one microsecond over a day-long plan is 86
/// billion events, and the honest answer to it is a refusal naming `framePeriod` rather than an
/// adapter that never returns. The count is exact and known before the simulation starts, so the
/// refusal happens in microseconds.
pub const MAX_ACTIVITY_EVENTS: i64 = 50_000;

/// The most times the cryocooler may switch in one run. A deadband small enough relative to the
/// heat flux makes a bang-bang controller chatter without bound; PlanDev would receive a profile of
/// millions of segments, if it received one at all.
pub const MAX_COOLER_SWITCHES: u32 = 20_000;

fn real() -> Value {
    json!({"type": "real"})
}
fn int() -> Value {
    json!({"type": "int"})
}
fn duration() -> Value {
    json!({"type": "duration"})
}
fn string() -> Value {
    json!({"type": "string"})
}

/// The whole declaration, as `describe` prints it.
pub fn declaration() -> Value {
    json!({
        "key": MODEL_KEY,
        "name": MODEL_NAME,
        "version": MODEL_VERSION,
        "activityTypes": [
            {
                "name": OBSERVE,
                "parameters": [
                    {"name": "duration", "schema": duration()},
                    // A string argument, and one the model actually carries rather than just
                    // echoing: it ends up inside /recorder/newestFrame, which is how a plan can be
                    // read back off the recorder.
                    {"name": "targetName", "schema": string(), "default": "unnamed"},
                    {"name": "framePeriod", "schema": duration(), "default": 30 * US_PER_S},
                    {"name": "powerWatts", "schema": real(), "default": 45.0}
                ],
                "computedAttributesSchema": {"type": "struct", "items": {
                    "framesWritten": int(),
                    "framesDropped": int(),
                    "peakDetectorKelvin": real()
                }}
            },
            {
                "name": DOWNLINK,
                "parameters": [
                    {"name": "duration", "schema": duration()},
                    {"name": "framePeriod", "schema": duration(), "default": 5 * US_PER_S},
                    {"name": "powerWatts", "schema": real(), "default": 30.0}
                ],
                "computedAttributesSchema": {"type": "struct", "items": {
                    "framesSent": int(),
                    "framesRemaining": int()
                }}
            },
            {
                // No `duration` parameter at all: an instantaneous retune, which comes back as a
                // span of duration 0. Worth having one, because an adapter that assumes every
                // activity has a duration only finds out when a mission model does not.
                "name": SET_SETPOINT,
                "parameters": [
                    {"name": "setpointKelvin", "schema": real()}
                ],
                "computedAttributesSchema": {"type": "struct", "items": {
                    "previousSetpointKelvin": real()
                }}
            }
        ],
        "resourceTypes": [
            {"name": R_KELVIN, "schema": real()},
            {"name": R_COOLER, "schema": {"type": "variant", "variants": [
                {"key": COOLER_OFF, "label": COOLER_OFF},
                {"key": COOLER_ON, "label": COOLER_ON}
            ]}},
            {"name": R_LOAD, "schema": real()},
            // Integer, and integer all the way out. A count widened to f64 arrives as `1.0` and
            // merlin's asInt() rejects the profile at ingest.
            {"name": R_FRAMES, "schema": int()},
            // A struct-valued resource: the metadata of the most recent stored frame. Structs are
            // CLOSED in PlanDev -- the gate rejects a value carrying a field this schema does not
            // declare, and one missing a field it does -- so there is no "no frame yet" null. The
            // pre-first-frame value is frameId 0.
            {"name": R_NEWEST, "schema": {"type": "struct", "items": {
                "frameId": int(),
                "target": string(),
                "detectorKelvin": real()
            }}},
            {"name": R_TARGET, "schema": string()}
        ],
        "parameters": [
            {"name": "initialKelvin", "schema": real(), "default": 95.0},
            {"name": "setpointKelvin", "schema": real(), "default": 90.0},
            {"name": "deadbandKelvin", "schema": real(), "default": 2.0},
            {"name": "thermalMassJPerK", "schema": real(), "default": 900.0},
            {"name": "parasiticWatts", "schema": real(), "default": 12.0},
            // Sized so the cooler beats the parasitic leak comfortably and the PAYLOAD by a hair:
            // 12 + 45 - 55 is +2 W, so the detector drifts up about 8 K over an hour-long
            // observation and recovers in a few minutes afterwards. That is the operational
            // constraint the model exists to express -- "how long can I integrate before the
            // detector is out of spec" is a question about a resource, which is a question PlanDev
            // can answer.
            {"name": "coolerLiftWatts", "schema": real(), "default": 55.0},
            {"name": "coolerDrawWatts", "schema": real(), "default": 70.0},
            {"name": "busLoadWatts", "schema": real(), "default": 20.0},
            {"name": "recorderCapacityFrames", "schema": int(), "default": 2000}
        ],
        // Ignored by `adapter_core.declaration_from_json`, which has no branch for it -- see
        // nx_service.py, which lifts it out of this document by hand. Published anyway: the
        // capability belongs to the model, and the day the host learns to parse it this file is
        // already correct.
        //
        // A pure simulator. Directives in, profiles and spans out; it places nothing of its own,
        // so PlanDev's scheduler can drive it as an oracle.
        "capabilities": {"plandevScheduling": {"supported": true}}
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn activity(name: &str) -> Value {
        declaration()["activityTypes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|a| a["name"] == name)
            .unwrap()
            .clone()
    }

    #[test]
    fn parameters_are_emitted_in_declaration_order() {
        // Merlin persists each parameter's index as its `order` and plandev-ui renders the form in
        // it. A map anywhere on this path would reshuffle the form between adapter restarts.
        let names: Vec<_> = activity(OBSERVE)["parameters"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| p["name"].as_str().unwrap().to_string())
            .collect();
        assert_eq!(
            names,
            ["duration", "targetName", "framePeriod", "powerWatts"]
        );
    }

    #[test]
    fn describing_twice_in_one_process_produces_identical_bytes() {
        // Necessary but not sufficient: the failure this guards against is a HashMap, and a
        // HashMap's order is randomized PER PROCESS, so it is stable within one. The
        // across-process half of this test is in test_nx_service.py, which runs `describe` twice.
        assert_eq!(declaration().to_string(), declaration().to_string());
    }

    #[test]
    fn exactly_one_parameter_per_activity_has_no_default_and_is_therefore_required() {
        // `default is None` is what adapter_core reads as "required". A default accidentally added
        // to `duration` would make it optional, and the activity would silently simulate as
        // zero-length instead of being refused in the editor.
        for (typ, required) in [
            (OBSERVE, "duration"),
            (DOWNLINK, "duration"),
            (SET_SETPOINT, "setpointKelvin"),
        ] {
            let params = activity(typ)["parameters"].as_array().unwrap().clone();
            let without: Vec<_> = params
                .iter()
                .filter(|p| p.get("default").is_none())
                .map(|p| p["name"].as_str().unwrap().to_string())
                .collect();
            assert_eq!(without, [required], "{typ}");
        }
    }

    #[test]
    fn an_int_schema_never_carries_a_floating_point_default() {
        // A default of 2000.0 against `{"type":"int"}` is rejected by adapter_core's own
        // typechecker the first time a planner opens the configuration -- not at startup, and not
        // in any test that does not resolve defaults.
        for p in declaration()["parameters"].as_array().unwrap() {
            if p["schema"]["type"] == "int" {
                assert!(p["default"].is_i64(), "{}: {}", p["name"], p["default"]);
            }
        }
    }

    #[test]
    fn every_resource_declares_a_schema_type_the_contract_knows() {
        let known = [
            "real", "int", "duration", "boolean", "string", "path", "variant", "series", "struct",
        ];
        for r in declaration()["resourceTypes"].as_array().unwrap() {
            let t = r["schema"]["type"].as_str().unwrap();
            assert!(known.contains(&t), "{}: {t}", r["name"]);
        }
    }
}
