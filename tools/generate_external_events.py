#!/usr/bin/env python3
"""Generate large, varied PlanDev external-event datasets for hopper/orbiter scale testing.

Emits two files in PlanDev's canonical external-event ingest format:

  <prefix>_schema.json  — event-type + source-type definitions (upload first)
  <prefix>_source.json  — one external source with N events across the event types

The goal is SCALE and VARIETY, not physical accuracy: events are placed with simple
per-type cadences (exponential spacing) and randomized attributes. Nothing here does
real geometry/SPICE — it just produces thousands of plausibly-shaped events spanning a
mission window, with several event types that each carry a different attribute schema.

The comms event type defaults to "DSNContact" so the data works directly with
examples/07-external-events' ScheduleDownlinksDuringContacts goal (which queries that
type). Pass --contact-type DSS_Pass to match the hopper comms_pass_schema instead.

Usage:
  python3 tools/generate_external_events.py                 # ~5000 events over 2028
  python3 tools/generate_external_events.py --count 20000 --seed 7
  python3 tools/generate_external_events.py --start 2028-100 --end 2028-200 \
      --out-dir /tmp/ev --prefix mars_events

Stdlib only (json, random, argparse, datetime). PlanDev ingests events at roughly
hundreds/sec, so tens of thousands is fine; size the count for your ingest budget.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone

# --- time helpers (PlanDev uses DOY timestamps "YYYY-DDDThh:mm:ssZ" and "HH:MM:SS" durations) ---

def parse_doy(s: str) -> datetime:
    """Parse 'YYYY-DDD' or full 'YYYY-DDDThh:mm:ss[Z]' into a UTC datetime."""
    s = s.rstrip("Z")
    fmt = "%Y-%jT%H:%M:%S" if "T" in s else "%Y-%j"
    return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)


def fmt_instant(dt: datetime) -> str:
    return dt.strftime("%Y-%jT%H:%M:%SZ")


def fmt_duration(seconds: float) -> str:
    seconds = max(1, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def make_key(name: str, contact_type: str, attrs: dict, i: int) -> str:
    """Build a descriptive, unique event key (this shows as the timeline label).

    Leads with the event's headline attribute(s) so the label reads like
    'Pass_DSS-14_X_00007' or 'Eclipse_MARS_UMBRA_00042' rather than a bare counter.
    The trailing index keeps keys unique within the source.
    """
    if name == contact_type:
        head = f"Pass_{attrs['station']}_{attrs['band']}"
    elif name == "Eclipse":
        head = f"Eclipse_{attrs['body']}_{attrs['shadow_type']}"
    elif name == "Occultation":
        head = f"Occultation_{attrs['occulting_body']}_by_{attrs['observer']}"
    elif name == "ThermalCycle":
        head = f"Thermal_{attrs['phase']}"
    elif name == "KeepOutWindow":
        head = f"KeepOut_{attrs['target_body']}"
    elif name == "MomentumDump":
        head = f"MomentumDump_{attrs['trigger']}"
    elif name == "SolarFlare":
        head = f"Flare_{attrs['xray_class']}"
    elif name == "GroundStationOutage":
        head = f"Outage_{attrs['station']}_{attrs['reason']}"
    else:
        head = name
    return f"{head}_{i:05d}"


# --- event-type catalog -----------------------------------------------------------------
#
# Each entry defines: the JSON-schema for its attributes (properties / required), a weight
# (share of the total event count), a duration range in seconds, and an attribute generator.
# Edit/extend this dict to add event types.

DSN_STATIONS = ["DSS-14", "DSS-24", "DSS-25", "DSS-26", "DSS-34", "DSS-43", "DSS-54", "DSS-63"]
BANDS = ["X", "Ka", "S", "UHF"]
BODIES = ["MARS", "MOON", "EARTH", "PHOBOS", "DEIMOS"]
FLARE_CLASSES = ["A", "B", "C", "M", "X"]
OUTAGE_REASONS = ["MAINTENANCE", "WEATHER", "RFI", "POWER"]


def _flare_class(rng: random.Random) -> str:
    # weighted toward small flares
    cls = rng.choices(FLARE_CLASSES, weights=[35, 30, 20, 12, 3])[0]
    return f"{cls}{rng.uniform(1.0, 9.9):.1f}"


def event_catalog(contact_type: str):
    return {
        contact_type: {
            "weight": 0.40,
            "dur_s": (30 * 60, 5 * 3600),
            "schema": {
                "type": "object",
                "required": ["station", "band"],
                "properties": {
                    "station": {"type": "string"},
                    "band": {"type": "string"},
                    "peak_elevation_deg": {"type": "number"},
                    "max_bitrate_mbps": {"type": "number"},
                },
            },
            "attrs": lambda rng: {
                "station": rng.choice(DSN_STATIONS),
                "band": rng.choice(BANDS),
                "peak_elevation_deg": round(rng.uniform(5, 85), 1),
                "max_bitrate_mbps": round(rng.choice([0.5, 1, 2, 4, 8, 16]) * rng.uniform(0.8, 1.2), 2),
            },
        },
        "Eclipse": {
            "weight": 0.15,
            "dur_s": (20 * 60, 70 * 60),
            "schema": {
                "type": "object",
                "required": ["shadow_type", "body"],
                "properties": {
                    "shadow_type": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
            "attrs": lambda rng: {
                "shadow_type": rng.choices(["UMBRA", "PENUMBRA"], weights=[3, 1])[0],
                "body": rng.choice(["MARS", "MOON"]),
            },
        },
        "Occultation": {
            "weight": 0.10,
            "dur_s": (5 * 60, 40 * 60),
            "schema": {
                "type": "object",
                "required": ["occulting_body", "observer"],
                "properties": {
                    "occulting_body": {"type": "string"},
                    "observer": {"type": "string"},
                },
            },
            "attrs": lambda rng: {
                "occulting_body": rng.choice(BODIES),
                "observer": rng.choice(DSN_STATIONS),
            },
        },
        "ThermalCycle": {
            "weight": 0.10,
            "dur_s": (30 * 60, 6 * 3600),
            "schema": {
                "type": "object",
                "required": ["phase"],
                "properties": {
                    "phase": {"type": "string"},
                    "est_surface_temp_c": {"type": "number"},
                },
            },
            "attrs": lambda rng: (
                lambda phase: {
                    "phase": phase,
                    "est_surface_temp_c": round(
                        rng.uniform(80, 120) if phase == "DAY"
                        else rng.uniform(-180, -130) if phase == "NIGHT"
                        else rng.uniform(-60, 40),
                        1,
                    ),
                }
            )(rng.choice(["DAY", "NIGHT", "TERMINATOR"])),
        },
        "KeepOutWindow": {
            "weight": 0.10,
            "dur_s": (10 * 60, 2 * 3600),
            "schema": {
                "type": "object",
                "required": ["target_body"],
                "properties": {
                    "target_body": {"type": "string"},
                    "half_angle_deg": {"type": "number"},
                },
            },
            "attrs": lambda rng: {
                "target_body": rng.choice(["SUN", "MOON", "EARTH"]),
                "half_angle_deg": round(rng.uniform(2, 30), 1),
            },
        },
        "MomentumDump": {
            "weight": 0.08,
            "dur_s": (3 * 60, 25 * 60),
            "schema": {
                "type": "object",
                "required": ["trigger"],
                "properties": {
                    "trigger": {"type": "string"},
                    "wheel_speed_rpm": {"type": "number"},
                },
            },
            "attrs": lambda rng: {
                "trigger": rng.choice(["MOMENTUM_THRESHOLD", "SCHEDULED", "GROUND_COMMANDED"]),
                "wheel_speed_rpm": round(rng.uniform(2000, 6000)),
            },
        },
        "SolarFlare": {
            "weight": 0.008,
            "dur_s": (10 * 60, 3 * 3600),
            "schema": {
                "type": "object",
                "required": ["xray_class"],
                "properties": {
                    "xray_class": {"type": "string"},
                    "peak_flux_wm2": {"type": "number"},
                },
            },
            "attrs": lambda rng: {
                "xray_class": _flare_class(rng),
                "peak_flux_wm2": float(f"{rng.uniform(1e-7, 1e-3):.2e}"),
            },
        },
        "GroundStationOutage": {
            "weight": 0.003,
            "dur_s": (2 * 3600, 23 * 3600),
            "schema": {
                "type": "object",
                "required": ["station", "reason"],
                "properties": {
                    "station": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
            "attrs": lambda rng: {
                "station": rng.choice(DSN_STATIONS),
                "reason": rng.choice(OUTAGE_REASONS),
            },
        },
    }


def generate(count, start, end, seed, contact_type):
    rng = random.Random(seed)
    catalog = event_catalog(contact_type)
    window_s = (end - start).total_seconds()
    if window_s <= 0:
        raise SystemExit("--end must be after --start")

    events = []
    per_type = {}
    for name, spec in catalog.items():
        n = max(1, round(count * spec["weight"]))
        per_type[name] = n
        mean_gap = window_s / n  # average spacing to spread ~n events across the window
        t = start + timedelta(seconds=rng.uniform(0, mean_gap))
        made = 0
        i = 0
        while t < end and made < n * 2:  # *2 cap guards against pathological tiny gaps
            # PlanDev requires each event's whole [start, start+duration] to fit within the
            # source period, so clamp the duration to what's left before the window end.
            remaining = (end - t).total_seconds()
            if remaining < 2:
                break
            i += 1
            dlo, dhi = spec["dur_s"]
            dur = min(rng.uniform(dlo, dhi), remaining - 1)
            attrs = spec["attrs"](rng)
            events.append({
                "key": make_key(name, contact_type, attrs, i),
                "event_type_name": name,
                "start_time": fmt_instant(t),
                "duration": fmt_duration(dur),
                "attributes": attrs,
            })
            made += 1
            t += timedelta(seconds=rng.expovariate(1.0 / mean_gap))

    events.sort(key=lambda e: e["start_time"])
    return events, per_type, catalog


def build_schema(catalog, contact_type):
    return {
        "event_types": {name: spec["schema"] for name, spec in catalog.items()},
        "source_types": {
            "MissionEvents": {
                "type": "object",
                "required": [],
                "properties": {"description": {"type": "string"}},
            }
        },
    }


def build_source(events, start, end, source_key, derivation_group):
    return {
        "source": {
            "key": source_key,
            "source_type_name": "MissionEvents",
            "derivation_group_name": derivation_group,
            "valid_at": fmt_instant(start - timedelta(days=1)),
            "period": {"start_time": fmt_instant(start), "end_time": fmt_instant(end)},
            "attributes": {
                "description": f"Generated scale-test external events ({len(events)} events)"
            },
        },
        "events": events,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=5000, help="approximate total number of events (default 5000)")
    ap.add_argument("--start", default="2028-001", help="window start, YYYY-DDD or full instant (default 2028-001)")
    ap.add_argument("--end", default="2029-001", help="window end (default 2029-001)")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    ap.add_argument("--contact-type", default="DSNContact",
                    help='name of the comms event type (default DSNContact; use DSS_Pass for hopper)')
    ap.add_argument("--out-dir", default=".", help="output directory (default current dir)")
    ap.add_argument("--prefix", default="external_events", help="output filename prefix")
    ap.add_argument("--source-key", default="ScaleTest_Events", help="external source key")
    ap.add_argument("--derivation-group", default="MissionEvents Default", help="derivation group name")
    args = ap.parse_args()

    start, end = parse_doy(args.start), parse_doy(args.end)
    events, per_type, catalog = generate(args.count, start, end, args.seed, args.contact_type)

    schema = build_schema(catalog, args.contact_type)
    source = build_source(events, start, end, args.source_key, args.derivation_group)

    import os
    os.makedirs(args.out_dir, exist_ok=True)
    schema_path = os.path.join(args.out_dir, f"{args.prefix}_schema.json")
    source_path = os.path.join(args.out_dir, f"{args.prefix}_source.json")
    with open(schema_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")
    with open(source_path, "w") as f:
        json.dump(source, f, indent=2)
        f.write("\n")

    print(f"Wrote {len(events)} events over {args.start} .. {args.end}")
    for name in sorted(per_type, key=lambda n: -per_type[n]):
        actual = sum(1 for e in events if e["event_type_name"] == name)
        print(f"  {name:<22} ~{actual}")
    print(f"Schema: {schema_path}")
    print(f"Source: {source_path}")
    print(f"\nUpload to PlanDev: the schema first (event/source types), then the source.")


if __name__ == "__main__":
    main()
