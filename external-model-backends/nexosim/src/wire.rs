//! The stdio wire: what `ExecBackend` writes to stdin, and what it will accept back on stdout.
//!
//! Everything the model emits is built through the constructors here, and `real()` is the only way
//! to get an `f64` onto the wire. That is not tidiness. `serde_json` serializes `NaN` and
//! `Infinity` as `null` and returns `Ok`, so a divergent integration leaves via a channel that
//! looks perfectly healthy: the adapter's `check_response` walks the response looking for
//! non-finite NUMBERS and a JSON `null` is not one, PlanDev stores a profile segment whose
//! `initial` is null, and the first thing anyone learns about it is a chart with a hole in it.
//! Python is protected from the same mistake by `json.dumps(..., allow_nan=False)`, which raises.
//! Rust has no equivalent, so the check has to be here, at the point where the number is minted.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Number, Value};

/// Why the run stopped. The distinction is the same one `adapter_core` draws between a 400 and a
/// 500, and it exists here because only the model knows which of the two a given failure is.
///
/// `Caller` exits 2 and `Model` exits 1. `ExecBackend` currently maps every nonzero exit to a 500
/// regardless, so today the difference is only visible in the message -- but the model should be
/// telling the truth about it whether or not the host is listening yet.
#[derive(Debug)]
pub enum Fault {
    /// The request is wrong in a way no schema can express. Should be a 400.
    Caller(String),
    /// The model could not produce a result the contract can carry. A 500.
    Model(String),
}

impl Fault {
    pub fn message(&self) -> &str {
        match self {
            Fault::Caller(m) | Fault::Model(m) => m,
        }
    }
    pub fn exit_code(&self) -> i32 {
        match self {
            Fault::Model(_) => 1,
            Fault::Caller(_) => 2,
        }
    }
}

pub fn caller<T>(msg: impl Into<String>) -> Result<T, Fault> {
    Err(Fault::Caller(msg.into()))
}

/// The ONLY route from an `f64` to a JSON number.
///
/// `what` is threaded through so the failure names the resource, span and instant that produced
/// it. Without that the operator gets "the model produced a non-finite value" and a whole
/// simulation to search.
pub fn real(v: f64, what: &str) -> Result<Value, Fault> {
    match Number::from_f64(v) {
        Some(n) => Ok(Value::Number(n)),
        // from_f64 returns None for exactly the two cases serde_json would otherwise write as
        // `null`: NaN and +/-Infinity.
        None => Err(Fault::Model(format!(
            "{what} is {v}, which is not a finite number and cannot be sent as JSON"
        ))),
    }
}

/// An integer-valued channel, kept out of `f64` end to end.
///
/// A resource declared `{"type": "int"}` and emitted as a float serializes as `1.0`, and merlin's
/// `asInt()` rejects it -- at ingest, long after the model has finished, with nothing pointing at
/// the cast that widened it. Nothing in this model converts a count to `f64` on the way out.
pub fn int(v: i64) -> Value {
    Value::Number(Number::from(v))
}

// ---------- request -----------------------------------------------------------------------------
/// A `/simulate` request as `ExecBackend` writes it: ALREADY NORMALIZED by `adapter_core`.
///
/// Nothing below re-checks argument types or fills a default, because by the time this is parsed
/// every directive has a declared type, all of its required parameters, defaults resolved and every
/// value checked against the schema `decl.rs` published. Re-implementing that here is exactly the
/// duplication `ExecBackend` exists to prevent.
#[derive(Debug, Deserialize)]
pub struct Request {
    /// Read by nothing here, and kept so this struct is the whole wire shape rather than the part
    /// that happens to be used today. Every offset this model reports is relative to the start of
    /// the window, which is exactly why the contract makes `planStart` optional.
    #[allow(dead_code)]
    #[serde(rename = "planStart")]
    pub plan_start: Option<String>,
    pub duration: i64,
    #[serde(default)]
    pub configuration: Map<String, Value>,
    #[serde(default)]
    pub directives: Vec<Directive>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Directive {
    /// Merlin's directive id. Echoed back on the span untouched and never interpreted, so it stays
    /// a `Value`: an adapter that assumed an integer here would break the day one arrives as a
    /// string.
    #[serde(default)]
    pub id: Value,
    #[serde(rename = "type")]
    pub typ: String,
    #[serde(rename = "startOffset")]
    pub start_offset: i64,
    #[serde(default)]
    pub arguments: Map<String, Value>,
}

/// A `/validate` batch, for the third verb this model adds to the two `ExecBackend` defines.
#[derive(Debug, Deserialize)]
pub struct ValidateRequest {
    #[serde(default)]
    pub subjects: Vec<ValidateSubject>,
}

#[derive(Debug, Deserialize)]
pub struct ValidateSubject {
    #[serde(rename = "type")]
    pub typ: String,
    #[serde(default)]
    pub arguments: Map<String, Value>,
}

// ---------- response ----------------------------------------------------------------------------
#[derive(Debug, Serialize)]
pub struct Response {
    // BTreeMap, not HashMap. Rust randomizes HashMap iteration per PROCESS, so a HashMap here
    // would reorder the resources in the response on every restart -- harmless for the profiles
    // themselves, and a trap for anyone who later diffs two runs to prove a change was inert.
    #[serde(rename = "realProfiles")]
    pub real_profiles: std::collections::BTreeMap<String, Profile>,
    #[serde(rename = "discreteProfiles")]
    pub discrete_profiles: std::collections::BTreeMap<String, Profile>,
    pub spans: Vec<Span>,
}

#[derive(Debug, Serialize)]
pub struct Profile {
    pub schema: Value,
    pub segments: Vec<Segment>,
}

#[derive(Debug, Serialize)]
pub struct Segment {
    /// Integer microseconds. `check_response` rejects a non-integer duration, and it is `i64` here
    /// so there is no float that could arrive at that check rounded.
    pub duration: i64,
    pub dynamics: Value,
}

/// `{initial, rate}`, where `rate` is per SECOND -- PlanDev evaluates a real profile as
/// `initial + rate * elapsedSeconds`.
pub fn ramp(initial: f64, rate: f64, what: &str) -> Result<Value, Fault> {
    let mut m = Map::new();
    m.insert("initial".into(), real(initial, &format!("{what} initial"))?);
    m.insert("rate".into(), real(rate, &format!("{what} rate"))?);
    Ok(Value::Object(m))
}

#[derive(Debug, Serialize)]
pub struct Span {
    #[serde(rename = "spanId")]
    pub span_id: i64,
    #[serde(rename = "parentId")]
    pub parent_id: Option<i64>,
    #[serde(rename = "directiveId")]
    pub directive_id: Value,
    #[serde(rename = "type")]
    pub typ: String,
    #[serde(rename = "startOffset")]
    pub start_offset: i64,
    pub arguments: Map<String, Value>,
    // Merlin tells a finished span from a running one by the presence of BOTH of these
    // (PostgresResultsCellRepository), and `check_response` refuses any other combination. They are
    // written together by `Span::finished` and omitted together by `Span::running`, so there is no
    // code path that can set one without the other.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration: Option<i64>,
    #[serde(rename = "computedAttributes", skip_serializing_if = "Option::is_none")]
    pub computed_attributes: Option<Value>,
}

impl Span {
    pub fn running(
        span_id: i64,
        directive_id: Value,
        typ: &str,
        start_offset: i64,
        arguments: Map<String, Value>,
    ) -> Self {
        Span {
            span_id,
            parent_id: None,
            directive_id,
            typ: typ.to_string(),
            start_offset,
            arguments,
            duration: None,
            computed_attributes: None,
        }
    }

    pub fn finished(mut self, duration: i64, computed: Map<String, Value>) -> Self {
        self.duration = Some(duration);
        self.computed_attributes = Some(Value::Object(computed));
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serde_json_writes_a_non_finite_float_as_null_so_the_model_must_refuse_it_itself() {
        // The whole reason `real()` exists. If this ever starts erroring on its own, the guard is
        // redundant -- but until then a NaN reaches PlanDev as a JSON null, which is legal JSON,
        // which means every check downstream of serialization waves it through.
        assert_eq!(serde_json::json!(f64::NAN).to_string(), "null");
        assert_eq!(serde_json::json!(f64::INFINITY).to_string(), "null");
        assert!(real(f64::NAN, "/x").is_err());
        assert!(real(f64::NEG_INFINITY, "/x").is_err());
    }

    #[test]
    fn a_refused_value_names_the_channel_that_produced_it() {
        // "the model produced a non-finite value" with no location leaves an operator grepping a
        // whole simulation; the message has to carry the resource.
        let err = real(f64::NAN, "/thermal/detectorKelvin at 00:10:00").unwrap_err();
        assert!(
            err.message()
                .contains("/thermal/detectorKelvin at 00:10:00"),
            "{err:?}"
        );
    }

    #[test]
    fn an_integer_channel_serializes_without_a_decimal_point() {
        // `{"type":"int"}` emitted as 3.0 is rejected by merlin's asInt() at ingest. Emitting
        // through `int()` rather than `real()` is what keeps that from happening silently.
        assert_eq!(int(3).to_string(), "3");
        assert_eq!(real(3.0, "/x").unwrap().to_string(), "3.0");
    }

    #[test]
    fn a_finished_span_carries_both_duration_and_computed_attributes() {
        // check_response rejects a span with one and not the other, and merlin reads a span with
        // computed attributes and no duration as finished-with-no-end.
        let running = Span::running(1, Value::Null, "Observe", 0, Map::new());
        assert!(running.duration.is_none() && running.computed_attributes.is_none());
        let done = Span::running(1, Value::Null, "Observe", 0, Map::new()).finished(5, Map::new());
        assert!(done.duration.is_some() && done.computed_attributes.is_some());
    }
}
