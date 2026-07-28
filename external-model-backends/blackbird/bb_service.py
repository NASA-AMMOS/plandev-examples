#!/usr/bin/env python3
"""Blackbird external-model backend SERVICE (multi-model).

One generic, model-agnostic adapter that can serve one OR many Blackbird adaptations. It speaks the
PlanDev external-model wire contract; PlanDev only ever talks to a backend at an operator-configured URL.

Everything that is not about Blackbird -- HTTP, routing, `?model=` resolution, ValueSchema
typechecking, default resolution, the identity hash, response validation -- lives in `adapter_core`,
shared with the Python adapter. What is left here is the Blackbird half: translating Blackbird's
types, plan files and TOL output to and from PlanDev's, and driving the JVM.

Endpoints (each addresses a model by key; if only one model is configured the key is optional):
  GET  /models                         -> { models: [{key, name, version, identityHash}] }   (discovery)
  GET  /introspect?model=<key>         -> { activityTypes, resourceTypes, parameters }
  POST /simulate?model=<key>           { planStart, duration(us), configuration, directives[] }
                                       -> { realProfiles, discreteProfiles, spans }
  POST /validate?model=<key>           { activities[], effectiveOnly }
                                       -> { results: [{valid, notices[], effectiveArguments}] }

Config: BB_MODELS = JSON map of {modelKey: classpath}. (Back-compat: if unset, a single model "default"
uses BLACKBIRD_CP.) Each classpath is Blackbird core + jpl_time + exactly one adaptation.

Run:  BB_MODELS='{"orbiter":"/cp/a","lander":"/cp/b"}' python3 bb_service.py [port]
stdlib only.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# adapter_core sits one directory up in the repo and NEXT TO this file inside the container image
# (the Dockerfile copies it in). Appending -- not inserting -- the repo root keeps the co-located
# copy winning when there is one, so the image always runs the module it shipped with.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter_core                                                            # noqa: E402
from adapter_core import (ActivityType, Declaration, Directive,                # noqa: E402,F401
                          Parameter, ResourceType, digest, iso_to_dt)

BLACKBIRD_MAIN = os.environ.get("BLACKBIRD_MAIN", "gov.nasa.jpl.Blackbird")
JPLTIME_LIB = os.environ.get("JPLTIME_LIB", "jplTime/lib")
JAVA_BIN = os.environ.get("JAVA_BIN", "java")


# ---------- time / value helpers (pure) ----------
def dt_to_bbtime(dt):
    return dt.strftime("%Y-%jT%H:%M:%S.%f")

def us_to_bbdur(us):
    s = us / 1_000_000.0
    d = int(s // 86400); s -= d*86400
    hh = int(s // 3600); s -= hh*3600
    mm = int(s // 60); s -= mm*60
    body = "%02d:%02d:%09.6f" % (hh, mm, s)
    return ("%dT%s" % (d, body)) if d else body

def bb_dur_to_us(txt):
    days = 0
    if "T" in txt:
        dp, txt = txt.split("T"); days = int(dp)
    hh, mm, ss = txt.split(":")
    return round((days*86400 + int(hh)*3600 + int(mm)*60 + float(ss)) * 1_000_000)

def bb_time_to_us_offset(ts, plan_start):
    m = re.match(r"(\d+)-(\d+)T(\d+):(\d+):(\d+)(?:\.(\d+))?", ts)
    y, doy, hh, mm, ss = int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5])
    micros = int(((m[6] or "0") + "000000")[:6])
    t = datetime(y, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy-1, hours=hh, minutes=mm, seconds=ss, microseconds=micros)
    return round((t - plan_start).total_seconds() * 1_000_000)

def composite_name(el):
    """Flatten Blackbird arrayed resources: <Name> + <Index level=N>idx</Index>... -> dotted name."""
    base = el.findtext("Name")
    idxs = [i.text or "" for i in el.findall("Index")]
    return base + "".join("." + i for i in idxs)

def split_type_args(inner):
    """Split 'string, list<int>' -> ['string', 'list<int>'], respecting nesting."""
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "<": depth += 1
        elif ch == ">": depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip(): parts.append(cur.strip())
    return parts

def bbtype_to_schema(bt):
    bt = (bt or "").strip()
    low = bt.lower()
    if low in ("double", "float", "real"): return {"type": "real"}
    if low in ("int", "integer", "long", "short", "byte"): return {"type": "int"}
    if low == "duration": return {"type": "duration"}
    if low in ("boolean", "bool"): return {"type": "boolean"}
    if low.startswith("list<") and low.endswith(">"):
        return {"type": "series", "items": bbtype_to_schema(bt[5:-1])}
    if low.startswith("map<") and low.endswith(">"):
        args = split_type_args(bt[4:-1])
        if len(args) == 2:
            # A map is a SERIES OF {key, value} STRUCTS -- merlin's own convention for Map parameters
            # (contrib MapValueMapper.getValueSchema). ValueSchema has no dictionary type, and ofStruct
            # needs a closed key set, but that is satisfied by the envelope: the struct's keys are
            # literally "key" and "value", not the map's keys, which stay free. Matching this exactly is
            # what makes a Blackbird map behave like any other Aerie map in constraints, the UI, and the
            # generated typings.
            return {"type": "series", "items": {"type": "struct", "items": {
                "key": bbtype_to_schema(args[0]), "value": bbtype_to_schema(args[1])}}}
    # time and custom ConvertableFromString types: carried as their string form.
    return {"type": "string"}

def fmt_param(bbtype, value):
    """PlanDev SerializedValue -> the value shape Blackbird's .plan.json reader expects.

    Deliberately NOT quoted for strings. Blackbird has two readers with different conventions: the
    command-script path strips surrounding quotes (ReflectionUtilities.returnValueOf), but the
    .plan.json path -- the one we use -- calls getAsString() with no stripping, so a quoted value
    arrives with the quote characters embedded. Blackbird's own JSONPlanWriter emits strings bare,
    which is the format to match. Verified against a real exported plan: ActivityEight's parameters
    come back as "Earth"/"x", not "\\"Earth\\""/"\\"x\\"".

    Containers are translated between the two conventions. PlanDev carries a map as a series of
    {key, value} structs (merlin's MapValueMapper); Blackbird writes a native JSON object. Lists agree
    on shape but their elements still need converting.
    """
    bt = (bbtype or "").strip()
    low = bt.lower()
    if low == "duration" and isinstance(value, (int, float)):
        return us_to_bbdur(int(value))
    if low.startswith("list<") and low.endswith(">") and isinstance(value, list):
        return [fmt_param(bt[5:-1], v) for v in value]
    if low.startswith("map<") and low.endswith(">") and isinstance(value, list):
        args = split_type_args(bt[4:-1])
        if len(args) == 2:
            out = {}
            for entry in value:
                if not isinstance(entry, dict) or "key" not in entry:
                    continue
                # Blackbird map keys are the JSON object's field names, so they are text by construction.
                out[str(fmt_param(args[0], entry["key"]))] = fmt_param(args[1], entry.get("value"))
            return out
    return value

def coerce_default(bbtype, dflt):
    """A Blackbird dictionary default (always TEXT) -> PlanDev's value space.

    Blackbird's CREATE_DICTIONARY writes every default as a string, so `"00:01:00"` and `"3"` have to
    be converted before they can be handed back as `effectiveArguments` or typechecked against the
    parameter's ValueSchema. Anything unconvertible is passed through untouched rather than dropped:
    a default we cannot read is still better information than no default at all.
    """
    if bbtype in ("int", "integer", "long"):
        try: return int(dflt)
        except (ValueError, TypeError): return dflt
    if bbtype in ("float", "double"):
        try: return float(dflt)
        except (ValueError, TypeError): return dflt
    if bbtype in ("boolean", "bool"):
        return str(dflt).lower() == "true"
    if bbtype == "duration":
        try: return bb_dur_to_us(dflt)
        except Exception: return dflt
    return dflt


# ---------- Blackbird invocation (classpath per model) ----------
def run_bb(script, workdir, cp):
    cmd = [JAVA_BIN, "-cp", cp, "-Djava.library.path=%s" % JPLTIME_LIB, BLACKBIRD_MAIN, script]
    p = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
    if p.returncode != 0:
        try: planj = open(os.path.join(workdir, "in.plan.json")).read()
        except Exception: planj = "(no in.plan.json)"
        raise RuntimeError("Blackbird exit %d\nSTDERR:\n%s\nSTDOUT:\n%s\nPLAN:\n%s"
                           % (p.returncode, p.stderr[-1500:], p.stdout[-500:], planj[:1500]))

def run_bb_ok(script, workdir, cp):
    cmd = [JAVA_BIN, "-cp", cp, "-Djava.library.path=%s" % JPLTIME_LIB, BLACKBIRD_MAIN, script]
    p = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
    return (p.returncode == 0, p.stderr or "")

def parse_res_specs(root):
    """resource composite-name -> (ValueSchema, is_real)."""
    res_specs = {}
    for spec in root.iter("ResourceSpec"):
        name = composite_name(spec)
        dtype = (spec.findtext("DataType") or "").lower()
        interp = (spec.findtext("Interpolation") or "constant").lower()
        poss = [s.text for s in spec.findall("./PossibleStates/StringValue")]
        if dtype in ("float", "double") and interp == "linear":
            vs, is_real = {"type": "real"}, True
        elif dtype in ("float", "double"):
            vs, is_real = {"type": "real"}, False
        elif dtype in ("int", "integer", "long", "byte"):
            vs, is_real = {"type": "int"}, False
        elif dtype == "boolean":
            vs, is_real = {"type": "boolean"}, False
        elif dtype == "duration":
            vs, is_real = {"type": "duration"}, False
        elif dtype == "time":
            # PlanDev's ValueSchema has no absolute-time type, so a TimeResource is carried as its
            # UTC string. (The TOL also gives milliseconds-since-epoch if a numeric form is ever wanted.)
            vs, is_real = {"type": "string"}, False
        elif poss:
            vs, is_real = {"type": "variant", "variants": [{"key": p, "label": p} for p in poss]}, False
        else:
            # list/map/custom -> best-effort string. Their values are NOT read below, so such a
            # resource will surface with no segments rather than wrong ones.
            vs, is_real = {"type": "string"}, False
        res_specs[name] = (vs, is_real)
    return res_specs

# Blackbird writes a resource value as <{DataTypeClassName}Value>, with Duration and Time
# special-cased to also carry a milliseconds= attribute (see TOLResourceValue.writeResValBlock).
# KEEP IN SYNC WITH parse_res_specs: a type mapped to a schema there but missing a tag here
# surfaces in PlanDev with a schema and NO segments -- a silent empty profile.
_VALUE_TAGS = ("DoubleValue", "IntegerValue", "IntValue", "LongValue", "ByteValue",
               "BooleanValue", "StringValue", "DurationValue", "TimeValue")

def read_res_value(r):
    """Value of a <Resource> node, or None if it carries no tag we understand."""
    for tag in _VALUE_TAGS:
        e = r.find(tag)
        if e is None or e.text is None:
            continue
        if tag == "DoubleValue":
            return float(e.text)
        if tag in ("IntegerValue", "IntValue", "LongValue", "ByteValue"):
            return int(e.text)
        if tag == "DurationValue":
            return bb_dur_to_us(e.text)
        if tag == "BooleanValue":
            return e.text.strip().lower() == "true"
        return e.text  # StringValue, TimeValue (UTC string, matching the schema above)
    # Structured values. Only ACTIVITY PARAMETERS reach these -- a Resource<V extends Comparable>
    # can never hold a List or Map -- but the reader is shared, so handle them here. Blackbird nests
    # <Element index="N"> for lists and <Element index="key"> for structs, each wrapping an ordinary
    # value tag, so the recursion is the same reader one level down.
    lv = r.find("ListValue")
    if lv is not None:
        return [read_res_value(e) for e in lv.findall("Element")]
    sv = r.find("StructValue")
    if sv is not None:
        # Blackbird's StructValue IS a map -- it has no fixed-shape struct type -- so emit PlanDev's
        # representation of a map: a series of {key, value} structs, matching merlin's MapValueMapper.
        # A bare {k: v} object would contradict the declared schema and the ingest gate would flag it.
        return [{"key": e.get("index"), "value": read_res_value(e)} for e in sv.findall("Element")]
    # Fallback: a CUSTOM Comparable value type. Blackbird names the tag <{SimpleClassName}Value> and
    # writes valueOut.toString(), so we cannot know the shape, but we CAN carry the text. That
    # matches the "string" schema parse_res_specs assigns and beats dropping the value silently.
    for e in r:
        if e.tag.endswith("Value") and e.text is not None:
            return e.text
    return None

def parse_initials(root):
    """resource composite-name -> earliest (initial) value."""
    seen = {}
    for rec in root.iter("TOLrecord"):
        if rec.get("type") != "RES_VAL":
            continue
        r = rec.find("Resource"); name = composite_name(r)
        if name in seen:
            continue
        v = read_res_value(r)
        if v is not None:
            seen[name] = v
    return seen

BB_TOOLS = os.environ.get("BB_TOOLS", "/opt/blackbird/tools")

# Every Blackbird span carries its originating activity UUID as a computed attribute, so a PlanDev span
# can be traced back to a record in a Blackbird plan file or TOL.
COMPUTED_ATTRIBUTES_SCHEMA = {"type": "struct", "items": {"blackbirdId": {"type": "string"}}}

def config_script_lines(configuration, config_specs):
    """PlanDev simulation configuration -> Blackbird `SET_PARAMETER Class.Field value` lines.

    Iterates the DECLARED parameters, not the request, so an unknown key cannot reach Blackbird and
    fail the whole script -- adapter_core rejects those upstream in `effective_config`, which is also
    why nothing here has to warn about them any more. A parameter the request left unset (or set to
    null) gets no line at all, which leaves the adaptation's own default in place. Values go through
    fmt_param so a duration arrives in Blackbird's own notation rather than as raw microseconds.
    """
    lines = []
    for spec in config_specs:
        value = (configuration or {}).get(spec["name"])
        if value is None:
            continue                                   # unset: leave the adaptation's own default
        v = fmt_param(spec["bbtype"], value)
        # SET_PARAMETER parses the rest of the line as the value, so it must be a single token's worth
        # of text; containers have no representation here and Blackbird has no syntax for them.
        if isinstance(v, (list, dict)):
            print("warning: configuration parameter '%s' is a container, which SET_PARAMETER cannot "
                  "express; ignoring" % spec["name"], file=sys.stderr)
            continue
        lines.append("SET_PARAMETER %s %s\n" % (spec["name"], v))
    return "".join(lines)

def load_config_specs(cp, workdir):
    """The adaptation's SIMULATION CONFIGURATION: public static fields on ParameterDeclaration subclasses.

    Blackbird names them `Class.Field` and sets them with `SET_PARAMETER Class.Field value`, so that
    dotted form is used as the PlanDev parameter name -- it is what a planner would type into a Blackbird
    script, and it keeps two adaptation classes free to declare the same field name. Returns [] rather
    than failing if the helper is unavailable, since an adaptation with no configuration is normal.
    """
    tools = BB_TOOLS
    if not os.path.isdir(tools):
        return []
    try:
        p = subprocess.run([JAVA_BIN, "-cp", cp + os.pathsep + tools,
                            "-Djava.library.path=%s" % JPLTIME_LIB, "BbParams"],
                           cwd=workdir, capture_output=True, text=True)
        if p.returncode != 0:
            print("warning: could not read adaptation parameters: %s" % p.stderr[-300:], file=sys.stderr)
            return []
        specs = []
        for e in json.loads(p.stdout or "[]"):
            specs.append({"name": "%s.%s" % (e["class"], e["field"]),
                          "cls": e["class"], "field": e["field"],
                          "bbtype": e.get("type") or "string", "default": e.get("default")})
        return specs
    except Exception as ex:
        print("warning: could not read adaptation parameters: %s" % ex, file=sys.stderr)
        return []

def load_model(key, cp):
    """Introspect one adaptation: activity param types/defaults (CREATE_DICTIONARY) + resource
    schemas/initials (zero-activity REMODEL)."""
    with tempfile.TemporaryDirectory() as wd:
        dpath = os.path.join(wd, "model.dict.json"); s = os.path.join(wd, "d.script")
        open(s, "w").write("CREATE_DICTIONARY %s\n" % dpath); run_bb(s, wd, cp)
        d = json.load(open(dpath))
        param_types, param_defaults = {}, {}
        for name, meta in d.get("activities", {}).items():
            ps = meta.get("parameters", [])
            param_types[name] = [(p["name"], p.get("type", "string")) for p in ps]
            param_defaults[name] = {p["name"]: p.get("default") for p in ps if p.get("default") not in (None, "")}
        plan = os.path.join(wd, "empty.plan.json"); json.dump({"activities": []}, open(plan, "w"))
        xml = os.path.join(wd, "empty.xml"); s2 = os.path.join(wd, "i.script")
        open(s2, "w").write("OPEN_FILE %s unfrozen decompose\nREMODEL\nWRITE %s\n" % (plan, xml)); run_bb(s2, wd, cp)
        root = ET.parse(xml).getroot()
        res_specs = parse_res_specs(root)
        initials = parse_initials(root)
        config_specs = load_config_specs(cp, wd)
    return {"cp": cp, "name": key, "version": "1.0.0", "param_types": param_types,
            "param_defaults": param_defaults, "res_specs": res_specs, "initials": initials,
            "config_specs": config_specs}


# ---------- declaration ----------
def published_digest_payload(model):
    """The exact bytes a Blackbird model's PUBLISHED identityHash is minted from.

    adapter_core has a canonical payload (`Declaration.digest_payload`) that a new model should use.
    This one is pinned because these models have already shipped: merlin STORES the hash as an
    attestation that it introspected the model it is about to simulate, so re-shaping the payload
    would invalidate every deployment without a single thing about the model having moved.

    It hashes the TRANSLATED schemas, not Blackbird's raw type strings. PlanDev stores ValueSchemas,
    and the attestation exists to detect that what PlanDev stored no longer describes what will run.
    Hashing the Blackbird-side names missed a whole class of drift: upgrading the adapter so that,
    say, map<string, string> maps to a key/value series instead of a bare string leaves every stored
    parameter schema wrong while the hash claims nothing changed. Including the adapter's own mapping
    in the digest means such an upgrade correctly invalidates exactly the models it affects -- a
    model using none of the changed types keeps its hash and is left alone.

    KNOWN GAP, preserved deliberately so the hash does not move: parameter DEFAULTS and therefore
    requiredParameters are NOT in here. merlin persists requiredParameters in activity_type and its
    gate enforces them, so flipping a Blackbird parameter between required and optional changes what
    PlanDev believes while this hash says nothing happened. The Python adapter's payload does cover
    defaults, and `Declaration.digest_payload` covers both -- adopting it is the fix, at the cost of
    a one-time re-attestation of every deployed Blackbird model.
    """
    param_types = model["param_types"]
    return {
        # Parameters are hashed in DECLARATION ORDER, not sorted. Order is not cosmetic: merlin assigns
        # each parameter an `order` from its index in this array (ResponseSerializers.serializeParameters),
        # stores it, reads activity types back sorted by it (GetActivityTypesAction), and plandev-ui lays
        # the argument form out in that order. So a reordered declaration changes what PlanDev stores, and
        # sorting here would hide exactly that from the attestation -- the stored order would go stale
        # while the hash claimed nothing had moved.
        "acts": {n: [[pn, bbtype_to_schema(bt)] for pn, bt in param_types[n]] for n in param_types},
        "res": {n: vs for n, (vs, _) in model["res_specs"].items()},
        # Config parameters are part of what PlanDev stores (mission_model_parameters), so they belong in
        # the attestation for the same reason activity and resource types do.
        "cfg": [[c["name"], bbtype_to_schema(c["bbtype"])] for c in model.get("config_specs", [])],
        # Computed-attribute schemas are stored in activity_type too, so a change to them is drift the
        # attestation must catch -- otherwise the gate starts rejecting spans against a stale schema.
        "computed": COMPUTED_ATTRIBUTES_SCHEMA,
    }


def build_declaration(key, model):
    """`load_model`'s Blackbird-shaped introspection -> the PlanDev-shaped Declaration.

    This is the whole translation layer: Blackbird type strings become ValueSchemas, and Blackbird's
    textual defaults are converted ONCE, here, instead of on every request. Converting at load time
    is what lets adapter_core fill and typecheck them like any other model's -- a default still in
    Blackbird notation would fail its own parameter's schema check.
    """
    acts = []
    for name, params in model["param_types"].items():
        defaults = model["param_defaults"].get(name, {})
        acts.append(ActivityType(
            name=name,
            parameters=[Parameter(pn, bbtype_to_schema(bt),
                                  coerce_default(bt, defaults[pn]) if pn in defaults else None)
                        for pn, bt in params],
            # Declared so the gate accepts what parse_output attaches to every span.
            computed_attributes_schema=COMPUTED_ATTRIBUTES_SCHEMA))
    return Declaration(
        key=key, name=model["name"], version=model["version"],
        activity_types=acts,
        resource_types=[ResourceType(n, vs) for n, (vs, _) in model["res_specs"].items()],
        # Simulation configuration: the adaptation's globals, editable per-plan in PlanDev exactly
        # like a JAR model's configuration. Declared with NO adapter-side default on purpose -- the
        # adaptation already holds its own, and the honest way to say "the planner did not set this"
        # is to emit no SET_PARAMETER line rather than to re-set the value Blackbird would have used.
        config_parameters=[Parameter(c["name"], bbtype_to_schema(c["bbtype"]), None)
                           for c in model.get("config_specs", [])],
        # Blackbird is the archetype that makes capabilities necessary. It is not a pure simulator:
        # its own Scheduler dispatches activities DURING the run (dispatchOnCondition, getWindows)
        # and decompose()/spawn() create more, so the schedule is an OUTPUT of simulating, not an
        # input to it. PlanDev's scheduler placing activities on top would mean two schedulers
        # writing the same plan, each unaware of the other's placements. Everything else PlanDev
        # does -- editing directives, simulating, plotting resources, checking constraints -- works
        # normally, and the message says so, because "unavailable" with no scope reads as broken.
        capabilities={
            # The other half of being Archetype B. Blackbird authors the plan, so the useful
            # direction is bringing one INTO PlanDev -- which is exactly the capability a pure
            # simulator has no use for and does not declare.
            adapter_core.PLAN_IMPORT: adapter_core.supported(formats=[{
                "key": "blackbird-plan-json",
                "label": "Blackbird plan (.plan.json)",
                "extensions": [".plan.json", ".json"],
            }]),
            adapter_core.PLANDEV_SCHEDULING: adapter_core.unsupported(
                "This model schedules its own activities: Blackbird's dispatcher places them during "
                "the simulation, so the schedule is a result of running it rather than an input. "
                "Using PlanDev's scheduler as well would put two schedulers on the same plan. Plan "
                "editing, simulation, resource plots and constraints all work normally."),
        },
        digest_payload=lambda _decl, m=model: published_digest_payload(m))


# ---------- plan build / output parse (per-model) ----------
def build_plan_json(plan_start, directives, workdir, param_types):
    acts = []
    directive_by_uuid = {}
    for d in directives:
        typ = d.type
        start = dt_to_bbtime(plan_start + timedelta(microseconds=d.start_offset))
        args = d.arguments or {}
        params = []
        # Iterate the model's DECLARED parameter order, not the order the arguments happen to arrive in.
        # Blackbird's .plan.json reader binds parameters POSITIONALLY and ignores `name` entirely
        # (PlanJSONHistoryReader.getParametersFromJSON), so the order we emit is the binding. Merlin
        # builds the arguments object from SerializedValue's Map.copyOf, and java.util immutable maps
        # iterate in a per-JVM-run salted order -- verified flipping between runs on this machine. So
        # the previous "iterate whatever arrived" was a coin flip per merlin restart: for two same-typed
        # parameters it silently swapped their values, and for differently-typed ones it produced an
        # intermittent simulation failure that would not reproduce.
        for pname, bt in param_types.get(typ, []):
            if pname not in args:
                continue   # absent: Blackbird applies the model default (see Declaration.effective_args)
            # Emit the value NATIVELY, matching what Blackbird's own JSONPlanWriter produces -- that is
            # the one shape its reader is guaranteed to accept, since writing and re-opening a plan
            # round-trips exactly. Verified against a real export: float -> bare number 42.5,
            # list<string> -> ["a","b","c"], map<string, string> -> {"k1":"v1"}, duration/time -> their
            # formatted strings. Serializing those to JSON *text* instead (the old behavior) handed
            # Blackbird a string where it expected an array, an object, or a number.
            params.append({"name": pname, "type": bt, "value": fmt_param(bt, args[pname])})
        # An argument the model does not declare cannot be positioned, and appending it would shift
        # every later parameter. Dropping it lets Blackbird report the arity mismatch against a plan
        # that is at least internally consistent. (On the /simulate path adapter_core has already
        # dropped it; this still fires for the raw arguments /validate hands the deep check.)
        for pname in args:
            if pname not in dict(param_types.get(typ, [])):
                print("warning: dropping undeclared argument '%s' on %s" % (pname, typ), file=sys.stderr)
        bb_id = str(uuid.uuid5(uuid.NAMESPACE_OID, "plandev-directive-" + str(d.id)))
        directive_by_uuid[bb_id] = d.id
        acts.append({"type": typ, "start": start, "parameters": params, "notes": "", "id": bb_id, "parent": None})
    path = os.path.join(workdir, "in.plan.json")
    json.dump({"activities": acts}, open(path, "w"))
    return path, directive_by_uuid

def parse_output(xml_path, plan_start, sim_duration_us, initials, directive_by_uuid=None):
    directive_by_uuid = directive_by_uuid or {}
    root = ET.parse(xml_path).getroot()
    res_specs = parse_res_specs(root)

    act_recs = [r for r in root.iter("TOLrecord") if r.get("type") == "ACT_START"]
    uuid_to_sid = {r.find("Instance").findtext("ID"): i for i, r in enumerate(act_recs, start=1)}
    spans = []
    for sid, rec in enumerate(act_recs, start=1):
        inst = rec.find("Instance")
        parent_uuid = (inst.findtext("Parent") or "").strip()
        parent_sid = uuid_to_sid.get(parent_uuid) if parent_uuid else None
        directive_id = directive_by_uuid.get(inst.findtext("ID"))
        start = span = None; args = {}
        for a in inst.findall("./Attributes/Attribute"):
            if a.findtext("Name") == "start": start = a.find("TimeValue").text
            if a.findtext("Name") == "span":  span = a.find("DurationValue").text
        for p in inst.findall("./Parameters/Parameter"):
            # Use the SAME reader as resources. This was a hand-rolled second copy handling only
            # Duration/Double/Integer/String, so a Time, Boolean, List, Map, or custom-typed argument
            # was silently dropped from the span -- the activity looked like it ran with fewer
            # arguments than it was given. PlanDev's ingest gate now flags exactly that as a missing
            # required parameter, which is how it surfaced.
            v = read_res_value(p)
            if v is not None:
                args[p.findtext("Name")] = v
        start_us, dur_us = bb_time_to_us_offset(start, plan_start), bb_dur_to_us(span)
        if start_us >= sim_duration_us:
            continue   # entirely outside PlanDev's window; Blackbird has no window concept, PlanDev does
        rec_out = {"spanId": sid, "type": inst.findtext("Type"), "startOffset": start_us,
                   "arguments": args, "parentId": parent_sid, "directiveId": directive_id}
        # An activity still running at the end of PlanDev's window is reported UNFINISHED (no duration)
        # rather than at its full Blackbird length. Merlin clamps profiles but not spans, so the full
        # length would persist inside a shorter dataset; and clamping it here would instead claim it
        # ended exactly at the window edge, which Blackbird never said. Unfinished is the one honest
        # option, and PlanDev stores it natively as a span with a null end.
        if start_us + dur_us <= sim_duration_us:
            rec_out["duration"] = dur_us
            # Computed attributes: values the model produced rather than was given. Blackbird's own
            # activity UUID goes here because it belongs to the executed INSTANCE, not to the
            # directive -- it is what lets a PlanDev span be traced back to a record in a Blackbird
            # plan file or TOL. PlanDev reads these as `computed.*` in command expansion, and they
            # must be DECLARED in introspect or the ingest gate rejects them.
            #
            # Attached only to a FINISHED span. Merlin tells the two apart by the presence of BOTH
            # `duration` and `computedAttributes` (PostgresResultsCellRepository), so an unfinished
            # span carrying computed attributes reads as finished-with-no-end. This adapter used to
            # attach them unconditionally; adapter_core's `check_response` now refuses to serialize
            # that pairing at all.
            rec_out["computedAttributes"] = {"blackbirdId": inst.findtext("ID") or ""}
        spans.append(rec_out)

    samples = {}
    for rec in root.iter("TOLrecord"):
        if rec.get("type") != "RES_VAL":
            continue
        r = rec.find("Resource")
        name = composite_name(r)
        if name not in res_specs:
            continue
        val = read_res_value(r)
        samples.setdefault(name, []).append((bb_time_to_us_offset(rec.findtext("TimeStamp"), plan_start), val))

    real_profiles, discrete_profiles = {}, {}
    for name, segs in samples.items():
        vs, is_real = res_specs[name]
        segs.sort(key=lambda x: x[0])
        if segs[0][0] > 0:
            segs.insert(0, (0, initials.get(name, segs[0][1])))
        out_segs = []
        for i, (off, v) in enumerate(segs):
            end = segs[i+1][0] if i+1 < len(segs) else sim_duration_us
            length = end - off
            if length <= 0:
                continue
            if is_real:
                # `is_real` means Blackbird declared Interpolation=linear, so the true profile RAMPS
                # between samples. PlanDev's RealDynamics is value = initial + rate*elapsedSECONDS
                # (RealDynamics.java:54), so derive the slope from the next sample. Emitting rate=0
                # here would render a linear resource as a staircase -- plausible-looking but wrong,
                # and constraints evaluated between samples would disagree with Blackbird.
                nxt = segs[i+1][1] if i + 1 < len(segs) else None
                rate = 0.0
                if isinstance(v, (int, float)) and isinstance(nxt, (int, float)) and length > 0:
                    rate = (float(nxt) - float(v)) / (length / 1_000_000.0)
                dyn = {"initial": float(v), "rate": rate}
            else:
                dyn = v
            out_segs.append({"duration": length, "dynamics": dyn})
        (real_profiles if is_real else discrete_profiles)[name] = {"schema": vs, "segments": out_segs}
    return real_profiles, discrete_profiles, spans


# ---------- validation ----------
def clean_bb_error(stderr):
    lines = [l.strip() for l in stderr.splitlines() if l.strip()]
    meaningful = [l for l in lines if not l.startswith("at ")]
    joined = " ".join(meaningful)
    m = re.search(r"Root cause:\s*(.+?)(?:\s+at\s|$)", joined)
    if m:
        return m.group(1).strip()[:400]
    for i, l in enumerate(meaningful):
        if "Error while creating activity" in l:
            return " ".join(meaningful[i:i + 3])[:400]
    for l in meaningful:
        if any(k in l for k in ("Not a JSON", "Index", "cannot", "Cannot", "NumberFormat",
                                "IllegalArgument", "Invalid", "required")):
            return l[:400]
    return (meaningful[-1] if meaningful else "invalid arguments")[:400]


# ---------- the backend ----------
# Blackbird has no notion of "check these arguments"; the only way to ask whether an activity
# constructs is to build a one-activity plan and open it. The instant chosen is arbitrary and never
# reaches PlanDev -- it only has to be a time Blackbird can parse.
VALIDATE_PLAN_START = datetime(2020, 1, 1, tzinfo=timezone.utc)


class BlackbirdBackend(adapter_core.Backend):
    """One Blackbird adaptation, behind the generic contract.

    Introspection runs ONCE, at construction: a CREATE_DICTIONARY plus a zero-activity REMODEL are
    two JVM starts, and the identity hash has to be fixed for the life of the process anyway --
    merlin stores it as an attestation and re-reading the model per request could hand it a
    different one each time it looks.
    """

    def __init__(self, key, cp):
        self.key = key
        self.model = load_model(key, cp)
        self._declaration = build_declaration(key, self.model)

    def declaration(self):
        return self._declaration

    def import_plan(self, request):
        """A Blackbird `.plan.json` -> a PlanDev plan.

        The conversion is `bb_import`, unchanged and already tested offline against a real Blackbird
        export -- this endpoint is the same code reached over HTTP instead of from a shell. That
        matters more than convenience: the CLI needs an operator to read the model's dictionary out
        of a running adapter and type the plan window into a dialog, while here the adaptation is
        already loaded in this process, so the schema the arguments are re-encoded against is
        necessarily the one this backend would simulate with. The two cannot drift.
        """
        import bb_import

        try:
            document = json.loads(request["content"])
        except ValueError as e:
            raise adapter_core.BadRequest("that is not a Blackbird .plan.json file: %s" % e)

        plan_start = request.get("planStart")
        try:
            plan, report = bb_import.convert(
                document,
                bb_import.ModelSchema.from_model(self.model, "adapter model %s" % self.key),
                plan_name=request.get("planName") or "%s import" % self.key,
                plan_start=bb_import.iso_to_dt(plan_start) if plan_start else None,
                duration_days=request.get("durationDays"))
        except ValueError as e:
            raise adapter_core.BadRequest(str(e))

        # Blackbird's plan file has no header -- no start, no duration, no model -- so the window is
        # DERIVED from the activities. Reported rather than silently applied: an operator importing a
        # week of ops needs to know the window came from the file's contents, not from their intent.
        notices = [{"severity": "info",
                    "message": "plan window derived from the file: starts %s, %s long"
                               % (report["planStart"], report["suggestedDuration"])}]
        notices += [{"severity": "warning",
                     "message": "activity %s (%s) was not imported: %s" % (d["id"], d["type"], d["reason"])}
                    for d in report["dropped"]]
        notices += [{"severity": "warning",
                     "message": "activity %s (%s): %s" % (w["index"], w["type"], w["message"])}
                    for w in report["warnings"]]
        return {"plan": plan, "notices": notices}

    def simulate(self, request):
        plan_start = request.plan_start
        with tempfile.TemporaryDirectory() as wd:
            plan_json, directive_by_uuid = build_plan_json(
                plan_start, request.directives, wd, self.model["param_types"])
            xml_path = os.path.join(wd, "out.xml")
            script = os.path.join(wd, "sim.script")
            # SET_PARAMETER lines go BEFORE the plan is opened and remodelled, so the adaptation's globals
            # are in place while it models. Blackbird holds these in static fields, but each simulate
            # spawns a fresh JVM, so there is no leakage between requests -- the defaults are restored by
            # construction.
            cfg_lines = config_script_lines(request.configuration, self.model["config_specs"])
            open(script, "w").write(
                cfg_lines + "OPEN_FILE %s unfrozen decompose\nREMODEL\nWRITE %s\n" % (plan_json, xml_path))
            run_bb(script, wd, self.model["cp"])
            rp, dp, spans = parse_output(xml_path, plan_start, request.duration,
                                         self.model["initials"], directive_by_uuid)
            return {"realProfiles": rp, "discreteProfiles": dp, "spans": spans}

    def deep_validate(self, subjects):
        """Ask Blackbird itself whether each activity CONSTRUCTS.

        This catches what no schema can: a value that is the right JSON type but that the
        adaptation's own parameter converter refuses, or a constructor that throws. It runs on top
        of adapter_core's typecheck rather than instead of it -- a subject that already has notices
        is skipped, because feeding Blackbird an argument the typechecker rejected is exactly how a
        type error used to surface as a JVM stack trace instead of a message naming the parameter.

        Blackbird reports against the plan file, not against a parameter, so these notices carry no
        `subjects` and render as an activity-level message.
        """
        pt = self.model["param_types"]
        out = []
        with tempfile.TemporaryDirectory() as wd:
            for subject in subjects:
                if subject.notices:
                    out.append([])
                    continue
                # NOTE: the RAW arguments, not the effective ones. That is what this check has always
                # done, and it is a KNOWN BUG kept intact by this refactor: Blackbird's .plan.json
                # reader binds positionally and rejects the whole file on an arity mismatch, so an
                # activity that simply omits a DEFAULTED parameter is reported invalid here even
                # though /simulate fills the default and runs it fine. Passing
                # `subject.effective_arguments` instead is the one-line fix.
                plan_json, _ = build_plan_json(
                    VALIDATE_PLAN_START,
                    [Directive(id=0, type=subject.type, start_offset=0, arguments=subject.arguments)],
                    wd, pt)
                script = os.path.join(wd, "validate.script")
                open(script, "w").write("OPEN_FILE %s unfrozen decompose\n" % plan_json)
                ok, stderr = run_bb_ok(script, wd, self.model["cp"])
                out.append([] if ok else [{"subjects": [], "message": clean_bb_error(stderr)}])
        return out


if __name__ == "__main__":
    # Read the port HERE, not at module scope: this module is also imported as a library (bb_import.py
    # reuses its time/value helpers), and at module scope `int(sys.argv[1])` blew up on the importer's
    # own first argument before a single helper was available.
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    cfg = os.environ.get("BB_MODELS")
    cp_map = json.loads(cfg) if cfg else {"default": os.environ["BLACKBIRD_CP"]}
    BACKENDS = {key: BlackbirdBackend(key, cp) for key, cp in cp_map.items()}
    summary = ", ".join("%s(%d acts/%d res, id=%s)"
                        % (k, len(b.model["param_types"]), len(b.model["res_specs"]),
                           b.declaration().identity_hash())
                        for k, b in BACKENDS.items())
    adapter_core.serve(BACKENDS, PORT,
                       banner="Blackbird multi-model backend on :%d  models: %s" % (PORT, summary))
