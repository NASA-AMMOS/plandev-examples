#!/usr/bin/env python3
"""The reusable half of the PlanDev external-model contract.

Every external-model backend -- whatever language the MODEL is written in -- has to speak the same
four endpoints, resolve the same `?model=` key, fill the same defaults, typecheck against the same
ValueSchemas, and publish the same kind of identity hash. That is a lot of contract, and none of it
is model-specific. This module owns all of it so a backend can be a declaration plus a `simulate`.

It exists because it was NOT here first. The Python and Blackbird adapters were written
independently against the same spec and drifted: `nonconformance`, the ValueSchema typechecker,
appeared six times in one and zero times in the other, so an audit that found and fixed a missing
typecheck in `/validate` fixed it in exactly one of the two. `iso_to_dt` was a verbatim duplicate.
`effective_args`, `introspect`, `models_list` and a hand-rolled `BaseHTTPRequestHandler` each
existed twice, subtly differently. A third adapter would have made three copies.

What a backend supplies (see `Backend`):
  * `declaration()` -- activity types, resource types, configuration parameters.
  * `simulate(request)` -- given an ALREADY-NORMALIZED request, return profiles and spans.
  * `deep_validate(subjects)` -- OPTIONAL, for checks this layer cannot make.

What this module supplies:
  * HTTP: routing, `?model=` resolution, JSON error envelopes, threaded serving.
  * `nonconformance` -- the ValueSchema typechecker.
  * defaults, effective arguments, effective configuration.
  * generic `/validate` -- missing, unrecognized and type-wrong parameters, attributed to subjects.
  * `identity_hash` -- the attestation merlin stores.
  * response validation -- catch a malformed result HERE, where the message can say what happened,
    rather than downstream in merlin's ingest gate or, worse, nowhere.

The wire contract (`?model=` names the model; optional when only one is configured):
  GET  /models                 -> {models:[{key,name,version,identityHash}]}
  GET|POST /introspect         -> {activityTypes, resourceTypes, parameters, identityHash}
  POST /simulate   {planStart, duration(us), configuration, directives:[{id,type,startOffset,arguments}]}
                               -> {realProfiles, discreteProfiles, spans}
  POST /validate   {activities:[{type,arguments}], effectiveOnly}
                               -> {results:[{valid, notices:[{subjects,message}], effectiveArguments}]}

stdlib only.
"""
import hashlib
import json
import math
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse, parse_qs

__all__ = [
    "BadRequest", "NotFound", "ModelError",
    "iso_to_dt", "nonconformance",
    "Parameter", "ActivityType", "ResourceType", "Declaration",
    "Directive", "SimulationRequest", "ValidationSubject",
    "Backend", "ExecBackend",
    "Registry", "check_response", "digest", "make_handler", "serve",
]

SCHEMA_TYPES = frozenset(("real", "int", "duration", "boolean", "string", "path",
                          "variant", "series", "struct"))


# ---------- errors -------------------------------------------------------------------------------
class BadRequest(Exception):
    """A CALLER error -- reported as 400 with the offending directive named, not as a 500.

    The distinction matters operationally: a 500 sends an operator looking at the adapter's logs,
    and a 400 tells the planner their plan is wrong. Getting it backwards wastes both their time.
    """


class NotFound(BadRequest):
    """A caller error that is specifically 'no such thing here' -- reported as 404."""


class ModelError(Exception):
    """The MODEL produced something the contract cannot carry -- reported as 500.

    Not a caller error: the request was fine and the backend answered wrongly. Raised by
    `check_response` before anything is serialized, so the message can name the offending span or
    segment instead of leaving merlin to reject an opaque blob.
    """


# ---------- time ---------------------------------------------------------------------------------
def iso_to_dt(iso):
    """An ISO-8601 instant (with `Z` or an offset) -> an aware UTC datetime."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


# ---------- ValueSchema conformance ---------------------------------------------------------------
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


# ---------- declaration ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Parameter:
    """One declared parameter: a name, a ValueSchema, and possibly a default.

    `default is None` means NO DEFAULT, which is also what makes the parameter required. Both
    shipped adapters already used that convention (a Python `None` default, a Blackbird dictionary
    entry with no `default` key), and PlanDev has no way to express "required, but defaults to
    null" anyway. `required` is available as an explicit override for a model that needs the two
    decoupled.
    """
    name: str
    schema: Dict[str, Any]
    default: Any = None
    required: Optional[bool] = None

    @property
    def is_required(self):
        return (self.default is None) if self.required is None else self.required


@dataclass(frozen=True)
class ActivityType:
    """One activity type. `parameters` is ORDERED and the order is load-bearing -- see
    `Declaration.digest_payload` for why PlanDev cares."""
    name: str
    parameters: Sequence[Parameter]
    computed_attributes_schema: Optional[Dict[str, Any]] = None

    @property
    def required_parameters(self):
        return [p.name for p in self.parameters if p.is_required]

    @property
    def by_name(self):
        return {p.name: p for p in self.parameters}


@dataclass(frozen=True)
class ResourceType:
    name: str
    schema: Dict[str, Any]


# ---------- capabilities --------------------------------------------------------------------------
# What PlanDev may DO with a model, as opposed to what the model is. PlanDev cannot infer any of this
# from the declared types: nothing in a list of activity types says whether the model places
# activities of its own during simulation, or whether the backend can read its framework's native
# plan format. Merlin stores whatever is declared here in mission_model.external_capabilities.
#
# Every capability is an OBJECT, never a bare boolean, so that an unsupported one has somewhere to
# carry the backend's own explanation. That is what keeps plandev-ui free of branches naming a
# particular framework: it renders "unavailable because <the backend's sentence>" without knowing
# what Blackbird is. An ABSENT capability means unsupported.

#: PlanDev's own scheduler may place activities in plans using this model. False for a
#: forward-dispatch framework, which places activities during its own simulation -- running PlanDev's
#: scheduler against one pits two schedulers against each other.
PLANDEV_SCHEDULING = "plandevScheduling"
#: The backend can read its framework's native plan format and return directives.
PLAN_IMPORT = "planImport"


def unsupported(reason):
    """A capability the backend does not offer, with the sentence the UI should show for it."""
    return {"supported": False, "reason": reason}


def supported(**detail):
    """A capability the backend offers, plus whatever that capability needs to describe itself."""
    return dict(detail, supported=True)


class Declaration:
    """Everything PlanDev stores about one model, plus the operations that follow from it.

    A backend builds one of these and this module does the rest: introspection, defaults,
    validation, request normalization and the identity hash all read from here.
    """

    def __init__(self, key, activity_types, resource_types=(), config_parameters=(),
                 name=None, version="1.0.0", digest_payload=None, capabilities=None):
        self.key = key
        self.name = name or key
        self.version = version
        self.activity_types = list(activity_types)
        self.resource_types = list(resource_types)
        self.config_parameters = list(config_parameters)
        # What PlanDev may DO with this model, as opposed to what the model is. See `unsupported`.
        self.capabilities = dict(capabilities or {})
        self._acts = {a.name: a for a in self.activity_types}
        # `digest_payload`: an override for a model that has ALREADY SHIPPED. The identity hash is
        # an attestation merlin STORES; changing the bytes it is computed from invalidates every
        # deployment of that model even though nothing about the model moved. So a published model
        # pins the payload its hash was minted from and a new one gets the canonical form below.
        self._digest_payload = digest_payload

    # -- introspection ----------------------------------------------------------------------------
    def __contains__(self, typ):
        return typ in self._acts

    def activity_type(self, typ):
        return self._acts.get(typ)

    def introspect(self):
        return {
            "activityTypes": [
                {"name": a.name,
                 "parameters": [{"name": p.name, "schema": p.schema} for p in a.parameters],
                 "requiredParameters": a.required_parameters,
                 # Declared so merlin's gate accepts what the model attaches to each span. An
                 # undeclared computed attribute is rejected exactly like an undeclared argument.
                 "computedAttributesSchema": a.computed_attributes_schema}
                for a in self.activity_types],
            "resourceTypes": [{"name": r.name, "schema": r.schema} for r in self.resource_types],
            # Simulation configuration: model-wide settings a planner edits per plan, distinct from
            # an activity's arguments. PlanDev stores these in mission_model_parameters and sends
            # them back as `configuration`.
            "parameters": [{"name": p.name, "schema": p.schema} for p in self.config_parameters],
            # Which PlanDev features apply to this model. PlanDev cannot infer these from the type
            # surface -- nothing in a model's activity types says whether it places activities of its
            # own during simulation -- and an absent capability means UNSUPPORTED.
            "capabilities": self.capabilities,
            "identityHash": self.identity_hash(),
        }

    def summary(self):
        return {"key": self.key, "name": self.name, "version": self.version,
                "identityHash": self.identity_hash()}

    # -- identity ---------------------------------------------------------------------------------
    def digest_payload(self):
        """The canonical digest input: everything PlanDev STORES about this model.

        requiredParameters and defaults are included deliberately. PlanDev persists
        requiredParameters in activity_type and merlin's gate enforces them, so flipping a
        parameter between required and optional changes what PlanDev believes without changing the
        model's schemas -- and merlin's drift check would never notice.

        Parameters are hashed in DECLARATION ORDER. Order is not cosmetic: merlin assigns each
        parameter an `order` from its index in the introspection array
        (ResponseSerializers.serializeParameters), persists it, reads activity types back sorted by
        it (GetActivityTypesAction), and plandev-ui lays the argument form out in that order.
        Sorting here would hide a reordered declaration from the attestation, leaving the stored
        order stale and the form rendering in the old sequence.

        Computed-attribute schemas are stored in activity_type too, so a change to them is drift
        the attestation must catch -- otherwise the gate starts rejecting spans against a stale
        schema.
        """
        return {
            "acts": {a.name: {"params": [[p.name, p.schema, p.default] for p in a.parameters],
                              "required": a.required_parameters,
                              "computed": a.computed_attributes_schema}
                     for a in self.activity_types},
            "res": {r.name: r.schema for r in self.resource_types},
            # Config parameters are part of what PlanDev stores (mission_model_parameters), so they
            # belong in the attestation for the same reason activity and resource types do.
            "cfg": [[p.name, p.schema, p.default] for p in self.config_parameters],
            # And so are capabilities. The attestation exists because PlanDev keeps a COPY of
            # something the backend owns, and the copy can go stale under a redeployed adapter --
            # which is as true of capabilities as of types. Leaving them out would create a second
            # unattested copy with exactly the failure mode the first one is guarded against: a
            # backend that starts placing its own activities while PlanDev still offers to schedule
            # for it, with two schedulers then writing the same plan.
            "caps": self.capabilities,
        }

    def identity_hash(self):
        payload = self._digest_payload(self) if self._digest_payload else self.digest_payload()
        return digest(payload)

    # -- effective arguments ------------------------------------------------------------------------
    def effective_args(self, typ, args):
        """Declared parameters only, with defaults filled in.

        An explicit JSON null counts as ABSENT, not as a supplied value -- otherwise a null sails
        past default resolution and reaches the model's arithmetic as None. Undeclared names are
        dropped rather than echoed: they would otherwise ride through into the span's arguments,
        where merlin's ingest gate flags every span for carrying an argument the model never
        declared.
        """
        act = self._acts.get(typ)
        if act is None:
            return {}
        supplied = {k: v for k, v in (args or {}).items() if v is not None}
        eff = {}
        for p in act.parameters:
            if p.name in supplied:
                eff[p.name] = supplied[p.name]
            elif p.default is not None:
                eff[p.name] = p.default
        return eff

    def undeclared(self, typ, args):
        act = self._acts.get(typ)
        declared = set(act.by_name) if act else set()
        return [k for k in (args or {}) if k not in declared]

    def effective_config(self, configuration):
        """Declared configuration only, defaults filled.

        Same discipline as activity arguments: an unknown key is REPORTED rather than silently
        honoured -- a casing typo in a stored configuration would otherwise simulate green with the
        parameter at its default, which looks exactly like the model ignoring it -- and a null means
        'use the default'.

        A declared parameter with no adapter-side default comes out as None. That is not an
        oversight: it is how a backend says "I was not told, so leave whatever the model itself
        defaults to alone."
        """
        supplied = {k: v for k, v in (configuration or {}).items() if v is not None}
        declared = {p.name for p in self.config_parameters}
        for k in supplied:
            if k not in declared:
                raise BadRequest("unknown configuration parameter '%s'" % k)
        out = {}
        for p in self.config_parameters:
            v = supplied.get(p.name, p.default)
            problem = nonconformance(v, p.schema)
            if problem:
                raise BadRequest("configuration parameter '%s' %s" % (p.name, problem))
            out[p.name] = v
        return out

    # -- validation ---------------------------------------------------------------------------------
    def validate_one(self, typ, args, effective_only=False):
        """The generic half of `/validate`: everything checkable from the declaration alone.

        A backend layers its own findings on top via `Backend.deep_validate`; it does not replace
        this. Notices carry `subjects` -- the parameter names they are about -- so plandev-ui can
        render them inline on the offending field instead of as an anonymous banner.
        """
        act = self._acts.get(typ)
        if act is None:
            return {"valid": False,
                    "notices": [{"subjects": [], "message": "unknown activity type '%s'" % typ}],
                    "effectiveArguments": None}
        eff = self.effective_args(typ, args)
        if effective_only:
            # The editor asks for effective arguments while a form is still half-filled; that is not
            # the moment to paint it red.
            return {"valid": True, "notices": [], "effectiveArguments": eff}
        notices = []
        args = args or {}
        for p in act.parameters:
            if p.is_required and args.get(p.name) is None:
                notices.append({"subjects": [p.name],
                                "message": "missing required parameter '%s'" % p.name})
        for name in self.undeclared(typ, args):
            notices.append({"subjects": [name], "message": "unrecognized parameter '%s'" % name})
        schemas = act.by_name
        for name, value in args.items():
            if name in schemas and value is not None:
                problem = nonconformance(value, schemas[name].schema)
                if problem:
                    notices.append({"subjects": [name],
                                    "message": "parameter '%s' %s" % (name, problem)})
        return {"valid": len(notices) == 0, "notices": notices, "effectiveArguments": eff}

    # -- request normalization ------------------------------------------------------------------------
    def normalize(self, req):
        """A raw `/simulate` body -> a `SimulationRequest` a backend can trust.

        Every check that can be made from the declaration is made HERE, once, before the model is
        started: the simulation window, the configuration, and each directive's type, required
        parameters and argument types. A backend never sees an unknown activity type, a missing
        required parameter, or a value that does not fit its own declared schema -- so it does not
        have to decide whether the resulting failure is a 400 or a 500, and a type-wrong argument
        cannot reach the model at all.
        """
        if "duration" not in req:
            raise BadRequest("request has no simulation `duration`")
        try:
            sim_dur = int(req["duration"])
        except (TypeError, ValueError):
            raise BadRequest("simulation duration must be integer microseconds, got %r"
                             % (req["duration"],))
        if sim_dur < 0:
            raise BadRequest("simulation duration must be >= 0 (got %d)" % sim_dur)
        cfg = self.effective_config(req.get("configuration"))

        plan_start_iso = req.get("planStart")
        plan_start = None
        if plan_start_iso is not None:
            try:
                plan_start = iso_to_dt(plan_start_iso)
            except (TypeError, ValueError) as e:
                raise BadRequest("planStart %r is not an ISO-8601 instant: %s" % (plan_start_iso, e))

        directives = []
        for d in req.get("directives", []):
            typ = d.get("type")
            act = self._acts.get(typ)
            if act is None:
                raise BadRequest("directive %s has unknown activity type '%s'" % (d.get("id"), typ))
            eff = self.effective_args(typ, d.get("arguments") or {})
            for p in act.parameters:
                if p.is_required and p.name not in eff:
                    raise BadRequest("directive %s (%s) is missing required parameter '%s'"
                                     % (d.get("id"), typ, p.name))
                problem = nonconformance(eff.get(p.name), p.schema)
                if problem:
                    raise BadRequest("directive %s (%s) parameter '%s' %s"
                                     % (d.get("id"), typ, p.name, problem))
            if "startOffset" not in d:
                raise BadRequest("directive %s (%s) has no startOffset" % (d.get("id"), typ))
            try:
                start = int(d["startOffset"])
            except (TypeError, ValueError):
                raise BadRequest("directive %s (%s) startOffset must be integer microseconds, got %r"
                                 % (d.get("id"), typ, d["startOffset"]))
            directives.append(Directive(id=d.get("id"), type=typ, start_offset=start,
                                        arguments=eff, raw=d))
        return SimulationRequest(duration=sim_dur, configuration=cfg, directives=directives,
                                 plan_start_iso=plan_start_iso, _plan_start=plan_start, raw=req)


def digest(payload):
    """16 hex characters of sha256 over `payload` canonicalized as sorted-key JSON.

    Stable across restarts by construction: nothing here reads the clock, an object id, or a
    salted dict iteration order. `sort_keys` neutralizes the insertion order of every mapping, and
    `default=str` keeps a stray non-JSON value (a Blackbird type object, say) from turning an
    attestation into a crash.
    """
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------- normalized request ---------------------------------------------------------------------
@dataclass(frozen=True)
class Directive:
    """One directive, with `arguments` already defaulted, filtered and typechecked."""
    id: Any
    type: str
    start_offset: int
    arguments: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class SimulationRequest:
    duration: int
    configuration: Dict[str, Any]
    directives: List[Directive]
    plan_start_iso: Optional[str] = None
    _plan_start: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def plan_start(self):
        """The plan's absolute start, as an aware UTC datetime.

        Optional on the wire, because a model whose spans and profiles are all relative offsets
        never needs it -- so it is only demanded from the backends that actually read it, and
        asking for one that was not sent is a 400 naming the missing field rather than a
        `NoneType` TypeError at a stack frame five calls deep.
        """
        if self._plan_start is None:
            raise BadRequest("request has no `planStart`, which this model needs to place "
                             "activities on an absolute timeline")
        return self._plan_start


@dataclass
class ValidationSubject:
    """One activity handed to `Backend.deep_validate`.

    `notices` is what the generic layer already found. A backend whose deep check is expensive --
    or whose model would simply crash on input this layer has already rejected -- skips any subject
    that arrives non-empty.
    """
    index: int
    type: str
    arguments: Dict[str, Any]
    effective_arguments: Dict[str, Any]
    notices: List[Dict[str, Any]]


# ---------- backend interface -------------------------------------------------------------------
class Backend:
    """What a model must provide. Everything else is this module's job.

    Deliberately small: three methods, one of them optional. If something can be derived from the
    declaration it belongs in `Declaration`, not here -- that is the whole point of the split.
    """

    def declaration(self):
        """-> Declaration. Called per request, so cache it if building one is expensive."""
        raise NotImplementedError

    def simulate(self, request):
        """`request` is a NORMALIZED `SimulationRequest`: the configuration is resolved and
        typechecked, and every directive's arguments are defaulted, filtered to declared names and
        typechecked against their schemas.

        Return {realProfiles, discreteProfiles, spans}. Raise `BadRequest` for anything still wrong
        with the caller's request that only the model can know.
        """
        raise NotImplementedError

    def deep_validate(self, subjects):
        """OPTIONAL. Model-specific checks the generic layer cannot make.

        Called once for the whole batch, so a backend that has to spawn a process can amortize it.
        `subjects` excludes unknown activity types and is empty when the caller asked for
        `effectiveOnly`. Return a list of extra notices per subject (parallel to `subjects`), or
        None for "nothing to add".
        """
        return None


# ---------- response validation ---------------------------------------------------------------------
def _foreign_type_hint(value):
    """A note naming the usual culprit, when `value` is of a type json cannot serialize.

    Almost always numpy, and worth spelling out because the way it fails is genuinely misleading:
    `numpy.float64` IS a subclass of Python's float, so every real-valued channel serializes
    perfectly and the casts at the boundary look like belt-and-braces. `numpy.int64` and
    `numpy.bool_` are NOT subclasses of int and bool, so the first integer- or boolean-valued
    channel anyone adds is where it bites -- long after the pattern looked safe.
    """
    module = (type(value).__module__ or "").split(".")[0]
    if module == "numpy":
        return (" -- numpy scalars and arrays are not JSON. Cast at the boundary: int(x), float(x),"
                " bool(x), or x.tolist() for an array. (numpy's float64 is a Python float subclass"
                " and passes, which is why this only surfaces on an int- or bool-valued channel.)")
    if module == "decimal":
        return " -- Decimal is not JSON; cast with float(x), accepting the precision that implies."
    return " -- only null, booleans, numbers, strings, lists and objects can be sent."


def _first_unsendable(value, path=""):
    """`(path, reason)` for the first value inside `value` that cannot go on the wire, or None.

    One walk, two failure modes, because both die anonymously otherwise:

    * A NON-FINITE number. `json.dumps` emits a bare `NaN`/`Infinity`, which is not legal JSON, so
      merlin's parser rejects the WHOLE response and the ingest dies before anything can say which
      resource produced it.
    * A value of a type json cannot serialize at all. `json.dumps` raises a `TypeError` naming only
      the type -- "Object of type int64 is not JSON serializable" -- with no resource, no span and
      no path. That is the same unhelpfulness the non-finite check exists to prevent, one type over.
    """
    if isinstance(value, float):
        # Checked before the general case: bool is a subclass of int, and numpy's float64 is a
        # subclass of float, so both are legitimately sendable and must not fall through.
        return (path or "<value>", "a non-finite number (NaN or Infinity)") \
            if not math.isfinite(value) else None
    if value is None or isinstance(value, (bool, int, str)):
        return None
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                return (path or "<value>",
                        "a %s key (%r); JSON object keys must be strings" % (type(k).__name__, k))
            found = _first_unsendable(v, "%s.%s" % (path, k))
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            found = _first_unsendable(v, "%s[%d]" % (path, i))
            if found:
                return found
        return None
    return (path or "<value>", "a %s%s" % (type(value).__name__, _foreign_type_hint(value)))


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _int_complaint(what, value):
    """Why `value` is not an integer, in a way that is not baffling when it plainly looks like one.

    `numpy.int64(10)` is an integer to every reader and not an `int` to Python, so "has a
    non-integer duration np.int64(10)" reads as a bug in the checker rather than in the model.
    """
    return "%s %r%s" % (what, value, _foreign_type_hint(value) if not isinstance(value, (int, float))
                        else "")


def check_response(response):
    """Refuse to serialize a simulation result the model got structurally wrong.

    All three failure modes below are silent, or nearly so, if they are not caught here:

    * A non-finite number. `json.dumps` would emit a bare `NaN`/`Infinity`, which is not legal
      JSON; merlin's parser rejects the WHOLE response, so the ingest dies before the gate's own
      non-finite check can report anything useful. Failing here means the message can name the
      resource or span that produced it.
    * A value of a type json cannot serialize -- a numpy scalar or array, most often. `json.dumps`
      raises a `TypeError` naming only the type ("Object of type int64 is not JSON serializable"),
      with no resource, no span and no path, which is the same unhelpfulness as the case above.
    * A span that is half-finished. Merlin tells a finished span from an unfinished one by the
      presence of BOTH `duration` and `computedAttributes` (PostgresResultsCellRepository), so the
      two travel together or not at all. A span carrying computed attributes with no duration
      claims to have produced its final values while still running, and merlin reads it as
      finished-with-no-end.
    """
    for kind in ("realProfiles", "discreteProfiles"):
        profiles = response.get(kind) or {}
        if not isinstance(profiles, dict):
            raise ModelError("%s must be an object of resource name -> profile, got %r"
                             % (kind, type(profiles).__name__))
        for name, prof in profiles.items():
            for i, seg in enumerate((prof or {}).get("segments") or []):
                if not _is_int(seg.get("duration")):
                    raise ModelError("%s '%s' segment %d %s" % (
                        kind, name, i, _int_complaint("has a non-integer duration",
                                                      seg.get("duration"))))
                bad = _first_unsendable(seg.get("dynamics"))
                if bad:
                    path, reason = bad
                    raise ModelError("resource '%s' segment %d cannot be sent as JSON: %s at %s"
                                     % (name, i, reason, path))

    for span in response.get("spans") or []:
        sid = span.get("spanId")
        finished, has_computed = "duration" in span, "computedAttributes" in span
        if finished != has_computed:
            raise ModelError(
                "span %s has %s but not %s: a finished span carries both `duration` and "
                "`computedAttributes`, an unfinished one carries neither"
                % (sid, "duration" if finished else "computedAttributes",
                   "computedAttributes" if finished else "duration"))
        if not _is_int(span.get("startOffset")):
            raise ModelError("span %s %s" % (
                sid, _int_complaint("has a non-integer startOffset", span.get("startOffset"))))
        if finished and not _is_int(span.get("duration")):
            raise ModelError("span %s %s" % (
                sid, _int_complaint("has a non-integer duration", span.get("duration"))))
        for part in ("arguments", "computedAttributes"):
            bad = _first_unsendable(span.get(part))
            if bad:
                path, reason = bad
                raise ModelError("span %s %s cannot be sent as JSON: %s at %s"
                                 % (sid, part, reason, path))
    return response


# ---------- sampled output -> profiles ---------------------------------------------------------------
# A fixed-step simulator reports SAMPLES -- a value at t0, another at t1 -- while PlanDev stores
# SEGMENTS, each a duration plus dynamics that hold over it. Converting between the two is generic,
# and getting it wrong is silent in both directions, so it lives here rather than in each adapter.
# Blackbird does not need this (its engine reports segments natively); Basilisk and any fixed-step
# backend do.
def snap_up(time_us, step_us):
    """The first grid point at or after `time_us`.

    CEIL, not nearest. A fixed-step simulator applies a scheduled effect at the first step at or
    after its time, so ceil is what the simulator will actually do; rounding to nearest reports an
    activity starting up to half a step BEFORE its effect was applied, which is a timeline and a
    profile disagreeing with each other by a step, with nothing anywhere to flag it.
    """
    return -((-time_us) // step_us) * step_us


def real_segments(times_us, values, sim_duration_us):
    """Samples -> linear segments covering [0, sim_duration_us] exactly.

    Two things here are not obvious, and both have already cost real debugging on real adapters.

    RATE IS THE SECANT between consecutive samples, `(v1 - v0) / dt`, never the model's instantaneous
    derivative. PlanDev evaluates a real profile as `initial + rate * elapsedSeconds`, so a segment's
    computed end value must equal the next segment's `initial`. Any saturation or nonlinearity -- a
    battery reaching capacity, a buffer filling -- makes the instantaneous derivative disagree, and
    the profile then contradicts itself between segments with nothing raised anywhere.

    THE FINAL SEGMENT IS EXTENDED to close the window. A fixed-step simulator halts at the last step
    at or before the requested stop time, so its samples fall short of the plan's duration by the
    sub-step remainder -- and merlin's ingest gate rejects a profile that does not cover the
    simulation. It is held FLAT rather than extrapolated along the last secant: past the final sample
    there is no data, and a hold is the only statement that invents none.
    """
    segments = []
    for i in range(len(times_us) - 1):
        span_us = times_us[i + 1] - times_us[i]
        segments.append({"duration": span_us,
                         "dynamics": {"initial": float(values[i]),
                                      "rate": (float(values[i + 1]) - float(values[i]))
                                      / (span_us / 1_000_000)}})
    if times_us:
        tail_us = sim_duration_us - times_us[-1]
        if tail_us > 0:
            segments.append({"duration": tail_us,
                             "dynamics": {"initial": float(values[-1]), "rate": 0.0}})
    return coalesce_real(segments)


def coalesce_real(segments):
    """Merge adjacent FLAT segments holding the same value.

    Restricted to `rate == 0` on purpose. A zero-rate segment evaluates to its `initial` everywhere,
    so merging two with a bit-identical initial is exactly equivalent -- no tolerance, no drift.
    Merging sloped segments would mean asserting `i + r*(d1+d2) == i + r*d1 + r*d2`, which
    floating-point addition does not guarantee, to save segments that a moving resource does not
    produce anyway. The win is where it matters: an idle subsystem, a saturated battery and a full
    recorder are all long flat runs, and a week-long plan at a 5-second step is otherwise ~120 000
    segments per resource.
    """
    out = []
    for segment in segments:
        dynamics = segment["dynamics"]
        if out:
            previous = out[-1]["dynamics"]
            if (previous["rate"] == 0.0 and dynamics["rate"] == 0.0
                    and previous["initial"] == dynamics["initial"]):
                out[-1]["duration"] += segment["duration"]
                continue
        out.append({"duration": segment["duration"], "dynamics": dict(dynamics)})
    return out


def discrete_segments(times_us, values, sim_duration_us):
    """Samples -> piecewise-constant segments covering [0, sim_duration_us] exactly."""
    segments = []
    for i in range(len(times_us) - 1):
        segments.append({"duration": times_us[i + 1] - times_us[i], "dynamics": values[i]})
    if times_us:
        tail_us = sim_duration_us - times_us[-1]
        if tail_us > 0:
            segments.append({"duration": tail_us, "dynamics": values[-1]})
    return coalesce_discrete(segments)


def coalesce_discrete(segments):
    """Merge adjacent segments holding the same value. Exact by definition, and the difference
    between an eclipse profile of a few dozen segments and one of a hundred thousand."""
    out = []
    for segment in segments:
        if out and out[-1]["dynamics"] == segment["dynamics"]:
            out[-1]["duration"] += segment["duration"]
            continue
        out.append(dict(segment))
    return out


# ---------- endpoint implementations ----------------------------------------------------------------
def run_validate(backend, req):
    """POST /validate. Generic checks first, then the backend's own, layered on top."""
    declaration = backend.declaration()
    effective_only = bool(req.get("effectiveOnly", False))
    activities = req.get("activities", []) or []
    results = [declaration.validate_one(a.get("type"), a.get("arguments") or {}, effective_only)
               for a in activities]
    if not effective_only:
        subjects = [ValidationSubject(index=i, type=a.get("type"), arguments=a.get("arguments") or {},
                                      effective_arguments=r["effectiveArguments"],
                                      notices=list(r["notices"]))
                    for i, (a, r) in enumerate(zip(activities, results))
                    # An unknown activity type has no declaration to check against; there is
                    # nothing a deep check could add and plenty it could crash on.
                    if r["effectiveArguments"] is not None]
        extra = backend.deep_validate(subjects) if subjects else None
        for subject, notices in zip(subjects, extra or []):
            if not notices:
                continue
            result = results[subject.index]
            result["notices"] = result["notices"] + list(notices)
            result["valid"] = not result["notices"]
    return {"results": results}


def run_simulate(backend, req):
    """POST /simulate. Normalize, run, then check the answer before it goes on the wire."""
    declaration = backend.declaration()
    return check_response(backend.simulate(declaration.normalize(req)))


# ---------- registry -------------------------------------------------------------------------------
class Registry:
    """The set of models one adapter serves, addressed by key."""

    def __init__(self, backends):
        self.backends = dict(backends)

    def resolve(self, key):
        """Model by key; if none is given and exactly one is configured, use it.

        A key that does not match must 404 rather than silently serving some other model --
        including its identityHash, which merlin stores as an attestation that it introspected the
        model it asked for. Serving the wrong one would make that attestation a lie.
        """
        if key is None:
            if len(self.backends) == 1:
                return next(iter(self.backends.values()))
            raise BadRequest("no model specified; available: %s" % (list(self.backends),))
        if key in self.backends:
            return self.backends[key]
        raise NotFound("unknown model '%s'; available: %s" % (key, list(self.backends)))

    def models_list(self):
        return {"models": [dict(b.declaration().summary(), key=k) for k, b in self.backends.items()]}


# ---------- HTTP -------------------------------------------------------------------------------------
def make_handler(registry):
    """A BaseHTTPRequestHandler class bound to `registry`. Exposed for tests."""

    class Handler(BaseHTTPRequestHandler):
        # A per-CONNECTION socket timeout, which is the one that actually bites: without it a
        # client that opens a socket and never sends a request line parks a handler thread
        # forever. (`ThreadingHTTPServer.timeout` only applies to `handle_request()`, so under
        # `serve_forever()` it does nothing for this case -- setting only that, as both adapters
        # previously did, left the hole open.)
        timeout = 60

        def _send(self, code, obj):
            # allow_nan=False: Python would otherwise emit bare Infinity/NaN, which is not legal
            # JSON. Merlin's parser rejects the whole response, so the ingest dies before the gate's
            # own non-finite check can report anything useful. `check_response` should have caught
            # this already and said where; this is the backstop for everything it does not walk.
            try:
                body = json.dumps(obj, allow_nan=False).encode()
            except ValueError:
                code, body = 500, json.dumps(
                    {"error": "model produced a non-finite value (NaN or Infinity), "
                              "which cannot be sent as JSON"}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _key(self, body=None):
            """`?model=<key>`, or `model` in the request body for callers that prefer it there."""
            q = parse_qs(urlparse(self.path).query).get("model")
            return (q[0] if q else None) or (body or {}).get("model")

        def _dispatch(self, path, req):
            """`req` is the parsed body for a POST, or None for a GET.

            The path is matched BEFORE the model is resolved, so an unknown path is "not found"
            rather than a complaint about the model key that happened to be on it.
            """
            # `endswith` rather than `==` so an adapter can live behind a path prefix
            # (http://host/models/battery/simulate) without the routing needing to know.
            if path.endswith("/models"):
                return registry.models_list()          # discovery: never model-scoped
            if path.endswith("/introspect"):
                return registry.resolve(self._key(req)).declaration().introspect()
            if req is not None:
                if path.endswith("/validate"):
                    return run_validate(registry.resolve(self._key(req)), req)
                if path.endswith("/simulate"):
                    return run_simulate(registry.resolve(self._key(req)), req)
                # Anything unmatched is a 404. An earlier adapter let unmatched POSTs fall through
                # to simulate(), so POST /introspect answered with a 500 from the simulator.
                raise NotFound("not found: %s" % path)
            raise NotFound("not found")

        def _handle(self, req):
            path = urlparse(self.path).path.rstrip("/")
            try:
                self._send(200, self._dispatch(path, req))
            except NotFound as e:
                self._send(404, {"error": str(e)})
            except BadRequest as e:
                self._send(400, {"error": str(e)})
            except ModelError as e:
                # Already fully diagnosed -- the message names the span, segment or subprocess that
                # went wrong. A traceback would only point back at check_response.
                self._send(500, {"error": str(e)})
            except Exception as e:                     # noqa: BLE001 -- the last line before a 500
                # Genuinely unexpected: log where it happened, because the message alone rarely says.
                traceback.print_exc()
                self._send(500, {"error": str(e)})

        def do_GET(self):
            self._handle(None)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._send(400, {"error": "malformed Content-Length header"})
                return
            raw = self.rfile.read(n) or b"{}"
            try:
                req = json.loads(raw)
            except ValueError as e:
                self._send(400, {"error": "malformed JSON body: %s" % e})
                return
            if not isinstance(req, dict):
                self._send(400, {"error": "request body must be a JSON object, got %s"
                                          % type(req).__name__})
                return
            self._handle(req)

        def log_message(self, *a):
            pass

    return Handler


def serve(backends, port, banner=None, socket_timeout=60, host="0.0.0.0"):
    """Serve `backends` (an ordered {key: Backend} mapping) forever on `port`."""
    registry = Registry(backends)
    if banner is None:
        banner = "external-model backend on :%d  models: %s" % (
            port, ", ".join("%s(id=%s)" % (k, b.declaration().identity_hash())
                            for k, b in registry.backends.items()))
    print(banner, flush=True)
    # Threading + a socket timeout: with a plain HTTPServer one half-open connection wedges the
    # adapter for every other caller, and merlin's simulate path would just block.
    srv = ThreadingHTTPServer((host, port), make_handler(registry))
    srv.timeout = socket_timeout
    srv.serve_forever()


# ---------- a model in another process ------------------------------------------------------------
def _parse_parameters(entries):
    return [Parameter(name=e["name"], schema=e.get("schema") or {"type": "string"},
                      default=e.get("default"), required=e.get("required"))
            for e in entries or []]


def declaration_from_json(obj, key=None):
    """Parse a declaration in the same JSON shape `/introspect` emits, plus optional defaults.

    `/introspect` cannot carry defaults -- PlanDev has no field for them -- but a backend
    describing itself to this module can and should, since defaults are what make a parameter
    optional and what `effectiveArguments` is built from.
    """
    acts = []
    for a in obj.get("activityTypes") or []:
        params = _parse_parameters(a.get("parameters"))
        required = a.get("requiredParameters")
        if required is not None:
            # An explicit requiredParameters list wins over the default-is-None convention, so a
            # model with a genuinely-null default can still declare the parameter optional.
            names = set(required)
            params = [Parameter(p.name, p.schema, p.default, p.name in names) for p in params]
        acts.append(ActivityType(name=a["name"], parameters=params,
                                 computed_attributes_schema=a.get("computedAttributesSchema")))
    return Declaration(
        key=key or obj.get("key") or "model",
        name=obj.get("name") or key or obj.get("key") or "model",
        version=obj.get("version") or "1.0.0",
        activity_types=acts,
        resource_types=[ResourceType(name=r["name"], schema=r.get("schema") or {"type": "string"})
                        for r in obj.get("resourceTypes") or []],
        config_parameters=_parse_parameters(obj.get("parameters")))


class ExecBackend(Backend):
    """A model that lives in another PROCESS, spoken to over stdio.

    This is the escape hatch that keeps the contract language-neutral without making every new
    language reimplement it. A Rust, C or Go model has to do exactly two things:

        <exe> describe               -> a declaration, as JSON, on stdout
        <exe> simulate               <- a normalized request, as JSON, on stdin
                                     -> {realProfiles, discreteProfiles, spans} on stdout

    and gets routing, `?model=` resolution, defaults, typechecking, the identity hash, response
    validation and the HTTP surface for free. The request it reads has already been normalized, so
    it never has to implement `nonconformance` or default resolution -- which is precisely the code
    that drifted when two adapters each kept their own copy.

    A nonzero exit, a timeout, or unparseable stdout becomes a proper error carrying the process's
    stderr, so a model that dies says why instead of surfacing as an empty 500. Stderr from a run
    that SUCCEEDS is a log, not a failure, and is forwarded to this adapter's own stderr.
    """

    def __init__(self, key, command, name=None, version=None, timeout=None, cwd=None, env=None):
        self.key = key
        self.command = list(command) if isinstance(command, (list, tuple)) else [command]
        self._name = name
        self._version = version
        self.timeout = timeout
        self.cwd = cwd
        self.env = env
        self._declaration = None

    # -- process plumbing ---------------------------------------------------------------------------
    def _run(self, verb, stdin_text=None):
        cmd = self.command + [verb]
        try:
            p = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True,
                               timeout=self.timeout, cwd=self.cwd, env=self.env)
        except FileNotFoundError:
            raise ModelError("model executable %r not found" % (cmd[0],))
        except subprocess.TimeoutExpired:
            raise ModelError("model '%s' did not answer `%s` within %ss"
                             % (self.key, verb, self.timeout))
        if p.returncode != 0:
            raise ModelError("model '%s' exited %d on `%s`\nSTDERR:\n%s"
                             % (self.key, p.returncode, verb, (p.stderr or "").strip()[-2000:]))
        if p.stderr:
            # Not an error: a model is entitled to log. Forward it so it is not simply swallowed.
            sys.stderr.write("[%s %s] %s" % (self.key, verb, p.stderr))
            sys.stderr.flush()
        try:
            return json.loads(p.stdout or "")
        except ValueError as e:
            raise ModelError("model '%s' wrote unparseable JSON on `%s`: %s\nSTDOUT:\n%s\nSTDERR:\n%s"
                             % (self.key, verb, e, (p.stdout or "")[:1000],
                                (p.stderr or "").strip()[-1000:]))

    # -- Backend ------------------------------------------------------------------------------------
    def declaration(self):
        """Cached after the first `describe`.

        Cached on purpose, and not only for speed: the identity hash has to be STABLE across the
        life of the process, and re-describing on every /models poll would let a model that is not
        quite deterministic hand merlin a different attestation each time it looks.
        """
        if self._declaration is None:
            obj = self._run("describe")
            if not isinstance(obj, dict):
                raise ModelError("model '%s' described itself as %s, expected a JSON object"
                                 % (self.key, type(obj).__name__))
            decl = declaration_from_json(obj, key=self.key)
            if self._name or self._version:
                decl.name = self._name or decl.name
                decl.version = self._version or decl.version
            self._declaration = decl
        return self._declaration

    def simulate(self, request):
        payload = {
            "planStart": request.plan_start_iso,
            "duration": request.duration,
            "configuration": request.configuration,
            "directives": [{"id": d.id, "type": d.type, "startOffset": d.start_offset,
                            "arguments": d.arguments} for d in request.directives],
        }
        out = self._run("simulate", json.dumps(payload))
        if not isinstance(out, dict):
            raise ModelError("model '%s' answered `simulate` with %s, expected a JSON object"
                             % (self.key, type(out).__name__))
        return {"realProfiles": out.get("realProfiles") or {},
                "discreteProfiles": out.get("discreteProfiles") or {},
                "spans": out.get("spans") or []}


def exec_backends_from_env(var="EXEC_MODELS"):
    """{modelKey: command} from a JSON environment variable, for a container that is configured
    rather than coded. A command may be a string or an argv list."""
    cfg = os.environ.get(var)
    if not cfg:
        return {}
    return {k: ExecBackend(k, v) for k, v in json.loads(cfg).items()}
