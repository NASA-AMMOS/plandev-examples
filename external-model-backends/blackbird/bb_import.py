#!/usr/bin/env python3
"""Convert a Blackbird `.plan.json` into a PlanDev `PlanTransfer` file.

Offline, one-way, and requires NO PlanDev changes: the output drops straight into the existing
"Import Plan" button on PlanDev's plans page (or `POST /uploadActivities` on the gateway).

    python3 bb_import.py mission.plan.json --introspect-url http://blackbird-adapter:5011 \\
        --model powermodel -o mission.plandev.json

Two things this has to get right, both of them silent failures if it does not:

1. **Only `parent == null` activities become directives.** A Blackbird plan file stores the
   decomposition tree flattened alongside the top-level activities, with no marker other than
   `parent`. In the reference fixture `ActivityOne` appears BOTH as a top-level activity and as a
   child of `ActivityTwo`, and one child starts at the same instant as its parent -- so no
   heuristic on type or start time can separate them. Importing a child as a directive
   double-counts it: PlanDev would run it AND regenerate it from its parent's decomposition, and
   nothing downstream flags that. `parent` is the only correct rule.

2. **Argument values are re-encoded to target the model's `ValueSchema`,** not copied. Blackbird's
   JSON and PlanDev's differ for exactly the types that matter: a duration is `"01:00:00.000000"`
   in one and `3600000000` in the other, and a map is a native JSON object in one and a series of
   `{key, value}` structs in the other (merlin's `MapValueMapper`). This is the inverse of
   `bb_service.fmt_param`, and it is driven by the same `bbtype_to_schema` the adapter registers
   with, so the two can never drift apart.

Blackbird's plan file has NO header -- no plan start, no duration, no model reference -- so the
plan window is derived from the activities and PRINTED for the operator to type into the import
dialog. The gateway takes the plan's name/model/start/duration from that form and ignores whatever
the file says, though PlanDev's UI does prefill the form from the file's `name`, `start_time` and
`duration`, which is why those are emitted too.

stdlib only.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# effective_args reaches coerce_default internally; see ModelSchema.from_url for why that matters.
from bb_service import (bb_dur_to_us, bb_time_to_us_offset, bbtype_to_schema,
                        effective_args, iso_to_dt, load_model)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
ONE_DAY = timedelta(days=1)
_DOY_START = re.compile(r"^\d{4}-\d{1,3}T")


# ---------- time formatting ----------
def bb_start_to_dt(ts):
    """A Blackbird activity `start` -> an aware UTC datetime.

    Blackbird writes day-of-year (`2024-001T08:00:00.000000`). Rather than keep a second copy of
    that parser, reuse the service's: an offset from the epoch IS the timestamp. An ISO-8601 start
    is accepted too, for plans that have been through a hand edit.
    """
    if not isinstance(ts, str) or not ts.strip():
        raise ValueError("missing or non-string start")
    ts = ts.strip()
    if _DOY_START.match(ts):
        return EPOCH + timedelta(microseconds=bb_time_to_us_offset(ts, EPOCH))
    return iso_to_dt(ts)


def us_to_pg_interval(us):
    """Microseconds -> a Postgres interval literal, `[N days ]HH:MM:SS[.ffffff]`.

    Negative values carry the sign on EVERY component (`-1 days -02:00:00`), which is what Postgres
    itself emits and the only form both it and the UI's `postgres-interval` read back as the same
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


def dt_to_iso(dt, suffix="Z"):
    body = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if dt.microsecond:
        body += ".%06d" % dt.microsecond
    return body + suffix


# ---------- argument coercion (the inverse of bb_service.fmt_param) ----------
class CoercionError(Exception):
    pass


def map_kv_schema(schema):
    """(key schema, value schema) if `schema` is PlanDev's shape for a map, else None.

    PlanDev has no dictionary `ValueSchema`; merlin's `MapValueMapper` -- and therefore the map
    branch of `bbtype_to_schema` -- carries a map as a series of two-field `{key, value}` structs.
    Blackbird has no struct type of its own, so a series-of-`{key, value}` can only ever be a map;
    the test is unambiguous.
    """
    if not isinstance(schema, dict) or schema.get("type") != "series":
        return None
    items = schema.get("items")
    if not isinstance(items, dict) or items.get("type") != "struct":
        return None
    fields = items.get("items")
    if not isinstance(fields, dict) or set(fields) != {"key", "value"}:
        return None
    return fields["key"], fields["value"]


def coerce_value(schema, value, where="value"):
    """A value as Blackbird's `.plan.json` writes it -> the value PlanDev's `ValueSchema` declares."""
    stype = (schema or {}).get("type")

    if stype == "duration":
        # Blackbird writes `HH:MM:SS.ffffff` (optionally `NTHH:...`); PlanDev stores microseconds.
        if isinstance(value, bool):
            raise CoercionError("%s: expected a duration, got a boolean" % where)
        if isinstance(value, (int, float)):
            return int(value)          # already microseconds (a hand-edited or re-imported plan)
        if isinstance(value, str):
            try:
                return bb_dur_to_us(value)
            except Exception:
                raise CoercionError("%s: %r is not a Blackbird duration (HH:MM:SS[.ffffff])" % (where, value))
        raise CoercionError("%s: expected a duration, got %s" % (where, type(value).__name__))

    if stype == "int":
        if isinstance(value, bool):
            raise CoercionError("%s: expected an integer, got a boolean" % where)
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                raise CoercionError("%s: %r is not an integer" % (where, value))
        raise CoercionError("%s: expected an integer, got %s" % (where, type(value).__name__))

    if stype == "real":
        if isinstance(value, bool):
            raise CoercionError("%s: expected a number, got a boolean" % where)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                raise CoercionError("%s: %r is not a number" % (where, value))
        raise CoercionError("%s: expected a number, got %s" % (where, type(value).__name__))

    if stype == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise CoercionError("%s: %r is not a boolean" % (where, value))

    if stype == "series":
        kv = map_kv_schema(schema)
        if kv is not None:
            key_schema, val_schema = kv
            if isinstance(value, dict):
                # The whole point of this branch: Blackbird's native JSON object becomes PlanDev's
                # {key, value} series. Object keys are text by construction, so a non-string key
                # schema still has to go through its own coercion.
                return [{"key": coerce_value(key_schema, k, "%s[key]" % where),
                         "value": coerce_value(val_schema, v, "%s[%s]" % (where, k))}
                        for k, v in value.items()]
            if isinstance(value, list) and all(isinstance(e, dict) and set(e) == {"key", "value"} for e in value):
                return [{"key": coerce_value(key_schema, e["key"], "%s[key]" % where),
                         "value": coerce_value(val_schema, e["value"], "%s[%s]" % (where, e["key"]))}
                        for e in value]
            raise CoercionError("%s: expected a JSON object for a map parameter, got %s"
                                % (where, type(value).__name__))
        if isinstance(value, list):
            items = schema.get("items") or {"type": "string"}
            return [coerce_value(items, v, "%s[%d]" % (where, i)) for i, v in enumerate(value)]
        raise CoercionError("%s: expected a JSON array for a list parameter, got %s"
                            % (where, type(value).__name__))

    if stype == "struct":
        fields = schema.get("items") or {}
        if not isinstance(value, dict):
            raise CoercionError("%s: expected a JSON object for a struct parameter, got %s"
                                % (where, type(value).__name__))
        return {k: coerce_value(fields.get(k) or {"type": "string"}, v, "%s.%s" % (where, k))
                for k, v in value.items()}

    # "string" and "variant": Blackbird `time` values and every custom ConvertableFromString type
    # land here. Carry the text VERBATIM -- normalizing `2024-001T08:00:00.000000` to ISO-8601 would
    # hand back something Blackbird's own parser rejects on the return trip.
    if isinstance(value, str):
        return value
    if value is None:
        raise CoercionError("%s: expected a string, got null" % where)
    raise CoercionError("%s: expected a string, got %s" % (where, type(value).__name__))


# ---------- the model's activity dictionary, from either source ----------
def _get_json(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def _post_json(url, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class ModelSchema:
    """Activity types and parameter `ValueSchema`s, normalized across both schema sources."""

    def __init__(self, source):
        self.source = source
        self.param_order = {}      # type -> [parameter name] in declared order
        self.param_schemas = {}    # type -> {parameter name: ValueSchema}
        self.param_types = {}      # type -> [(name, bbtype)]   -- for effective_args
        self.param_defaults = {}   # type -> {name: default}    -- for effective_args

    def __contains__(self, typ):
        return typ in self.param_order

    def effective(self, typ, provided):
        return effective_args(typ, provided, self.param_types, self.param_defaults)

    @classmethod
    def from_classpath(cls, classpath, key=None):
        m = load_model(key or "model", classpath)
        self = cls("classpath %s" % classpath)
        for typ, params in m["param_types"].items():
            self.param_order[typ] = [pn for pn, _ in params]
            self.param_schemas[typ] = {pn: bbtype_to_schema(bt) for pn, bt in params}
            self.param_types[typ] = list(params)
            self.param_defaults[typ] = dict(m["param_defaults"].get(typ, {}))
        return self

    @classmethod
    def from_url(cls, base_url, key=None):
        base = base_url.rstrip("/")
        query = "?model=%s" % urllib.parse.quote(key) if key else ""
        intro = _get_json(base + "/introspect" + query)
        self = cls(base + "/introspect" + query)
        for a in intro.get("activityTypes", []):
            typ = a.get("name")
            params = a.get("parameters", []) or []
            self.param_order[typ] = [p["name"] for p in params]
            self.param_schemas[typ] = {p["name"]: (p.get("schema") or {"type": "string"}) for p in params}
            # /introspect carries ValueSchemas, not Blackbird type strings, and no defaults at all.
            # Both of those only ever reach effective_args, where the type selects a coerce_default
            # conversion -- and the defaults fetched below arrive ALREADY coerced (the adapter's
            # validate() runs coerce_default itself). "string" is therefore the CORRECT choice here,
            # the one that passes an already-converted default through untouched, not a placeholder.
            self.param_types[typ] = [(p["name"], "string") for p in params]
            self.param_defaults[typ] = {}
        self._fetch_defaults(base, query, intro)
        return self

    def _fetch_defaults(self, base, query, intro):
        """Recover parameter defaults over HTTP.

        `/introspect` reports only WHICH parameters are optional, not what they default to, but
        `/validate` with `effectiveOnly` returns `effective_args` of an empty argument set -- which
        is exactly the default map, already in PlanDev's value space. It short-circuits before
        Blackbird is invoked, so this costs one round trip and no JVM.
        """
        optional = [a["name"] for a in intro.get("activityTypes", []) or []
                    if set(p["name"] for p in a.get("parameters", []) or [])
                    - set(a.get("requiredParameters", []) or [])]
        if not optional:
            return
        try:
            res = _post_json(base + "/validate" + query,
                             {"activities": [{"type": t, "arguments": {}} for t in optional],
                              "effectiveOnly": True})
            for typ, result in zip(optional, res.get("results", []) or []):
                self.param_defaults[typ] = dict(result.get("effectiveArguments") or {})
        except Exception as e:
            print("warning: could not read parameter defaults from %s (%s). Optional parameters "
                  "missing from the plan file will be left unset; the model applies its own default "
                  "at simulation time." % (base, e), file=sys.stderr)


# ---------- conversion ----------
def convert(plan, schema, plan_name="imported", plan_start=None, duration_days=None):
    """Blackbird plan dict -> (PlanTransfer dict, report dict)."""
    source = plan.get("activities")
    if not isinstance(source, list):
        raise ValueError("not a Blackbird plan file: no top-level \"activities\" array")

    dropped, warnings = [], []

    def warn(index, typ, message):
        warnings.append({"index": index, "type": typ, "message": message})

    def drop(bb_id, typ, reason):
        dropped.append({"id": bb_id, "type": typ, "reason": reason})

    # A duplicate id is not fatal here -- ids only become metadata -- but it means the file cannot be
    # traced back to Blackbird activity-for-activity, and the parent links are ambiguous.
    seen_ids, duplicate_ids = set(), set()
    for a in source:
        aid = a.get("id")
        (duplicate_ids if aid in seen_ids else seen_ids).add(aid)

    # Pass 1: pick out the directives. `parent` is the ONLY rule -- see the module docstring.
    candidates = []
    for index, act in enumerate(source):
        bb_id, typ, parent = act.get("id"), act.get("type"), act.get("parent")
        if parent is not None:
            reason = "decomposition child of %s" % parent
            if parent not in seen_ids:
                reason += " (parent uuid is not in this file)"
                warn(index, typ, "parent uuid %s is not present in the file; the activity is still a "
                                 "decomposition child and is not imported" % parent)
            drop(bb_id, typ, reason)
            continue
        if typ not in schema:
            drop(bb_id, typ, "activity type is not registered in the model (%s)" % schema.source)
            continue
        try:
            start = bb_start_to_dt(act.get("start"))
        except Exception as e:
            drop(bb_id, typ, "unusable start %r (%s)" % (act.get("start"), e))
            continue
        if bb_id in duplicate_ids:
            warn(index, typ, "activity id %s appears more than once in the file" % bb_id)
        candidates.append((index, act, start))

    # Pass 2: the plan window. Blackbird's file has no header, so it is derived. Flooring to the UTC
    # day is what keeps every offset non-negative and leaves headroom before the first activity.
    if plan_start is None:
        if not candidates:
            raise ValueError("no importable top-level activities, so no plan start can be derived; "
                             "pass --plan-start to convert anyway")
        plan_start = min(s for _, _, s in candidates).replace(hour=0, minute=0, second=0, microsecond=0)
    if duration_days is None:
        last = max((s for _, _, s in candidates), default=plan_start)
        whole_days = (last.replace(hour=0, minute=0, second=0, microsecond=0) - plan_start) // ONE_DAY
        duration_days = max(1, whole_days + 1)
    plan_end = plan_start + timedelta(days=duration_days)

    # Pass 3: build the directives.
    activities = []
    for index, act, start in candidates:
        typ = act.get("type")
        declared = schema.param_order[typ]
        schemas = schema.param_schemas[typ]

        provided, provided_bbtype = {}, {}
        for p in act.get("parameters") or []:
            pname = p.get("name")
            if pname in provided:
                warn(index, typ, "parameter '%s' is listed more than once; the last value wins" % pname)
            provided[pname] = p.get("value")
            provided_bbtype[pname] = p.get("type")

        coerced = {}
        for pname in declared:
            if pname not in provided:
                continue
            bbtype = (provided_bbtype.get(pname) or "").strip()
            if bbtype.lower() == "time":
                warn(index, typ, "parameter '%s' is a Blackbird `time`, so it is an ABSOLUTE instant "
                                 "carried verbatim (%r). It will NOT move if the plan start changes."
                                 % (pname, provided[pname]))
            # The file records the type each value was written as. Comparing its ValueSchema to the
            # model's catches a model that has changed shape since the plan was exported -- otherwise
            # the value coerces cleanly against the new schema and quietly means something else.
            if bbtype and bbtype_to_schema(bbtype) != schemas[pname]:
                warn(index, typ, "parameter '%s' is written as Blackbird type '%s' but the model now "
                                 "declares schema %s; the model's schema is used"
                                 % (pname, bbtype, json.dumps(schemas[pname])))
            try:
                coerced[pname] = coerce_value(schemas[pname], provided[pname], "parameter '%s'" % pname)
            except CoercionError as e:
                warn(index, typ, "%s -- argument omitted, so the model default (if any) applies" % e)

        for pname in provided:
            if pname not in schemas:
                # Blackbird binds parameters POSITIONALLY on the way back in, so an argument the model
                # does not declare cannot be placed; keeping it would also trip PlanDev's own
                # argument validation. Dropping it is the only shape that stays consistent.
                warn(index, typ, "parameter '%s' is not declared by the model and is dropped" % pname)

        args = schema.effective(typ, coerced)
        for pname in declared:
            if pname in provided:
                continue
            if pname in args:
                warn(index, typ, "declared parameter '%s' is absent from the plan file; filled from "
                                 "the model default (%s)" % (pname, json.dumps(args[pname], default=str)))
            else:
                warn(index, typ, "declared parameter '%s' is absent from the plan file and the model "
                                 "declares no default" % pname)

        offset_us = round((start - plan_start).total_seconds() * 1_000_000)
        if offset_us < 0:
            warn(index, typ, "starts %s before the plan start; start_offset is negative"
                             % us_to_pg_interval(-offset_us))
        if start >= plan_end:
            warn(index, typ, "starts at %s, beyond the end of the suggested plan window (%s)"
                             % (dt_to_iso(start), dt_to_iso(plan_end)))

        metadata = {"blackbirdId": act.get("id")}
        notes = act.get("notes")
        if isinstance(notes, str) and notes.strip():
            metadata["blackbirdNotes"] = notes

        activities.append({
            "anchor_id": None,
            "anchored_to_start": True,
            # Sequential and index-aligned: the gateway keys its anchor remap off this id, matching
            # each created directive back by POSITION in this array.
            "id": len(activities) + 1,
            "arguments": {pname: args[pname] for pname in declared if pname in args},
            "metadata": metadata,
            "name": typ,
            "start_offset": us_to_pg_interval(offset_us),
            "tags": [],
            "type": typ,
        })

    duration = us_to_pg_interval(duration_days * 86_400_000_000)
    transfer = {
        "activities": [{k: a[k] for k in ("anchor_id", "anchored_to_start", "arguments", "id",
                                          "metadata", "name", "start_offset", "tags", "type")}
                       for a in activities],
        "duration": duration,
        # The gateway takes the plan's model and window from the import FORM and never reads these;
        # PlanDev's UI does prefill that form from `name`/`start_time`/`duration`, which is the only
        # reason they are here. `end_time` is deliberately absent -- its presence is exactly how the
        # UI detects a deprecated v1 transfer file.
        "id": 0,
        "model_id": 0,
        "name": plan_name,
        "simulation_arguments": {},
        # `+00:00` rather than `Z`: the UI strips exactly that suffix before parsing, and appends its
        # own `Z` afterwards -- a `Z` here survives the strip and becomes a `ZZ` it cannot read.
        "start_time": dt_to_iso(plan_start, "+00:00"),
        "tags": [],
        "version": "2",
    }
    report = {
        "activities": len(activities),
        "planStart": dt_to_iso(plan_start),
        "suggestedDuration": duration,
        "dropped": dropped,
        "warnings": warnings,
    }
    return transfer, report


def print_report(report, source_count, out_path, stream=sys.stderr):
    def p(line):
        print(line, file=stream)

    p("bb_import: %d source activities -> %d directives, %d dropped, %d warning(s)"
      % (source_count, report["activities"], len(report["dropped"]), len(report["warnings"])))
    p("  the plan file has no header, so ENTER THESE IN THE IMPORT DIALOG:")
    p("    plan start : %s" % report["planStart"])
    p("    duration   : %s" % report["suggestedDuration"])
    if report["dropped"]:
        p("  dropped:")
        for d in report["dropped"]:
            p("    - %s %s: %s" % (d["id"], d["type"], d["reason"]))
    if report["warnings"]:
        p("  warnings:")
        for w in report["warnings"]:
            p("    - [source #%d] %s: %s" % (w["index"], w["type"], w["message"]))
    if out_path:
        p("  wrote %s" % out_path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Convert a Blackbird .plan.json into a PlanDev PlanTransfer file.",
        epilog="The plan window is derived and printed; type it into PlanDev's import dialog, which "
               "is where the gateway reads it from.")
    ap.add_argument("plan", help="Blackbird .plan.json to convert ('-' for stdin)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--introspect-url", metavar="URL",
                     help="base URL of a running bb_service (GET <URL>/introspect)")
    src.add_argument("--classpath", metavar="CP",
                     help="Blackbird classpath to introspect locally (needs java)")
    ap.add_argument("--model", metavar="KEY",
                    help="model key; optional when the adapter serves exactly one model")
    ap.add_argument("-o", "--output", metavar="PATH", help="write the PlanTransfer here (default: stdout)")
    ap.add_argument("--report", metavar="PATH", help="also write the JSON report here ('-' for stdout)")
    ap.add_argument("--plan-name", metavar="NAME", help="plan name (default: the input file's base name)")
    ap.add_argument("--plan-start", metavar="ISO",
                    help="override the derived plan start, e.g. 2024-01-01T00:00:00Z")
    ap.add_argument("--duration-days", type=int, metavar="N", help="override the derived plan duration")
    args = ap.parse_args(argv)

    if args.plan == "-":
        plan = json.load(sys.stdin)
    else:
        with open(args.plan) as f:
            plan = json.load(f)
    default_name = "imported-plan" if args.plan == "-" else \
        re.sub(r"\.plan\.json$|\.json$", "", os.path.basename(args.plan))

    schema = (ModelSchema.from_url(args.introspect_url, args.model) if args.introspect_url
              else ModelSchema.from_classpath(args.classpath, args.model))

    transfer, report = convert(
        plan, schema,
        plan_name=args.plan_name or default_name,
        plan_start=iso_to_dt(args.plan_start) if args.plan_start else None,
        duration_days=args.duration_days)

    body = json.dumps(transfer, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(body + "\n")
    else:
        print(body)
    if args.report:
        rbody = json.dumps(report, indent=2)
        if args.report == "-":
            print(rbody)
        else:
            with open(args.report, "w") as f:
                f.write(rbody + "\n")
    print_report(report, len(plan.get("activities") or []), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
