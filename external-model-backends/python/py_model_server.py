#!/usr/bin/env python3
"""Minimal PYTHON external-model backend for PlanDev — proof that the `external` wire contract is
language-neutral (same contract the Blackbird adapter speaks; Merlin needs zero new code).

This is an Archetype-A "pure simulator": simulate(directives) -> profiles + spans, with no internal
scheduling (PlanDev's own scheduler could drive it as an oracle).

Model: a toy spacecraft BATTERY.
  Resources: SoC (real, LINEAR — a genuine rate-based profile, which Blackbird's constant reals can't show),
             Mode (variant: Idle | Charging | Discharging), Cycles (int).
  Activities: Charge(duration, rate=1.0/s), Discharge(duration, load=2.0/s).

Endpoints (same shape as the Blackbird adapter; `?model=` is optional but, if given, must match):
  GET  /models                 -> {models:[{key,name,version,identityHash}]}
  GET|POST /introspect         -> {activityTypes, resourceTypes, parameters, identityHash}
  POST /simulate   {planStart, duration(us), configuration, directives:[{id,type,startOffset(us),arguments}]}
                -> {realProfiles, discreteProfiles, spans}
  POST /validate   {activities:[{type,arguments}], effectiveOnly}
                -> {results:[{valid, notices:[{subjects,message}], effectiveArguments}]}

Run:  python3 py_model_server.py [port]   (stdlib only)
"""
import hashlib, json, math, sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

MODEL_KEY, MODEL_NAME, MODEL_VERSION = "battery", "battery", "1.0.0"
US_PER_S = 1_000_000
SOC_INIT, CYCLES_INIT = 50.0, 0

# --- model definition (types + defaults + per-parameter validation) --------------------------------
# Each activity: params as (name, valueSchema, default-or-None). None default => required.
MODEL = {
    "Charge":    [("duration", {"type": "duration"}, None),
                  ("rate",     {"type": "real"},     1.0)],
    "Discharge": [("duration", {"type": "duration"}, None),
                  ("load",     {"type": "real"},     2.0)],
}
RESOURCE_TYPES = {
    "SoC":    {"type": "real"},
    "Mode":   {"type": "variant", "variants": [{"key": k, "label": k} for k in ("Idle", "Charging", "Discharging")]},
    "Cycles": {"type": "int"},
}

def iso_to_dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)

# --- ValueSchema conformance -----------------------------------------------------------------------
def nonconformance(value, schema):
    """None if `value` fits `schema`, else a message. Mirrors merlin's ExternalResultsGate check, so an
    argument this accepts is one the gate will also accept once it comes back on a span."""
    if value is None:
        return None                                   # a schema says nothing about nullability
    t = schema.get("type")
    if t == "real":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        return None if ok else "expected a finite real, got %r" % (value,)
    if t == "int":
        # bool is an int subclass in Python; PlanDev's int schema does not accept one.
        ok = isinstance(value, int) and not isinstance(value, bool)
        return None if ok else "expected an integer, got %r" % (value,)
    if t == "duration":
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
            if sub: return "at [%d]: %s" % (i, sub)
        return None
    if t == "struct":
        if not isinstance(value, dict):
            return "expected an object, got %r" % (value,)
        items = schema.get("items", {})
        for k, s in items.items():
            if k not in value: return "missing field '%s'" % k
            sub = nonconformance(value[k], s)
            if sub: return "at .%s: %s" % (k, sub)
        for k in value:
            if k not in items: return "unexpected field '%s'" % k
        return None
    return None

# --- validation / effective args -------------------------------------------------------------------
def effective_args(typ, args):
    """Declared parameters only, with defaults filled in.

    An explicit JSON null counts as ABSENT, not as a supplied value -- otherwise a null sails past
    default resolution and reaches the arithmetic below as None. Undeclared names are dropped rather
    than echoed: they would otherwise ride through into the span's arguments, where merlin's ingest
    gate flags every span for carrying an argument the model never declared.
    """
    supplied = {k: v for k, v in (args or {}).items() if v is not None}
    eff = {}
    for name, _schema, dflt in MODEL.get(typ, []):
        if name in supplied:
            eff[name] = supplied[name]
        elif dflt is not None:
            eff[name] = dflt
    return eff

def undeclared(typ, args):
    declared = {n for n, _s, _d in MODEL.get(typ, [])}
    return [k for k in (args or {}) if k not in declared]

def validate_one(typ, args, effective_only):
    if typ not in MODEL:
        return {"valid": False, "notices": [{"subjects": [], "message": "unknown activity type '%s'" % typ}],
                "effectiveArguments": None}
    eff = effective_args(typ, args)
    if effective_only:
        return {"valid": True, "notices": [], "effectiveArguments": eff}
    notices = []
    args = args or {}
    schemas = {n: s for n, s, _d in MODEL[typ]}
    for name, _schema, dflt in MODEL[typ]:
        if dflt is None and args.get(name) is None:
            notices.append({"subjects": [name], "message": "missing required parameter '%s'" % name})
    for name in undeclared(typ, args):
        notices.append({"subjects": [name], "message": "unrecognized parameter '%s'" % name})
    # Merlin DELEGATES authoritative validation to the backend for external models, so if this does not
    # typecheck, nothing does: a type-wrong argument would validate green in the editor and then either
    # crash the simulation or produce a span the ingest gate rejects.
    for name, value in args.items():
        if name in schemas and value is not None:
            problem = nonconformance(value, schemas[name])
            if problem:
                notices.append({"subjects": [name], "message": "parameter '%s' %s" % (name, problem)})
    # Per-parameter semantic checks -- unlike Blackbird, a Python model CAN attribute an error to a
    # specific parameter (subjects), so it renders inline on that field in the UI.
    for pname in ("rate", "load"):
        v = args.get(pname)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v <= 0:
            notices.append({"subjects": [pname], "message": "'%s' must be > 0 (got %s)" % (pname, v)})
    v = args.get("duration")
    if isinstance(v, int) and not isinstance(v, bool) and v < 0:
        notices.append({"subjects": ["duration"], "message": "'duration' must be >= 0 (got %d)" % v})
    return {"valid": len(notices) == 0, "notices": notices, "effectiveArguments": eff}

# --- simulation ------------------------------------------------------------------------------------
class BadRequest(Exception):
    """A caller error -- reported as 4xx with the offending directive named, not as a 500."""

def simulate(req):
    sim_dur = int(req["duration"])
    if sim_dur < 0:
        raise BadRequest("simulation duration must be >= 0 (got %d)" % sim_dur)

    # Resolve every directive to an absolute half-open window [start, end) clamped into the simulation,
    # BEFORE any profile is built. Everything downstream then works in absolute offsets.
    acts, spans = [], []
    for d in req.get("directives", []):
        typ = d.get("type")
        if typ not in MODEL:
            raise BadRequest("directive %s has unknown activity type '%s'" % (d.get("id"), typ))
        eff = effective_args(typ, d.get("arguments") or {})
        for name, schema, dflt in MODEL[typ]:
            if dflt is None and name not in eff:
                raise BadRequest("directive %s (%s) is missing required parameter '%s'" % (d.get("id"), typ, name))
            problem = nonconformance(eff.get(name), schema)
            if problem:
                raise BadRequest("directive %s (%s) parameter '%s' %s" % (d.get("id"), typ, name, problem))
        start, dur = int(d["startOffset"]), int(eff["duration"])
        if dur < 0:
            raise BadRequest("directive %s (%s) has negative duration %d" % (d.get("id"), typ, dur))
        if start >= sim_dur:
            continue                                   # begins after the window; contributes nothing
        end = min(start + dur, sim_dur)                # clamp: nothing may extend past the simulation
        rate = float(eff["rate"]) if typ == "Charge" else -float(eff["load"])
        acts.append({"start": start, "end": end, "rate": rate, "type": typ})
        # The span reports the CLAMPED window, and the coerced effective arguments -- not a raw echo of
        # the request. Merlin does not clamp spans (it does clamp profiles), so an unclamped span would
        # persist at its full length inside a shorter dataset.
        spans.append({"spanId": len(spans) + 1, "type": typ, "startOffset": start,
                      "duration": end - start, "arguments": eff, "parentId": None,
                      "directiveId": d.get("id")})

    # Build the profile from a breakpoint timeline rather than a running cursor. A cursor cannot express
    # overlap -- and for a battery, a Charge overlapping a Discharge is the ordinary case, not an edge
    # case. The old cursor appended each activity's segment wherever the cursor happened to be, so the
    # SECOND of two overlapping activities landed at a cumulative offset later than its own span said it
    # ran, and the profile silently disagreed with the timeline. Deriving segments from sorted absolute
    # breakpoints makes cumulative segment offsets equal wall-clock offsets by construction, and makes
    # the result independent of the order directives arrive in.
    points = {0, sim_dur}
    for a in acts:
        points.add(a["start"]); points.add(a["end"])
    breaks = sorted(p for p in points if 0 <= p <= sim_dur)

    real_segs, mode_segs, cyc_segs = [], [], []
    soc, cycles = SOC_INIT, CYCLES_INIT
    for lo, hi in zip(breaks, breaks[1:]):
        if hi <= lo:
            continue
        active = [a for a in acts if a["start"] <= lo < a["end"]]
        rate = float(sum(a["rate"] for a in active))   # concurrent effects superpose
        cycles = CYCLES_INIT + sum(1 for a in acts if a["type"] == "Charge" and a["start"] <= lo)
        mode = "Charging" if rate > 0 else "Discharging" if rate < 0 else "Idle"
        dur = hi - lo
        real_segs.append({"duration": dur, "dynamics": {"initial": soc, "rate": rate}})
        mode_segs.append({"duration": dur, "dynamics": mode})
        cyc_segs.append({"duration": dur, "dynamics": cycles})
        soc += rate * (dur / US_PER_S)

    return {
        "realProfiles":     {"SoC": {"schema": RESOURCE_TYPES["SoC"], "segments": real_segs}},
        "discreteProfiles": {"Mode":   {"schema": RESOURCE_TYPES["Mode"],   "segments": mode_segs},
                             "Cycles": {"schema": RESOURCE_TYPES["Cycles"], "segments": cyc_segs}},
        "spans": spans,
    }

def identity_hash():
    """Digest of everything PlanDev STORES about this model.

    requiredParameters and defaults are included deliberately. PlanDev persists requiredParameters in
    activity_type and merlin's gate enforces them, so flipping a parameter between required and optional
    changes what PlanDev believes without changing the model's schemas -- and merlin's drift check would
    never notice. Parameters are sorted so a pure reordering of the declaration does NOT move the hash;
    order is not something PlanDev stores or cares about, and a spurious change here refuses simulations
    and invalidates the cache for nothing.
    """
    return hashlib.sha256(json.dumps({
        "acts": {t: sorted(([n, s, d] for n, s, d in ps), key=lambda p: p[0]) for t, ps in MODEL.items()},
        "res": RESOURCE_TYPES,
        "params": [],
    }, sort_keys=True).encode()).hexdigest()[:16]

def introspect():
    return {
        "activityTypes": [{"name": t, "parameters": [{"name": n, "schema": s} for n, s, _ in ps],
                           "requiredParameters": [n for n, _, d in ps if d is None]}
                          for t, ps in MODEL.items()],
        "resourceTypes": [{"name": n, "schema": s} for n, s in RESOURCE_TYPES.items()],
        "parameters": [],
        "identityHash": identity_hash(),
    }

def models_list():
    return {"models": [{"key": MODEL_KEY, "name": MODEL_NAME, "version": MODEL_VERSION,
                        "identityHash": identity_hash()}]}

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        # allow_nan=False: Python would otherwise emit bare Infinity/NaN, which is not legal JSON. Merlin's
        # parser rejects the whole response, so the ingest dies before the gate's own non-finite check can
        # report anything useful. Fail here, where the message can say what happened.
        try:
            body = json.dumps(obj, allow_nan=False).encode()
        except ValueError:
            code, body = 500, json.dumps(
                {"error": "model produced a non-finite value (NaN or Infinity), which cannot be sent as JSON"}).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _model_ok(self):
        """`?model=` is optional (one model here), but a key that does not match must 404 rather than
        silently serving this model -- including its identityHash, which merlin stores as an attestation
        that it introspected the model it asked for."""
        keys = parse_qs(urlparse(self.path).query).get("model")
        if keys and keys[0] != MODEL_KEY:
            self._send(404, {"error": "unknown model '%s'; available: ['%s']" % (keys[0], MODEL_KEY)})
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path.endswith("/models"):
            self._send(200, models_list())          # discovery: never model-scoped
        elif path.endswith("/introspect"):
            if self._model_ok(): self._send(200, introspect())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n) or b"{}"
            try:
                req = json.loads(raw)
            except ValueError as e:
                self._send(400, {"error": "malformed JSON body: %s" % e}); return
            if path.endswith("/introspect"):
                if self._model_ok(): self._send(200, introspect())
            elif path.endswith("/validate"):
                if not self._model_ok(): return
                self._send(200, {"results": [validate_one(a.get("type"), a.get("arguments") or {},
                                                          bool(req.get("effectiveOnly")))
                                             for a in req.get("activities", [])]})
            elif path.endswith("/simulate"):
                if not self._model_ok(): return
                self._send(200, simulate(req))
            else:
                # Previously anything unmatched fell through to simulate(), so POST /introspect answered
                # with a 500 from the simulator instead of an introspection.
                self._send(404, {"error": "not found: %s" % path})
        except BadRequest as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send(500, {"error": str(e)})

    def log_message(self, *a): pass

if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5002
    print("Python battery model backend on :%d  (activity types: %d, resources: %d)"
          % (PORT, len(MODEL), len(RESOURCE_TYPES)), flush=True)
    # Threading + a socket timeout: with a plain HTTPServer one half-open connection wedges the adapter
    # for every other caller, and merlin's simulate path would just block.
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.timeout = 60
    srv.serve_forever()
