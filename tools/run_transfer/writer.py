#!/usr/bin/env python3
"""Read and write PlanDev run-transfer files -- a simulation PlanDev did not perform.

A `.run.json` file is one simulation, frozen: the model's type declaration, the directives the run
was performed against, and the profiles and spans it produced. PlanDev imports it as a first-class
run, with nothing behind the model to compile or to call. `README.md`, beside this file, is the
normative format reference; this is the reference implementation of a producer.

    python3 -m run_transfer.writer --help    # not a CLI; import it

**Stdlib only, and standalone on purpose.** A producer is the party most likely to live outside
PlanDev altogether -- another team, another language's toolchain, a laptop with a JVM and no
network -- so this module depends on nothing but Python, and on no other file in this repository.
Copy it next to your own code if that is easier than depending on this repo.

What a producer supplies:

  * a DECLARATION -- activity types with their parameters, resource types, configuration
    parameters -- as `ModelDeclaration`, or as any object with the same attributes;
  * the DIRECTIVES the run was performed against, as `RunDirective`, each with a `local_id`;
  * the RESULTS, as `{realProfiles, discreteProfiles, spans}`.

What this module supplies:

  * `RunTransfer(...).to_json()` -- the document, in the format's own units and calendars;
  * `parse_run` -- the inverse, which is what makes the round trip testable rather than asserted;
  * `run_problems` / `check_run` -- PlanDev's own ingest rules, applied BEFORE the upload;
  * `dumps_run` / `write_run` / `read_run` -- serialization, including the one rule that silently
    corrupts a run if a producer gets it wrong (see `dumps_run`);
  * `declaration_digest` -- the identity PlanDev stores, which decides whether re-importing a run
    reuses the model it already created.
"""
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

__all__ = [
    "RUN_TRANSFER_KIND", "RUN_TRANSFER_VERSION", "PLAN_TRANSFER_VERSION", "NO_SIMULATOR_REASON",
    "SIMULATION", "PLANDEV_SCHEDULING", "PLAN_IMPORT", "supported", "unsupported",
    "Parameter", "ActivityType", "ResourceType", "ModelDeclaration", "declaration_from_json",
    "RunDirective", "RunTransfer", "parse_run", "run_model", "run_plan", "run_results",
    "canonical_json", "declaration_digest", "dumps_run", "write_run", "read_run",
    "run_problems", "check_run", "nonconformance", "RunTransferError",
    "us_to_interval", "interval_to_us", "dt_to_plan_time", "dt_to_results_time", "results_time_to_dt",
]


class RunTransferError(Exception):
    """A run file that cannot be written, or that PlanDev would refuse."""


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def iso_to_dt(iso):
    """An ISO-8601 instant (with `Z` or an offset) -> an aware UTC datetime."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


# ---------- ValueSchema conformance -----------------------------------------------------------------
def nonconformance(value, schema):
    """None if `value` fits `schema`, else a message saying why.

    Mirrors merlin's ExternalResultsGate check, so an argument this accepts is one the gate will
    also accept once it comes back on a span.

    This is the ONLY typecheck there is. Merlin DELEGATES authoritative validation to the backend
    for external models: if a type-wrong argument gets past here it validates green in the editor
    and then either crashes the simulation or produces a span the ingest gate rejects.
    """
    if value is None:
        return None                                   # a schema says nothing about nullability
    t = schema.get("type")
    if t == "real":
        # An int satisfies real -- PlanDev widens it, and refusing one would reject a perfectly
        # ordinary argument. Non-finite floats do NOT: json.dumps would emit bare NaN/Infinity,
        # which is not legal JSON, so they are a type error and not merely a strange number.
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        return None if ok else "expected a finite real, got %r" % (value,)
    if t == "int":
        # bool is an int subclass in Python; PlanDev's int schema does not accept one, and a `True`
        # silently stored as 1 is a type error that only surfaces much later.
        ok = isinstance(value, int) and not isinstance(value, bool)
        return None if ok else "expected an integer, got %r" % (value,)
    if t == "duration":
        # Durations are integer MICROSECONDS on the wire; 1.5 has no representation, and neither
        # does "01:00:00" -- a model's own notation is the model's business, not the contract's.
        ok = isinstance(value, int) and not isinstance(value, bool)
        return None if ok else "expected a duration as integer microseconds, got %r" % (value,)
    if t == "boolean":
        return None if isinstance(value, bool) else "expected a boolean, got %r" % (value,)
    if t in ("string", "path"):
        return None if isinstance(value, str) else "expected a string, got %r" % (value,)
    if t == "variant":
        keys = [v["key"] for v in schema.get("variants", [])]
        if not isinstance(value, str):
            return "expected one of %s, got %r" % (keys, value)
        return None if value in keys else "expected one of %s, got %r" % (keys, value)
    if t == "series":
        if not isinstance(value, list):
            return "expected a list, got %r" % (value,)
        for i, v in enumerate(value):
            sub = nonconformance(v, schema.get("items", {}))
            if sub:
                return "at [%d]: %s" % (i, sub)
        return None
    if t == "struct":
        if not isinstance(value, dict):
            return "expected an object, got %r" % (value,)
        items = schema.get("items", {})
        # Both directions are checked. A missing field is the obvious error; an UNEXPECTED one
        # matters just as much, because ValueSchema structs are closed -- merlin's gate rejects a
        # span carrying a field the schema never declared.
        for k, s in items.items():
            if k not in value:
                return "missing field '%s'" % k
            sub = nonconformance(value[k], s)
            if sub:
                return "at .%s: %s" % (k, sub)
        for k in value:
            if k not in items:
                return "unexpected field '%s'" % k
        return None
    return None


# ---------- the declaration ---------------------------------------------------------------------
@dataclass(frozen=True)
class Parameter:
    """One declared parameter: a name and a `ValueSchema`.

    A run file carries no DEFAULTS -- PlanDev has no field for them -- so there is nowhere to put
    one here. Which parameters are required is stated outright instead, by `ActivityType`.
    """
    name: str
    schema: Dict[str, Any]


@dataclass(frozen=True)
class ActivityType:
    """One activity type. `parameters` is ORDERED and the order is load-bearing.

    merlin assigns each parameter an `order` from its index in this array, persists it, reads
    activity types back sorted by it, and plandev-ui lays the argument form out in that sequence.
    Sorting the array is a bug, not a tidy-up.
    """
    name: str
    parameters: Sequence[Parameter]
    #: Required, not optional: the ingest gate holds every finished span's computed attributes to
    #: it, so a type that computes nothing declares the closed empty struct.
    computed_attributes_schema: Optional[Dict[str, Any]] = None
    required_parameters: Sequence[str] = ()
    #: Documentation. PlanDev stores and displays both; neither is part of the digest.
    subsystem: Optional[str] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class ResourceType:
    name: str
    schema: Dict[str, Any]


@dataclass
class ModelDeclaration:
    """Everything a run file says about the model its results were produced against.

    A minimal type on purpose. Any object carrying the same attributes works everywhere this one
    does -- a backend that already models its own declaration passes that instead of rebuilding it.
    """
    name: str
    version: str = "1.0.0"
    activity_types: Sequence[ActivityType] = ()
    resource_types: Sequence[ResourceType] = ()
    #: Simulation configuration: model-wide settings a planner edits per plan, distinct from an
    #: activity's arguments. ORDERED, for the same reason activity parameters are.
    config_parameters: Sequence[Parameter] = ()

    def activity_type(self, name):
        for act in self.activity_types:
            if act.name == name:
                return act
        return None


# ---------- capabilities --------------------------------------------------------------------------
# What PlanDev may DO with a model, as opposed to what the model is. Nothing in a list of activity
# types says whether PlanDev can simulate the model or schedule against it, so it is declared.
#
# Every capability is an OBJECT, never a bare boolean, so an unsupported one has somewhere to carry
# its own explanation. That is what keeps plandev-ui free of branches naming a kind of model: it
# renders "unavailable because <sentence>" without knowing what produced the run. An ABSENT
# capability means unsupported.

#: Whether PlanDev can run a simulation of this model. Always unsupported in a run file -- see
#: `run_model`.
SIMULATION = "simulation"
#: PlanDev's own scheduler may place activities in plans using this model.
PLANDEV_SCHEDULING = "plandevScheduling"
#: Something can read this model's native plan format and hand back directives.
PLAN_IMPORT = "planImport"


def unsupported(reason):
    """A capability that does not apply, with the sentence the UI should show for it."""
    return {"supported": False, "reason": reason}


def supported(**detail):
    """A capability that applies, plus whatever that capability needs to describe itself."""
    return dict(detail, supported=True)


def declaration_from_json(model):
    """A run file's `model` member -> a `ModelDeclaration`."""
    return ModelDeclaration(
        name=model.get("name") or "model",
        version=model.get("version") or "1.0.0",
        activity_types=[ActivityType(
            name=a["name"],
            parameters=[Parameter(p["name"], p.get("schema") or {"type": "string"})
                        for p in a.get("parameters") or []],
            computed_attributes_schema=a.get("computedAttributesSchema"),
            required_parameters=list(a.get("requiredParameters") or ()),
            subsystem=a.get("subsystem"), description=a.get("description"))
            for a in model.get("activityTypes") or []],
        resource_types=[ResourceType(r["name"], r.get("schema") or {"type": "string"})
                        for r in model.get("resourceTypes") or []],
        config_parameters=[Parameter(p["name"], p.get("schema") or {"type": "string"})
                           for p in model.get("parameters") or []])


# ---------- the document ---------------------------------------------------------------------------
# A `.run.json` file is one simulation, frozen: the model's type declaration, the directives the run
# was performed against, and the profiles and spans it produced. PlanDev imports it as a first-class
# run with no backend anywhere behind it. `README.md`, beside this file, is the normative spec;
# what follows is the writer for it.
#
# The writer takes a producer's inputs in the shape a simulator already has them: a
# `ModelDeclaration`, the directives the run was performed against, and the
# `{realProfiles, discreteProfiles, spans}` the run produced. Written once, it keeps one place
# honest about the format.

RUN_TRANSFER_KIND = "plandev-run"
#: The envelope's version. A MAJOR only: a consumer that does not recognize it refuses the whole
#: file rather than reading the members it happens to understand.
RUN_TRANSFER_VERSION = "1"
#: The `plan` member carries PlanTransfer's own version, independently of the envelope's.
PLAN_TRANSFER_VERSION = "2"

#: Whether PlanDev can run this model. Always unsupported in a run file -- see `run_model`.
SIMULATION = "simulation"

#: The sentence PlanDev shows where the simulate control would be. A reason is mandatory for an
#: unsupported capability, and this is the generic one: it says what happened and what to do next,
#: without naming a framework, because nothing downstream of the file may know what produced it.
NO_SIMULATOR_REASON = (
    "This model was declared by a run transfer, so PlanDev has no simulator to run it. "
    "Import another recorded run to see different results.")

# Mirrors ExternalResultsGate. Activity type and parameter names become bare TypeScript identifiers
# in the generated constraint and scheduling typings; resource names do not, and are only held to
# being non-empty, under 256 characters and free of control characters.
_TS_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]{0,127}\Z")
_RESOURCE_NAME = re.compile(r"[^\x00-\x1f\x7f]{1,255}\Z")


# -- canonicalization and identity ------------------------------------------------------------------
def canonical_json(payload):
    r"""Sorted-key, whitespace-free JSON, as UTF-8 bytes.

    Three arguments here are each load-bearing against a SECOND implementation of this function --
    the gateway computes the same digest over the same payload in TypeScript, and a digest that
    disagrees means a re-import creates a duplicate model instead of reusing one:

    * `separators` -- Python's default is `', '` / `': '`; `JSON.stringify` emits neither.
    * `ensure_ascii=False` -- Python's default escapes every non-ASCII character as `\uXXXX`, which
      `JSON.stringify` does not. A model with an accented resource name would hash differently in
      the two languages, and nothing but that model would ever reveal it.
    * `allow_nan=False` -- a non-finite value would be written as the non-JSON token `Infinity`,
      which no other implementation can read back at all.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def declaration_digest(model):
    """16 hex characters identifying the TYPE SURFACE a run file's `model` member declares.

    This is NOT the identity hash a live backend publishes, and the difference is not an oversight.
    That one is taken over everything the backend knows, including each parameter's default. A run
    file cannot carry defaults -- PlanDev has no field for them -- so a reader of the file could
    never reproduce it. This digest is therefore taken over exactly what
    the file carries, which is exactly what PlanDev will store, and is what the importer uses to
    answer the one question a repeat import asks: is this the same model I already have?

    Same answer, byte for byte, as the gateway's `declarationDigest`. That equality is asserted by a
    test on each side against the same fixture, because the two together are what make a re-import
    idempotent rather than a second model with the same name.
    """
    payload = {
        "acts": {a["name"]: {"computed": a.get("computedAttributesSchema"),
                             "params": [[p["name"], p["schema"]] for p in a.get("parameters") or []],
                             "required": a.get("requiredParameters")}
                 for a in model.get("activityTypes") or []},
        "caps": model.get("capabilities") or {},
        "cfg": [[p["name"], p["schema"]] for p in model.get("parameters") or []],
        "res": {r["name"]: r["schema"] for r in model.get("resourceTypes") or []},
    }
    # There is no number anywhere in a ValueSchema, which is why this agrees with a JavaScript
    # implementation without either side having to pin a float format.
    return hashlib.sha256(canonical_json(payload)).hexdigest()[:16]


# -- the format's two calendars, and its interval literals -------------------------------------------
def us_to_interval(us):
    """Microseconds -> a Postgres interval literal, `[-][N days ]HH:MM:SS[.ffffff]`.

    Negative values carry the sign on EVERY component (`-1 days -02:00:00`), which is what Postgres
    emits and the only form both it and the UI's `postgres-interval` read back as the same
    magnitude -- `-1 days 02:00:00` parses as -22h, not -26h.
    """
    us = int(us)
    sign = "-" if us < 0 else ""
    us = abs(us)
    days, us = divmod(us, 86_400_000_000)
    hours, us = divmod(us, 3_600_000_000)
    minutes, us = divmod(us, 60_000_000)
    seconds, micros = divmod(us, 1_000_000)
    body = "%s%02d:%02d:%02d" % (sign, hours, minutes, seconds)
    if micros:
        body += ".%06d" % micros
    return "%s%d days %s" % (sign, days, body) if days else body


_INTERVAL = re.compile(r"\A(?P<sign>-)?(?:(?P<days>\d+) days? )?-?(?P<h>\d+):(?P<m>\d{2}):"
                       r"(?P<s>\d{2})(?:\.(?P<frac>\d{1,6}))?\Z")


def interval_to_us(text):
    """A Postgres interval literal -> microseconds. The inverse of `us_to_interval`."""
    match = _INTERVAL.match((text or "").strip())
    if not match:
        raise RunTransferError("%r is not an interval literal; expected [-][N days ]HH:MM:SS[.ffffff]"
                         % (text,))
    micros = int((match.group("frac") or "0").ljust(6, "0"))
    total = (int(match.group("days") or 0) * 86_400_000_000
             + int(match.group("h")) * 3_600_000_000 + int(match.group("m")) * 60_000_000
             + int(match.group("s")) * 1_000_000 + micros)
    return -total if match.group("sign") else total


def dt_to_plan_time(dt):
    """`plan.start_time`: an ISO CALENDAR date-time with a literal `+00:00`.

    Not a `Z`. plandev-ui strips exactly the `+00:00` suffix when it renders a plan start, and a `Z`
    survives the strip and lands in the field.
    """
    dt = dt.astimezone(timezone.utc)
    body = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if dt.microsecond:
        body += ".%06d" % dt.microsecond
    return body + "+00:00"


def dt_to_results_time(dt):
    """`results.startTime`: DAY-OF-YEAR, `uuuu-DDDTHH:MM:SS[.ffffff]`.

    Yes, the two timestamps in one file use different calendars. This one is parsed by
    `gov.nasa.ammos.plandev.types.Timestamp`, which reads day-of-year and nothing else; the plan's
    is parsed by Postgres. The asymmetry is inherited from the two formats this one embeds, and a
    calendar date here is a parse failure rather than a wrong time.
    """
    dt = dt.astimezone(timezone.utc)
    body = dt.strftime("%Y-%jT%H:%M:%S")
    return body + (".%06d" % dt.microsecond if dt.microsecond else "")


def results_time_to_dt(text):
    """The inverse of `dt_to_results_time`."""
    fmt = "%Y-%jT%H:%M:%S.%f" if "." in (text or "") else "%Y-%jT%H:%M:%S"
    try:
        return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        raise RunTransferError("%r is not a day-of-year timestamp; expected uuuu-DDDTHH:MM:SS[.ffffff]"
                         % (text,))


# -- the document -------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RunDirective:
    """One directive of the run, in the writer's units rather than the file's.

    `local_id` is the file's own keyspace, and the reason this type exists. `ExternalResultsGate`
    requires every span's directive to be one merlin knows about, but Postgres assigns directive ids
    on insert, so a file cannot name them. Spans and anchors therefore reference `local_id`, and the
    importer rewrites both through the map it builds as it inserts.

    A producer that hands these to a backend should pass `local_id` as the directive id it sends, so
    the spans come back already carrying it -- see `run_results`.
    """
    local_id: str
    type: str
    start_offset: int = 0
    arguments: Dict[str, Any] = field(default_factory=dict)
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Sequence[Any] = ()
    anchor_id: Optional[str] = None
    anchored_to_start: bool = True


def run_model(declaration, mission, name=None, version=None, description=None, capabilities=None,
              simulation_reason=NO_SIMULATOR_REASON):
    """A `ModelDeclaration` -> the file's `model` member: the `registerModelTypes` payload, unchanged.

    Capabilities are NOT inherited from the declaration, which is the one surprising thing here. A
    live backend's capabilities describe what that backend can do -- read its framework's plan
    format, decline PlanDev's scheduler because it runs its own -- and every one of them needs the
    backend to be reachable. Behind an imported run there is no backend, so carrying them across
    would publish an offer PlanDev cannot meet. What is true of every declared model, and the only
    capability this function asserts, is that it cannot be simulated. A producer that knows better
    passes `capabilities` explicitly.
    """
    model = {"mission": mission, "name": name or declaration.name,
             "version": version or declaration.version}
    if description is not None:
        model["description"] = description
    model["activityTypes"] = [_activity_type_json(a) for a in declaration.activity_types]
    model["resourceTypes"] = [{"name": r.name, "schema": r.schema}
                              for r in declaration.resource_types]
    model["parameters"] = [{"name": p.name, "schema": p.schema}
                           for p in declaration.config_parameters]
    model["capabilities"] = dict({SIMULATION: unsupported(simulation_reason)},
                                 **(capabilities or {}))
    return model


def _activity_type_json(act):
    if act.computed_attributes_schema is None:
        # Not defaulted to an empty struct on the model's behalf. The gate holds every finished
        # span's computed attributes to whatever is declared here, so guessing `{}` would turn a
        # missing declaration into a wrong one, and the model's own spans would then be refused for
        # carrying attributes it really does compute.
        raise RunTransferError(
            "activity type '%s' declares no computedAttributesSchema, which a run file requires. "
            "A type that computes nothing declares the closed empty struct "
            '{"type": "struct", "items": {}}.' % act.name)
    out = {"name": act.name,
           "parameters": [{"name": p.name, "schema": p.schema} for p in act.parameters],
           "requiredParameters": act.required_parameters,
           "computedAttributesSchema": act.computed_attributes_schema}
    if act.subsystem is not None:
        out["subsystem"] = act.subsystem
    if act.description is not None:
        out["description"] = act.description
    return out


def run_plan(name, start, duration_us, directives, configuration=None, tags=()):
    """The file's `plan` member: a PlanTransfer v2 document keyed by `localId`."""
    return {
        "version": PLAN_TRANSFER_VERSION,
        "name": name,
        "start_time": dt_to_plan_time(start),
        "duration": us_to_interval(duration_us),
        "simulation_arguments": dict(configuration or {}),
        "activities": [{"localId": d.local_id,
                        "type": d.type,
                        "start_offset": us_to_interval(d.start_offset),
                        "arguments": dict(d.arguments or {}),
                        "anchor_id": d.anchor_id,
                        "anchored_to_start": d.anchored_to_start,
                        "name": d.name if d.name is not None else d.local_id,
                        "metadata": dict(d.metadata or {}),
                        "tags": list(d.tags or ())}
                       for d in directives],
        "tags": list(tags or ()),
    }


def run_results(start, duration_us, response, declaration=None):
    """The file's `results` member, from what a `Backend.simulate` returns.

    Two translations happen here and nowhere else:

    * The two profile maps become one, keyed by resource and discriminated by `type`. That is the
      shape `ingestExternalSimulationResults` parses, and keeping the writer's INPUT in the
      backend's shape is what lets any adapter here produce a run file from a result it already has.
    * A span's `directiveId` becomes `directiveLocalId`. A backend echoes back whatever id it was
      given, so a producer that passes each directive's `local_id` as its id gets the file's
      keyspace for free.
    """
    declared = {r.name: r.schema for r in declaration.resource_types} if declaration else {}
    profiles = {}
    for kind, tag in (("realProfiles", "real"), ("discreteProfiles", "discrete")):
        for name, profile in (response.get(kind) or {}).items():
            schema = (profile or {}).get("schema") or declared.get(name)
            if schema is None:
                # merlin dies on a schema-less profile with a NullPointerException deep inside
                # ValueSchemaJsonParser, naming neither the resource nor the model.
                raise RunTransferError("resource '%s' has no schema on its profile and is not declared by "
                                 "this model, so there is nothing to fall back to" % name)
            profiles[name] = {"type": tag, "schema": schema,
                              "segments": list((profile or {}).get("segments") or [])}
    return {"startTime": dt_to_results_time(start), "duration": int(duration_us),
            "profiles": profiles, "spans": [_span_json(s) for s in response.get("spans") or []]}


def _span_json(span):
    out = {"spanId": span["spanId"]}
    if span.get("parentId") is not None:
        out["parentId"] = span["parentId"]
    out["type"] = span["type"]
    out["startOffset"] = span["startOffset"]
    # Absent, never null: merlin reads `duration`, `parentId`, `directiveLocalId` and
    # `computedAttributes` with `optionalField`, so an explicit null is a parse failure rather than
    # an omission. A span with no duration was still running when the simulation ended.
    if "duration" in span:
        out["duration"] = span["duration"]
    local = span.get("directiveLocalId", span.get("directiveId"))
    if local is not None:
        out["directiveLocalId"] = str(local)
    out["arguments"] = dict(span.get("arguments") or {})
    if "computedAttributes" in span:
        out["computedAttributes"] = span["computedAttributes"]
    return out


@dataclass
class RunTransfer:
    """One run file, assembled but not yet serialized.

    Everything the writer needs, in the units a backend works in: microseconds, aware datetimes, a
    `ModelDeclaration`, and the response shape `simulate` returns. `to_json` does the format's part.
    """
    declaration: ModelDeclaration
    mission: str
    plan_name: str
    plan_start: datetime
    plan_duration_us: int
    directives: Sequence[RunDirective] = ()
    #: `{realProfiles, discreteProfiles, spans}`. None writes a plain plan transfer with no results.
    response: Optional[Dict[str, Any]] = None
    configuration: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    plan_tags: Sequence[Any] = ()
    #: Default to the plan's window. A run recorded over a shorter window sets these.
    results_start: Optional[datetime] = None
    results_duration_us: Optional[int] = None

    def to_json(self):
        document = {"kind": RUN_TRANSFER_KIND, "version": RUN_TRANSFER_VERSION,
                    "model": run_model(self.declaration, self.mission, name=self.model_name,
                                       version=self.model_version, description=self.description,
                                       capabilities=self.capabilities),
                    "plan": run_plan(self.plan_name, self.plan_start, self.plan_duration_us,
                                     self.directives, self.configuration, self.plan_tags)}
        if self.response is not None:
            document["results"] = run_results(
                self.results_start or self.plan_start,
                self.plan_duration_us if self.results_duration_us is None
                else self.results_duration_us,
                self.response, self.declaration)
        return document

    @property
    def identity(self):
        """The digest PlanDev will store for this model. See `declaration_digest`."""
        return declaration_digest(self.to_json()["model"])


def parse_run(document):
    """A run file -> a `RunTransfer`. The inverse of `to_json`, and the reason it is here.

    A writer nobody can read back is a writer nobody can test: the round trip is what proves this
    module models the whole format rather than the parts one producer happened to need.
    """
    model, plan = document.get("model") or {}, document.get("plan") or {}
    declaration = declaration_from_json(model)
    response, results = None, document.get("results")
    if results is not None:
        response = {"realProfiles": {}, "discreteProfiles": {},
                    "spans": list(results.get("spans") or [])}
        for name, profile in (results.get("profiles") or {}).items():
            kind = "realProfiles" if profile.get("type") == "real" else "discreteProfiles"
            response[kind][name] = {"schema": profile.get("schema"),
                                    "segments": list(profile.get("segments") or [])}
    return RunTransfer(
        declaration=declaration,
        mission=model.get("mission"),
        description=model.get("description"),
        model_name=model.get("name"),
        model_version=model.get("version"),
        capabilities=model.get("capabilities"),
        plan_name=plan.get("name"),
        plan_start=iso_to_dt(plan.get("start_time")),
        plan_duration_us=interval_to_us(plan.get("duration")),
        configuration=dict(plan.get("simulation_arguments") or {}),
        plan_tags=list(plan.get("tags") or ()),
        directives=[RunDirective(local_id=a.get("localId"), type=a.get("type"),
                                 start_offset=interval_to_us(a.get("start_offset")),
                                 arguments=dict(a.get("arguments") or {}),
                                 name=a.get("name"), metadata=dict(a.get("metadata") or {}),
                                 tags=list(a.get("tags") or ()), anchor_id=a.get("anchor_id"),
                                 anchored_to_start=a.get("anchored_to_start", True))
                    for a in plan.get("activities") or []],
        response=response,
        results_start=results_time_to_dt(results["startTime"]) if results else None,
        results_duration_us=results.get("duration") if results else None)


# -- serialization ------------------------------------------------------------------------------------
def dumps_run(document, indent=2):
    """Serialize a run file. Never emits `Infinity`, `-Infinity` or `NaN`.

    `json.dumps` writes all three as bare tokens, which are not JSON: `JSON.parse` and ajv reject
    them, so a file carrying one is refused as malformed before anything can say which resource
    produced it. The portable spelling of an infinity is `1e400` -- valid JSON, and a double
    infinity in Java, Python and JavaScript alike -- so that is what this writes, substituting a
    random placeholder rather than rewriting the serialized text, which would also match the
    characters `Infinity` inside a string value.

    A NaN has no spelling at all. It is refused rather than written as an infinity, because those
    are different numbers and a producer silently shipping one for the other is worse than a file
    that never leaves.
    """
    token = " %s " % os.urandom(8).hex()
    substitutions = {}

    def mark(value):
        if isinstance(value, float) and not math.isfinite(value):
            if math.isnan(value):
                raise RunTransferError(
                    "a NaN cannot be written to a run file: JSON has no NaN, and `1e400` -- the "
                    "only portable spelling of a non-finite number -- is an infinity, not a NaN")
            placeholder = "%s%s" % (token, "pos" if value > 0 else "neg")
            substitutions[json.dumps(placeholder)] = "1e400" if value > 0 else "-1e400"
            return placeholder
        if isinstance(value, dict):
            return {k: mark(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [mark(v) for v in value]
        return value

    text = json.dumps(mark(document), indent=indent, ensure_ascii=False, allow_nan=False)
    for placeholder, literal in substitutions.items():
        text = text.replace(placeholder, literal)
    return text + "\n"


def write_run(document, path):
    """Write a run file to `path`, UTF-8. Returns the path, so a CLI can report where it went."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(dumps_run(document))
    return path


def _refuse_json_constant(token):
    raise RunTransferError(
        "`%s` is not JSON. Python's parser accepts it and nothing downstream of this process does, "
        "so reading it here would only hide the problem one step further on. Write `1e400`."
        % token)


def read_run(path):
    """Read a run file, refusing the non-JSON tokens Python's parser would otherwise accept."""
    with open(path, encoding="utf-8") as handle:
        return json.loads(handle.read(), parse_constant=_refuse_json_constant)


# -- pre-flight ---------------------------------------------------------------------------------------
def run_problems(document):
    """Every problem in a run file that can be seen from the file alone, as messages.

    This is the gate's rule set applied before upload rather than after: the same closed-world check
    `ExternalResultsGate` makes -- nothing undeclared, nothing non-finite, nothing outside the
    simulation window, no dangling parent -- plus the importer's cross-references, which the gate
    never sees because the importer resolves them first.

    What it cannot see is anything about PlanDev: whether a model of this name already exists,
    whether the plan name is taken (plan names are globally unique), whether the caller may write.
    Those are the importer's answers and need a server to give them.

    Returns messages rather than raising, so a producer can fix a run in one pass instead of one
    round trip per problem. `check_run` is the raising form.
    """
    problems = []
    model = document.get("model") or {}
    acts = {a.get("name"): a for a in model.get("activityTypes") or []}

    if document.get("kind") != RUN_TRANSFER_KIND:
        problems.append("`kind` is %r; a run file's kind must be exactly %r"
                        % (document.get("kind"), RUN_TRANSFER_KIND))
    if document.get("version") != RUN_TRANSFER_VERSION:
        problems.append("`version` is %r; this writer produces version %r"
                        % (document.get("version"), RUN_TRANSFER_VERSION))

    for name, act in acts.items():
        if not _TS_IDENTIFIER.match(name or ""):
            problems.append("activity type '%s' is not a legal TypeScript identifier, so the "
                            "generated constraint and scheduling typings will not compile" % name)
        seen = set()
        for parameter in act.get("parameters") or []:
            if not _TS_IDENTIFIER.match(parameter.get("name") or ""):
                problems.append("parameter '%s' of activity type '%s' is not a legal TypeScript "
                                "identifier" % (parameter.get("name"), name))
            if parameter.get("name") in seen:
                problems.append("activity type '%s' declares parameter '%s' twice"
                                % (name, parameter.get("name")))
            seen.add(parameter.get("name"))
        for required in act.get("requiredParameters") or []:
            if required not in seen:
                problems.append("activity type '%s' requires parameter '%s', which it does not "
                                "declare" % (name, required))
    resources = {}
    for resource in model.get("resourceTypes") or []:
        if not _RESOURCE_NAME.match(resource.get("name") or ""):
            problems.append("resource name '%s' is empty, over 255 characters, or contains control "
                            "characters" % resource.get("name"))
        resources[resource.get("name")] = resource.get("schema")

    local_ids = []
    for index, activity in enumerate((document.get("plan") or {}).get("activities") or []):
        local_id = activity.get("localId")
        where = "directive %s" % (local_id if local_id is not None else "#%d" % index)
        if local_id in local_ids:
            problems.append("duplicate localId '%s'; a localId must be unique within the file"
                            % local_id)
        local_ids.append(local_id)
        if activity.get("type") not in acts:
            problems.append("%s has type '%s', which this file does not declare"
                            % (where, activity.get("type")))
        else:
            problems += _argument_problems(where, acts[activity["type"]], activity.get("arguments"))
    for activity in (document.get("plan") or {}).get("activities") or []:
        anchor = activity.get("anchor_id")
        if anchor is None:
            continue
        if anchor == activity.get("localId"):
            problems.append("directive %s is anchored to itself" % anchor)
        elif anchor not in local_ids:
            problems.append("directive %s is anchored to '%s', which is not a localId in this file"
                            % (activity.get("localId"), anchor))

    results = document.get("results")
    if results is not None:
        problems += _results_problems(results, acts, resources, set(local_ids))
    return problems


def _argument_problems(where, act, arguments):
    """The gate's argument check: nothing undeclared, nothing type-wrong, nothing required missing."""
    problems = []
    declared = {p.get("name"): p.get("schema") for p in act.get("parameters") or []}
    for name, value in (arguments or {}).items():
        if name not in declared:
            problems.append("%s has argument '%s', which is not a declared parameter of '%s'"
                            % (where, name, act.get("name")))
        else:
            problem = nonconformance(value, declared[name])
            if problem:
                problems.append("%s argument '%s' %s" % (where, name, problem))
    for required in act.get("requiredParameters") or []:
        if required not in (arguments or {}):
            problems.append("%s is missing required parameter '%s'" % (where, required))
    return problems


def _results_problems(results, acts, resources, local_ids):
    problems = []
    duration = results.get("duration")
    for name, profile in (results.get("profiles") or {}).items():
        if name not in resources:
            problems.append("resource '%s' is not a registered resource type of this model" % name)
        elif profile.get("schema") != resources[name]:
            problems.append("resource '%s' has schema %s on its profile but is declared as %s"
                            % (name, json.dumps(profile.get("schema")),
                               json.dumps(resources[name])))
        total = 0
        for index, segment in enumerate(profile.get("segments") or []):
            if not _is_int(segment.get("duration")) or segment["duration"] < 0:
                problems.append("resource '%s' segment %d has duration %r; a segment's duration is "
                                "non-negative integer microseconds"
                                % (name, index, segment.get("duration")))
                continue
            total += segment["duration"]
            # No `dynamics` at all is a GAP -- "this resource has no value here" -- which is
            # legitimate and must not be reported as a missing field.
            if "dynamics" not in segment:
                continue
            if profile.get("type") == "real":
                problems += _real_dynamics_problems(name, index, segment["dynamics"])
            else:
                problem = nonconformance(segment["dynamics"], profile.get("schema") or {})
                if problem:
                    problems.append("resource '%s' segment %d value does not match its schema: %s"
                                    % (name, index, problem))
        if _is_int(duration) and total > duration:
            problems.append("resource '%s' profile runs %dus, past the simulation duration of %dus"
                            % (name, total, duration))

    span_ids, parents = set(), {}
    for span in results.get("spans") or []:
        span_id = span.get("spanId")
        where = "span %s" % span_id
        if span_id in span_ids:
            problems.append("duplicate spanId %s" % span_id)
        span_ids.add(span_id)
        if span.get("parentId") is not None:
            parents[span_id] = span["parentId"]
        if span.get("type") not in acts:
            problems.append("%s has type '%s', which is not a registered activity type"
                            % (where, span.get("type")))
        else:
            problems += _argument_problems(where, acts[span["type"]], span.get("arguments"))
            if "computedAttributes" in span:
                problem = nonconformance(span["computedAttributes"],
                                         acts[span["type"]].get("computedAttributesSchema") or {})
                if problem:
                    problems.append("%s computed attributes %s" % (where, problem))
        # merlin tells a finished span from an unfinished one by the presence of BOTH `duration` and
        # `computedAttributes`, so the two travel together or not at all.
        if ("duration" in span) != ("computedAttributes" in span):
            problems.append(
                "%s has %s but not %s: a finished span carries both, an unfinished one carries "
                "neither" % (where, "duration" if "duration" in span else "computedAttributes",
                             "computedAttributes" if "duration" in span else "duration"))
        local = span.get("directiveLocalId")
        if local is not None and local not in local_ids:
            problems.append("%s claims directiveLocalId '%s', which is not a directive in this file"
                            % (where, local))
        if local is not None and span.get("parentId") is not None:
            problems.append("%s has both a parentId and a directiveLocalId; a span is either a "
                            "directive's own span or a child of another span" % where)
        start = span.get("startOffset")
        if not _is_int(start) or start < 0:
            problems.append("%s starts at %r; a startOffset is non-negative integer microseconds"
                            % (where, start))
        elif _is_int(duration) and start > duration:
            problems.append("%s starts at %dus, past the simulation duration of %dus"
                            % (where, start, duration))
        if "duration" in span:
            if not _is_int(span["duration"]) or span["duration"] < 0:
                problems.append("%s has duration %r; a span's duration is non-negative integer "
                                "microseconds" % (where, span["duration"]))
            elif _is_int(start) and _is_int(duration) and start + span["duration"] > duration:
                problems.append("%s runs to %dus, past the simulation duration of %dus"
                                % (where, start + span["duration"], duration))
    for span_id, parent in parents.items():
        if parent not in span_ids:
            problems.append("span %s has parentId %s, which is not a span in this result"
                            % (span_id, parent))
    for span_id in parents:
        seen, cursor = {span_id}, parents.get(span_id)
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            cursor = parents.get(cursor)
        if cursor is not None:
            problems.append("span %s is part of a parent cycle" % span_id)
    return problems


def _real_dynamics_problems(name, index, dynamics):
    if not isinstance(dynamics, dict):
        return ["resource '%s' segment %d has dynamics %r; a real segment carries {initial, rate}"
                % (name, index, dynamics)]
    problems = []
    for part in ("initial", "rate"):
        value = dynamics.get(part)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append("resource '%s' segment %d has a non-numeric `%s` (%r)%s"
                            % (name, index, part, value,
                               " -- a NaN serialized to null upstream looks exactly like this"
                               if value is None else ""))
        elif not math.isfinite(value):
            problems.append("resource '%s' has a non-finite %s (%s)" % (name, part, value))
    return problems


def check_run(document):
    """`run_problems`, raising. Returns the document, so it can be used in a write expression."""
    problems = run_problems(document)
    if problems:
        raise RunTransferError("this run file will be refused:\n  - %s" % "\n  - ".join(problems))
    return document
