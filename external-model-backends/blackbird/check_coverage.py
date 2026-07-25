#!/usr/bin/env python3
"""
Conformance check for the PlanDev external-model wire contract, run against the `covermodel`
probe adaptation (one resource of EVERY Blackbird resource type).

Why this exists: the demo `powermodel` only declares Double/Integer/String, and Blackbird's own
exampleAdaptation has no BooleanResource or Sum*Resource -- so those paths were untested by
construction. Two were silently broken: the resource registered in PlanDev with a schema and then
had NO segments at all, which looks like "the model just didn't touch it" rather than a bug.

Usage (from inside the cluster, or with the adapter port published):
    python3 check_coverage.py [base_url]        # default http://localhost:5011
Exits non-zero on the first failed assertion, so it can gate CI.
"""
import json
import sys
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5011").rstrip("/")
MODEL = "covermodel"

# Expected PlanDev ValueSchema per probe resource. This is the contract: a Blackbird type on the
# left MUST map to the schema on the right, or downstream typing (constraints, UI, DSL) is wrong.
EXPECTED_SCHEMA = {
    "Dbl":     "real",     # DoubleResource
    "Int":     "int",      # IntegerResource
    "StrEnum": "variant",  # StringResource WITH possible states
    "StrFree": "string",   # StringResource without
    "Bool":    "boolean",  # BooleanResource      <- silently became "string" before the fix
    "Dur":     "duration", # DurationResource
    "Tim":     "string",   # TimeResource (PlanDev has no absolute-time schema; carried as UTC text)
    "Ramp":    "real",     # DoubleResource, Interpolation=linear
    "Integ":   "real",     # IntegratingResource
    "SumDbl":  "real",     # SumDoubleResource
    "SumInt":  "int",      # SumIntegerResource
    "Vec.x":   "real",     # ArrayedResource, flattened to Name.Index
    "Vec.y":   "real",
}

# ExerciseAll drives Ramp 0 -> 100 over half its duration. With duration=2h, the ramp spans
# 3600s, so a correct adapter emits rate = 100/3600 per SECOND (RealDynamics.java:54).
SIM_DURATION_US = 86_400_000_000
ACT_DURATION_US = 7_200_000_000
EXPECTED_RAMP_RATE = 100.0 / (ACT_DURATION_US / 2 / 1_000_000)

failures = []


def check(cond, msg):
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        failures.append(msg)


def post(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:
        return json.load(r)


print(f"== introspect {MODEL} ==")
intro = get(f"/introspect?model={MODEL}")
schemas = {r["name"]: r["schema"] for r in intro.get("resourceTypes", [])}
for name, want in EXPECTED_SCHEMA.items():
    got = schemas.get(name)
    check(got is not None and got.get("type") == want,
          f"{name}: schema is {json.dumps(got)} (want type={want!r})")

acts = {a["name"]: a for a in intro.get("activityTypes", [])}
ex = acts.get("ExerciseAll", {})
pnames = [p["name"] for p in ex.get("parameters", [])]
# Blackbird reflects real constructor parameter names -- but only if compiled with `javac
# -parameters`. Without it they degrade to arg0/arg1, which is what a planner sees in the form.
check(pnames == ["d"], f"ExerciseAll parameter names are {pnames} (want ['d']; needs javac -parameters)")

print(f"\n== simulate {MODEL} ==")
sim = post(f"/simulate?model={MODEL}", {
    "planStart": "2024-01-01T00:00:00Z",
    "duration": SIM_DURATION_US,
    "configuration": {},
    "directives": [{"id": 1, "type": "ExerciseAll",
                    "startOffset": 3_600_000_000, "arguments": {"d": ACT_DURATION_US}}],
})
real, disc = sim.get("realProfiles", {}), sim.get("discreteProfiles", {})
allp = {**real, **disc}

# The headline invariant: a resource that introspects must actually produce data. This single
# check is what catches the "silent empty profile" class of bug for every type at once.
for name in EXPECTED_SCHEMA:
    segs = allp.get(name, {}).get("segments", [])
    check(len(segs) > 0, f"{name}: has {len(segs)} segment(s) (want >0)")

for name, prof in allp.items():
    bad = [s for s in prof.get("segments", []) if s.get("dynamics") is None]
    check(not bad, f"{name}: no null dynamics ({len(bad)} null)")

bool_vals = {s["dynamics"] for s in disc.get("Bool", {}).get("segments", [])}
check(bool_vals and all(isinstance(v, bool) for v in bool_vals),
      f"Bool: values are real booleans {bool_vals}")

rates = [s["dynamics"]["rate"] for s in real.get("Ramp", {}).get("segments", [])]
check(any(abs(r - EXPECTED_RAMP_RATE) < 1e-6 for r in rates),
      f"Ramp: has a segment with rate ~{EXPECTED_RAMP_RATE:.6f} /s (got {rates})")

spans = sim.get("spans", [])
check(any(s["type"] == "ExerciseAll" and s.get("directiveId") == 1 for s in spans),
      "ExerciseAll span is linked back to directiveId=1")

print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'ALL CHECKS PASSED'}")
sys.exit(1 if failures else 0)
