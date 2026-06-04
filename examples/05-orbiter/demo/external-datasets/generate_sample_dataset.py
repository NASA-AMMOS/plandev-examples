"""
Generate a sample external dataset for the 04-orbiter example.

Produces three profiles aligned to the SimplePlan time bounds
(start 2024-002T00:00:00, duration 144h = 6 days):

  - solarArrayInputPower (real, watts): sinusoidal with eclipse dips,
    ~90-minute orbital period.
  - instrumentTemperature (real, celsius): slow thermal drift around
    the orbit.
  - dsnContact (discrete, string enum): which Deep Space Network
    complex (GOLDSTONE / CANBERRA / MADRID / NONE) is in view.

Each profile contains SEGMENTS_PER_PROFILE segments (default 60,000),
so any single profile satisfies the >=50k-segment requirement.

Output: sample_dataset.json (~10-15 MB).
"""

import json
import math
from pathlib import Path

PLAN_ID = 6
DATASET_START = "2024-002T00:00:00"

DURATION_SECONDS = 144 * 3600
DURATION_MICROS = DURATION_SECONDS * 1_000_000

SEGMENTS_PER_PROFILE = 60_000
SEGMENT_DURATION_MICROS = DURATION_MICROS // SEGMENTS_PER_PROFILE
SEGMENT_DURATION_SECONDS = SEGMENT_DURATION_MICROS / 1_000_000

ORBITAL_PERIOD_SECONDS = 90 * 60
ECLIPSE_FRACTION = 0.35

DSN_STATIONS = ["GOLDSTONE", "CANBERRA", "MADRID"]
DSN_PERIOD_SECONDS = 8 * 3600


def solar_power(t_seconds: float) -> float:
    phase = (t_seconds % ORBITAL_PERIOD_SECONDS) / ORBITAL_PERIOD_SECONDS
    if phase < ECLIPSE_FRACTION:
        return 0.0
    sun_phase = (phase - ECLIPSE_FRACTION) / (1.0 - ECLIPSE_FRACTION)
    return round(420.0 * math.sin(math.pi * sun_phase), 4)


def instrument_temp(t_seconds: float) -> float:
    orbital = 4.0 * math.sin(2 * math.pi * t_seconds / ORBITAL_PERIOD_SECONDS)
    diurnal = 1.5 * math.sin(2 * math.pi * t_seconds / (24 * 3600))
    drift = 0.000005 * t_seconds
    return round(-20.0 + orbital + diurnal + drift, 4)


def dsn_contact(t_seconds: float) -> str:
    slot = int((t_seconds % (3 * DSN_PERIOD_SECONDS)) // DSN_PERIOD_SECONDS)
    sub = (t_seconds % DSN_PERIOD_SECONDS) / DSN_PERIOD_SECONDS
    if sub < 0.1 or sub > 0.9:
        return "NONE"
    return DSN_STATIONS[slot]


def build_real_segments(value_fn):
    segments = []
    for i in range(SEGMENTS_PER_PROFILE):
        t0 = i * SEGMENT_DURATION_SECONDS
        t1 = (i + 1) * SEGMENT_DURATION_SECONDS
        v0 = value_fn(t0)
        v1 = value_fn(t1)
        rate = (v1 - v0) / SEGMENT_DURATION_SECONDS
        segments.append({
            "duration": SEGMENT_DURATION_MICROS,
            "dynamics": {"initial": v0, "rate": round(rate, 6)},
        })
    return segments


def build_discrete_segments(value_fn):
    segments = []
    for i in range(SEGMENTS_PER_PROFILE):
        t = i * SEGMENT_DURATION_SECONDS
        segments.append({
            "duration": SEGMENT_DURATION_MICROS,
            "dynamics": value_fn(t),
        })
    return segments


def main():
    dataset = {
        "planId": PLAN_ID,
        "datasetStart": DATASET_START,
        "profileSet": {
            "solarArrayInputPower": {
                "type": "real",
                "schema": {
                    "type": "struct",
                    "items": {
                        "rate": {"type": "real"},
                        "initial": {"type": "real"},
                    },
                },
                "segments": build_real_segments(solar_power),
            },
            "instrumentTemperature": {
                "type": "real",
                "schema": {
                    "type": "struct",
                    "items": {
                        "rate": {"type": "real"},
                        "initial": {"type": "real"},
                    },
                },
                "segments": build_real_segments(instrument_temp),
            },
            "dsnContact": {
                "type": "discrete",
                "schema": {"type": "string"},
                "segments": build_discrete_segments(dsn_contact),
            },
        },
    }

    out_path = Path(__file__).parent / "sample_dataset.json"
    with out_path.open("w") as f:
        json.dump(dataset, f)

    total_segments = SEGMENTS_PER_PROFILE * len(dataset["profileSet"])
    print(f"Wrote {out_path}")
    print(f"Profiles: {len(dataset['profileSet'])}")
    print(f"Segments per profile: {SEGMENTS_PER_PROFILE:,}")
    print(f"Total segments: {total_segments:,}")
    print(f"Segment duration: {SEGMENT_DURATION_SECONDS:.3f}s")
    print(f"File size: {out_path.stat().st_size / 1_048_576:.1f} MiB")


if __name__ == "__main__":
    main()
