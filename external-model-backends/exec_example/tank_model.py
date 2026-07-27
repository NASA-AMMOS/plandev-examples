#!/usr/bin/env python3
"""A complete external model in ~60 lines, spoken over stdio -- the `ExecBackend` protocol.

    tank_model.py describe     -> the declaration, as JSON, on stdout
    tank_model.py simulate     <- a normalized request, as JSON, on stdin
                               -> {realProfiles, discreteProfiles, spans} on stdout

`adapter_core.ExecBackend` wraps this into a full PlanDev external-model backend. That is the point
of the example: NOTHING below typechecks an argument, resolves a default, computes an identity hash,
routes a URL or validates its own output, because the adapter does all of it. By the time `simulate`
reads stdin, every directive has a known type, all of its required parameters, defaults filled in
and every value checked against the schema this file declared. A model written in Rust, C or Go has
exactly this much to implement.

The model: a tank with one activity.
  Resources: Level (real, ramping) and Filling (boolean).
  Activity:  Fill(duration, rate=1.0/s), which raises Level while it runs.
  Config:    initialLevel (real, default 0.0).

It is written in Python only so the example needs no toolchain; nothing about the protocol is
Python-specific. Errors go to stderr with a nonzero exit, which the adapter turns into a 500 that
quotes them.
"""
import json
import sys

US_PER_S = 1_000_000

DECLARATION = {
    "key": "tank",
    "name": "tank",
    "version": "1.0.0",
    "activityTypes": [{
        "name": "Fill",
        # Same shape /introspect emits, plus `default` -- which /introspect has no field for, but
        # which the adapter needs in order to fill it in and report `effectiveArguments`. A
        # parameter with no default is required.
        "parameters": [{"name": "duration", "schema": {"type": "duration"}},
                       {"name": "rate", "schema": {"type": "real"}, "default": 1.0}],
        "computedAttributesSchema": {"type": "struct", "items": {"added": {"type": "real"}}},
    }],
    "resourceTypes": [{"name": "Level", "schema": {"type": "real"}},
                      {"name": "Filling", "schema": {"type": "boolean"}}],
    "parameters": [{"name": "initialLevel", "schema": {"type": "real"}, "default": 0.0}],
}


def simulate(req):
    sim_dur = req["duration"]
    level = req["configuration"]["initialLevel"]

    # Absolute breakpoints, so two overlapping Fills SUM rather than one overwriting the other.
    windows = [(d["startOffset"], min(d["startOffset"] + d["arguments"]["duration"], sim_dur),
                d["arguments"]["rate"], d)
               for d in req["directives"] if d["startOffset"] < sim_dur]
    edges = {0, sim_dur} | {w[0] for w in windows} | {w[1] for w in windows}
    breaks = sorted(b for b in edges if 0 <= b <= sim_dur)

    level_segs, filling_segs = [], []
    for lo, hi in zip(breaks, breaks[1:]):
        rate = sum(w[2] for w in windows if w[0] <= lo < w[1])
        level_segs.append({"duration": hi - lo, "dynamics": {"initial": level, "rate": float(rate)}})
        filling_segs.append({"duration": hi - lo, "dynamics": rate != 0})
        level += rate * ((hi - lo) / US_PER_S)

    spans = []
    for i, (start, end, rate, d) in enumerate(windows, start=1):
        span = {"spanId": i, "type": d["type"], "startOffset": start, "arguments": d["arguments"],
                "parentId": None, "directiveId": d["id"]}
        # A finished span carries BOTH `duration` and `computedAttributes`; one that outlived the
        # window carries neither. The adapter refuses to serialize any other combination.
        if start + d["arguments"]["duration"] <= sim_dur:
            span["duration"] = d["arguments"]["duration"]
            span["computedAttributes"] = {"added": rate * ((end - start) / US_PER_S)}
        spans.append(span)

    return {"realProfiles": {"Level": {"schema": {"type": "real"}, "segments": level_segs}},
            "discreteProfiles": {"Filling": {"schema": {"type": "boolean"}, "segments": filling_segs}},
            "spans": spans}


if __name__ == "__main__":
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb == "describe":
        json.dump(DECLARATION, sys.stdout)
    elif verb == "simulate":
        request = json.load(sys.stdin)
        for d in request.get("directives", []):
            # A model-level check the adapter cannot make for us: the schema says `duration` is an
            # integer, not that it is a sensible one.
            if d["arguments"]["duration"] < 0:
                sys.stderr.write("directive %s: a Fill cannot last %d microseconds\n"
                                 % (d["id"], d["arguments"]["duration"]))
                raise SystemExit(1)
        json.dump(simulate(request), sys.stdout)
    else:
        sys.stderr.write("usage: tank_model.py {describe|simulate}\n")
        raise SystemExit(2)
