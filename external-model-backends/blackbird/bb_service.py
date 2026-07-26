#!/usr/bin/env python3
"""Blackbird external-model backend SERVICE (multi-model).

One generic, model-agnostic adapter that can serve one OR many Blackbird adaptations. It speaks the
PlanDev external-model wire contract; PlanDev only ever talks to a backend at an operator-configured URL.

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
import hashlib, json, os, re, subprocess, sys, tempfile, uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

BLACKBIRD_MAIN = os.environ.get("BLACKBIRD_MAIN", "gov.nasa.jpl.Blackbird")
JPLTIME_LIB = os.environ.get("JPLTIME_LIB", "jplTime/lib")
JAVA_BIN = os.environ.get("JAVA_BIN", "java")

# modelKey -> {cp, name, version, param_types, param_defaults, res_specs, initials, identity}
MODELS = {}

# ---------- time / value helpers (pure) ----------
def iso_to_dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)

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

def load_model(key, cp):
    """Introspect one adaptation: activity param types/defaults (CREATE_DICTIONARY) + resource
    schemas/initials (zero-activity REMODEL). Identity = hash of the introspected types."""
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
    # Hash the TRANSLATED schemas, not Blackbird's raw type strings. PlanDev stores ValueSchemas, and the
    # attestation exists to detect that what PlanDev stored no longer describes what will run. Hashing
    # the Blackbird-side names missed a whole class of drift: upgrading the adapter so that, say,
    # map<string, string> maps to a key/value series instead of a bare string leaves every stored
    # parameter schema wrong while the hash claims nothing changed. Including the adapter's own mapping
    # in the digest means such an upgrade correctly invalidates exactly the models it affects -- a model
    # using none of the changed types keeps its hash and is left alone.
    identity = hashlib.sha256(json.dumps({
        "acts": {n: sorted(([pn, bbtype_to_schema(bt)] for pn, bt in param_types[n]), key=lambda p: p[0])
                 for n in param_types},
        "res": {n: vs for n, (vs, _) in res_specs.items()},
    }, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return {"cp": cp, "name": key, "version": "1.0.0", "param_types": param_types,
            "param_defaults": param_defaults, "res_specs": res_specs, "initials": initials, "identity": identity}

# ---------- plan build / output parse (per-model) ----------
def build_plan_json(plan_start, directives, workdir, param_types):
    acts = []
    directive_by_uuid = {}
    for d in directives:
        typ = d["type"]
        start = dt_to_bbtime(plan_start + timedelta(microseconds=d["startOffset"]))
        args = d.get("arguments") or {}
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
                continue   # absent: Blackbird applies the model default (see effective_args)
            # Emit the value NATIVELY, matching what Blackbird's own JSONPlanWriter produces -- that is
            # the one shape its reader is guaranteed to accept, since writing and re-opening a plan
            # round-trips exactly. Verified against a real export: float -> bare number 42.5,
            # list<string> -> ["a","b","c"], map<string, string> -> {"k1":"v1"}, duration/time -> their
            # formatted strings. Serializing those to JSON *text* instead (the old behavior) handed
            # Blackbird a string where it expected an array, an object, or a number.
            params.append({"name": pname, "type": bt, "value": fmt_param(bt, args[pname])})
        # An argument the model does not declare cannot be positioned, and appending it would shift
        # every later parameter. Dropping it lets Blackbird report the arity mismatch against a plan
        # that is at least internally consistent.
        for pname in args:
            if pname not in dict(param_types.get(typ, [])):
                print("warning: dropping undeclared argument '%s' on %s" % (pname, typ), file=sys.stderr)
        bb_id = str(uuid.uuid5(uuid.NAMESPACE_OID, "plandev-directive-" + str(d["id"])))
        directive_by_uuid[bb_id] = d["id"]
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

# ---------- validation / effective args (per-model) ----------
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

def coerce_default(bbtype, dflt):
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

def effective_args(typ, provided, param_types, param_defaults):
    eff = dict(provided or {})
    ptypes = dict(param_types.get(typ, []))
    for pname, dflt in param_defaults.get(typ, {}).items():
        if pname not in eff:
            eff[pname] = coerce_default(ptypes.get(pname, "string"), dflt)
    return eff

# ---------- endpoint impls ----------
def introspect(model):
    acts = []
    for name, params in model["param_types"].items():
        defaults = model["param_defaults"].get(name, {})
        acts.append({"name": name,
                     "parameters": [{"name": pn, "schema": bbtype_to_schema(bt)} for pn, bt in params],
                     "requiredParameters": [pn for pn, _ in params if pn not in defaults]})
    res = [{"name": n, "schema": vs} for n, (vs, _) in model["res_specs"].items()]
    return {"activityTypes": acts, "resourceTypes": res, "parameters": [],
            "identityHash": model["identity"]}

def simulate(req, model):
    plan_start = iso_to_dt(req["planStart"])
    sim_dur = int(req["duration"])
    # Fill model defaults before building the plan, exactly as validate() does. Blackbird's .plan.json
    # reader requires every declared parameter to be present and rejects the WHOLE FILE on an arity
    # mismatch -- not just the offending activity -- and PlanDev only stores arguments a user explicitly
    # set. So a single directive leaving a defaulted parameter unset failed the entire simulation.
    directives = [
        {**d, "arguments": effective_args(
            d["type"], d.get("arguments") or {}, model["param_types"], model["param_defaults"])}
        for d in req.get("directives", [])]
    with tempfile.TemporaryDirectory() as wd:
        plan_json, directive_by_uuid = build_plan_json(plan_start, directives, wd, model["param_types"])
        xml_path = os.path.join(wd, "out.xml")
        script = os.path.join(wd, "sim.script")
        open(script, "w").write("OPEN_FILE %s unfrozen decompose\nREMODEL\nWRITE %s\n" % (plan_json, xml_path))
        run_bb(script, wd, model["cp"])
        rp, dp, spans = parse_output(xml_path, plan_start, sim_dur, model["initials"], directive_by_uuid)
        return {"realProfiles": rp, "discreteProfiles": dp, "spans": spans}

def validate(req, model):
    effective_only = bool(req.get("effectiveOnly", False))
    plan_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    pt, pd = model["param_types"], model["param_defaults"]
    results = []
    with tempfile.TemporaryDirectory() as wd:
        for a in req.get("activities", []):
            typ = a.get("type"); args = a.get("arguments") or {}
            if typ not in pt:
                results.append({"valid": False,
                                "notices": [{"subjects": [], "message": "unknown activity type '%s'" % typ}],
                                "effectiveArguments": None})
                continue
            eff = effective_args(typ, args, pt, pd)
            if effective_only:
                results.append({"valid": True, "notices": [], "effectiveArguments": eff}); continue
            plan_json, _ = build_plan_json(plan_start, [{"id": 0, "type": typ, "startOffset": 0, "arguments": args}], wd, pt)
            script = os.path.join(wd, "validate.script")
            open(script, "w").write("OPEN_FILE %s unfrozen decompose\n" % plan_json)
            ok, stderr = run_bb_ok(script, wd, model["cp"])
            results.append({"valid": ok,
                            "notices": [] if ok else [{"subjects": [], "message": clean_bb_error(stderr)}],
                            "effectiveArguments": eff})
    return {"results": results}

def models_list():
    return {"models": [{"key": k, "name": m["name"], "version": m["version"], "identityHash": m["identity"]}
                       for k, m in MODELS.items()]}

# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _resolve(self, key):
        """Model by key; if none given and exactly one is configured, use it. Raises KeyError otherwise."""
        if key and key in MODELS:
            return MODELS[key]
        if not key and len(MODELS) == 1:
            return next(iter(MODELS.values()))
        raise KeyError("unknown or unspecified model '%s'; available: %s" % (key, list(MODELS)))

    def _key(self, body=None):
        q = parse_qs(urlparse(self.path).query).get("model")
        return (q[0] if q else None) or (body or {}).get("model")

    def do_GET(self):
        try:
            path = urlparse(self.path).path.rstrip("/")
            if path.endswith("/models"):
                self._send(200, models_list())
            elif path.endswith("/introspect"):
                self._send(200, introspect(self._resolve(self._key())))
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(400 if isinstance(e, KeyError) else 500, {"error": str(e)})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            path = urlparse(self.path).path.rstrip("/")
            model = self._resolve(self._key(req))
            if path.endswith("/validate"):
                self._send(200, validate(req, model))
            elif path.endswith("/introspect"):
                self._send(200, introspect(model))
            else:
                self._send(200, simulate(req, model))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send(400 if isinstance(e, KeyError) else 500, {"error": str(e)})

    def log_message(self, *a): pass

if __name__ == "__main__":
    # Read the port HERE, not at module scope: this module is also imported as a library (bb_import.py
    # reuses its time/value helpers), and at module scope `int(sys.argv[1])` blew up on the importer's
    # own first argument before a single helper was available.
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    cfg = os.environ.get("BB_MODELS")
    cp_map = json.loads(cfg) if cfg else {"default": os.environ["BLACKBIRD_CP"]}
    for key, cp in cp_map.items():
        MODELS[key] = load_model(key, cp)
    summary = ", ".join("%s(%d acts/%d res, id=%s)" % (k, len(m["param_types"]), len(m["res_specs"]), m["identity"])
                        for k, m in MODELS.items())
    print("Blackbird multi-model backend on :%d  models: %s" % (PORT, summary), flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
