"""
Generate a JPL-Horizons-validated external dataset of Sun & Earth elevation
for the hopper model, as seen from a fixed point on the lunar surface.

This is Phase 1 of the "Sun & Earth Elevation for the Hopper Model" plan: it
produces the *reference* time-series that the in-sim simulated resource
(SurfaceGeometryCalculator, a later phase) is validated against -- mirroring the
"JPL Horizons reference" dots in the reference web tool.

Two profiles, aligned to a plan's time bounds:

  - sunElevation   (real, degrees): apparent elevation of the Sun above the
    local horizon. Near the lunar south pole this grazes the horizon (~+-4 deg).
  - earthElevation (real, degrees): apparent elevation of the Earth. At the pole
    Earth sits near the horizon and oscillates ~+-9 deg due to lunar libration.

The elevation is computed with the SAME method the Java SurfaceGeometryCalculator
will use -- spherical Moon, radial "up", target position from spkpos rotated into
the IAU_MOON body-fixed frame via pxform -- so Phase 3 is an apples-to-apples
check (any mismatch is an implementation bug, not a method difference).

Independent cross-checks (do not affect the emitted dataset):
  --fidelity : compares the manual method against SPICE's own topocentric routine
               spiceypy.azlcpo at sampled epochs (same kernels, different code
               path -- catches conceptual errors in the manual method).
  --horizons : also emit independent JPL Horizons reference profiles
               (sunElevationHorizons / earthElevationHorizons) -- the chart's
               "reference" series, an independent overlay to validate the
               simulated resource against in Phase 3 -- and report the computed-
               vs-Horizons deviation (settles the IAU_MOON-vs-MOON_ME question).
               One range request per target. Requires network; non-fatal on error.

Kernels: reuses the shared top-level spice-kernels/ (de440s.bsp for the Moon
ephemeris, pck00011.tpc for the IAU_MOON frame, naif0012.tls for leap seconds).
No new kernels are needed. Override the directory with SPICE_DIRECTORY.

Output: lunar_elevation_dataset.json (real-typed profiles, {initial, rate}
linear segments at --step-minutes resolution). Keep the row count modest:
PlanDev ingests external-dataset segments at only ~hundreds of rows/sec, so
hourly over a year (~8.7k seg/profile) ingests in ~1 min, whereas sub-10-minute
resolution over a year (~60k) takes several minutes. Elevation is smooth, so
hourly is visually indistinguishable from finer sampling.
"""

import argparse
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import spiceypy as spice

# --- Site & target defaults -------------------------------------------------

# Lunar south-pole site from the reference tool (planetocentric, east-positive).
DEFAULT_LAT_DEG = -87.5
DEFAULT_LON_DEG = 5.0

MOON_ID = "301"
SUN_ID = "10"
EARTH_ID = "399"
ABCORR = "LT+S"          # apparent direction; matches JPL Horizons + the Java model
BODY_FRAME = "IAU_MOON"  # libration-bearing body-fixed frame (from pck00011.tpc)

# --- Plan/time defaults -----------------------------------------------------

DEFAULT_PLAN_ID = 1            # MUST match the PlanDev plan you upload to
DEFAULT_START = "2028-01-01"   # year chosen to line up with the reference chart
DEFAULT_DAYS = 365             # full year (matches the reference chart's full-year view)
DEFAULT_STEP_MINUTES = 60      # hourly. Elevation varies slowly, so linear segments at this
                               # resolution stay smooth while keeping the row count -- and
                               # therefore PlanDev's per-segment ingest time -- low. There is
                               # NO minimum segment count; more segments just ingest slower
                               # (PlanDev inserts ~hundreds of profile_segment rows/sec).


def repo_spice_dir() -> Path:
    """Shared kernel directory: $SPICE_DIRECTORY, else the nearest spice-kernels/
    found by walking up from this file (robust to where the example lives)."""
    env = os.environ.get("SPICE_DIRECTORY")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "spice-kernels"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"No 'spice-kernels' directory found above {here}; set SPICE_DIRECTORY."
    )


def furnish_kernels(spice_dir: Path) -> None:
    needed = ["naif0012.tls", "pck00011.tpc", "de440s.bsp"]
    missing = [k for k in needed if not (spice_dir / k).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing kernels {missing} in {spice_dir}. "
            f"Set SPICE_DIRECTORY or run `git lfs pull`."
        )
    for k in needed:
        spice.furnsh(str(spice_dir / k))


def moon_radius_km() -> float:
    """Mean lunar radius (spherical-Moon assumption), from the loaded PCK."""
    _, radii = spice.bodvrd("MOON", "RADII", 3)
    return float(np.mean(radii))


def observer_bf(r_moon_km: float, lat_rad: float, lon_rad: float) -> np.ndarray:
    """Observer rectangular position in the IAU_MOON frame (spherical Moon)."""
    return np.array(spice.latrec(r_moon_km, lon_rad, lat_rad))


def elevation_deg(et: float, target: str, r_obs: np.ndarray, up: np.ndarray) -> float:
    """
    Apparent elevation (deg) of `target` above the local horizon at `et`.

    Mirror of the Java SurfaceGeometryCalculator: target position relative to the
    Moon center in J2000 (LT+S), rotated into IAU_MOON, minus the surface offset.
    Keeping the full `- r_obs` term is what produces Earth's +-9 deg libration
    swing -- never approximate look ~= target.
    """
    pos_j2000, _ = spice.spkpos(target, et, "J2000", ABCORR, MOON_ID)
    rot = spice.pxform("J2000", BODY_FRAME, et)          # J2000 -> IAU_MOON
    tgt_bf = np.array(rot).dot(np.array(pos_j2000))
    look = tgt_bf - r_obs
    return 90.0 - math.degrees(spice.vsep(look, up))


# --- Dataset assembly -------------------------------------------------------


def build_real_segments(value_fn, n_segments, seg_dur_s, seg_dur_us):
    """Linear {initial, rate} segments approximating value_fn over each step."""
    segments = []
    for i in range(n_segments):
        t0 = i * seg_dur_s
        v0 = value_fn(t0)
        v1 = value_fn(t0 + seg_dur_s)
        rate = (v1 - v0) / seg_dur_s
        segments.append({
            "duration": seg_dur_us,
            "dynamics": {"initial": round(v0, 6), "rate": round(rate, 9)},
        })
    return segments


REAL_PROFILE_SCHEMA = {
    "type": "struct",
    "items": {"rate": {"type": "real"}, "initial": {"type": "real"}},
}


def doy_string(dt: datetime) -> str:
    """PlanDev DOY datasetStart format, e.g. 2028-001T00:00:00."""
    return f"{dt.year}-{dt.timetuple().tm_yday:03d}T{dt:%H:%M:%S}"


# --- Cross-checks (do not affect the emitted dataset) -----------------------


def azlcpo_elevation_deg(et: float, target: str, r_obs: np.ndarray) -> float:
    """Independent elevation via SPICE's topocentric routine (same kernels)."""
    azlsta, _ = spice.azlcpo(
        "ELLIPSOID", target, et, ABCORR,
        False,   # azccw: azimuth measured clockwise (from north)
        True,    # elplsz: elevation positive toward +Z (up)
        r_obs, MOON_ID, BODY_FRAME,
    )
    return math.degrees(azlsta[2])


def run_fidelity_check(et0, span_s, r_obs, up, n=12):
    print("\n-- Fidelity: manual (spherical/pxform) vs SPICE azlcpo --")
    worst = 0.0
    for k in range(n):
        et = et0 + span_s * k / (n - 1)
        for name, tid in (("sun", SUN_ID), ("earth", EARTH_ID)):
            man = elevation_deg(et, tid, r_obs, up)
            azl = azlcpo_elevation_deg(et, tid, r_obs)
            worst = max(worst, abs(man - azl))
    print(f"   max |manual - azlcpo| over {n} epochs x2 targets: {worst:.4f} deg")
    print("   (expect << 0.1 deg near the pole; large => method bug)")


def horizons_elevation_series(target, lat_deg, lon_deg, start_dt, stop_dt, n_steps, ssl_ctx=None):
    """
    Apparent elevation (deg) at n_steps+1 equally spaced epochs over
    [start_dt, stop_dt], via a single JPL Horizons range request
    (EPHEM_TYPE=OBSERVER, QUANTITIES=4 -> azimuth & elevation). Returns a list
    of n_steps+1 floats aligned to the dataset's segment boundaries.
    """
    import urllib.parse
    import urllib.request

    if n_steps > 90_000:
        raise ValueError(
            f"Horizons caps output near 90k rows; {n_steps} steps is too many. "
            f"Use a coarser --step-minutes for the Horizons overlay."
        )
    params = {
        "format": "text", "COMMAND": f"'{target}'", "EPHEM_TYPE": "OBSERVER",
        "CENTER": "'coord@301'", "COORD_TYPE": "GEODETIC",
        "SITE_COORD": f"'{lon_deg},{lat_deg},0'",
        "QUANTITIES": "'4'",  # azimuth & elevation
        "START_TIME": f"'{start_dt:%Y-%m-%d %H:%M}'",
        "STOP_TIME": f"'{stop_dt:%Y-%m-%d %H:%M}'",
        "STEP_SIZE": f"'{n_steps}'",  # integer => n_steps+1 equally spaced rows
        "CSV_FORMAT": "YES", "ANG_FORMAT": "DEG",
    }
    url = "https://ssd.jpl.nasa.gov/api/horizons.api?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120, context=ssl_ctx) as resp:
        text = resp.read().decode()
    body = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip().splitlines()
    # CSV per row: Date, (blank), (flag), Azi_(a-app), Elev_(a-app), (trailing)
    return [float(row.split(",")[4]) for row in body]


def build_segments_from_series(values, seg_dur_s, seg_dur_us):
    """Real {initial, rate} segments connecting consecutive sampled values."""
    segments = []
    for i in range(len(values) - 1):
        v0, v1 = values[i], values[i + 1]
        rate = (v1 - v0) / seg_dur_s
        segments.append({
            "duration": seg_dur_us,
            "dynamics": {"initial": round(v0, 6), "rate": round(rate, 9)},
        })
    return segments


# --- Main -------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, default=DEFAULT_LAT_DEG, help="site latitude (deg)")
    ap.add_argument("--lon", type=float, default=DEFAULT_LON_DEG, help="site longitude (deg, east+)")
    ap.add_argument("--start", default=DEFAULT_START, help="UTC start date YYYY-MM-DD")
    ap.add_argument("--days", type=float, default=DEFAULT_DAYS, help="span in days")
    ap.add_argument("--step-minutes", type=float, default=DEFAULT_STEP_MINUTES, help="segment resolution in minutes (larger = fewer rows = faster ingest)")
    ap.add_argument("--plan-id", type=int, default=DEFAULT_PLAN_ID, help="PlanDev plan id to attach to")
    ap.add_argument("--out", default=None, help="output JSON path")
    ap.add_argument("--fidelity", action="store_true", help="run offline azlcpo cross-check")
    ap.add_argument("--horizons", action="store_true", help="also emit JPL Horizons reference profiles + report deviation (network)")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification for the Horizons request (proxy/self-signed cert environments)")
    args = ap.parse_args()

    spice_dir = repo_spice_dir()
    furnish_kernels(spice_dir)
    try:
        r_moon = moon_radius_km()
        lat_rad = math.radians(args.lat)
        lon_rad = math.radians(args.lon)
        r_obs = observer_bf(r_moon, lat_rad, lon_rad)
        up = r_obs / np.linalg.norm(r_obs)

        start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        et0 = spice.str2et(start_dt.strftime("%Y-%m-%dT%H:%M:%S"))
        span_s = args.days * 86_400.0

        seg_dur_us = int(round(args.step_minutes * 60_000_000))
        seg_dur_s = seg_dur_us / 1_000_000.0
        n_segments = max(1, int(round(span_s * 1_000_000 / seg_dur_us)))

        def sun_el(t_s):
            return elevation_deg(et0 + t_s, SUN_ID, r_obs, up)

        def earth_el(t_s):
            return elevation_deg(et0 + t_s, EARTH_ID, r_obs, up)

        print(f"Site: lat={args.lat} lon={args.lon}  Moon R={r_moon:.3f} km  frame={BODY_FRAME}")
        print(f"Span: {args.start} + {args.days}d  step={args.step_minutes}min  segments/profile={n_segments:,}")
        print("Computing sunElevation ...")
        sun_segments = build_real_segments(sun_el, n_segments, seg_dur_s, seg_dur_us)
        print("Computing earthElevation ...")
        earth_segments = build_real_segments(earth_el, n_segments, seg_dur_s, seg_dur_us)

        profile_set = {
            "sunElevation": {"type": "real", "schema": REAL_PROFILE_SCHEMA, "segments": sun_segments},
            "earthElevation": {"type": "real", "schema": REAL_PROFILE_SCHEMA, "segments": earth_segments},
        }

        # Optional: add independent JPL Horizons reference profiles (the chart's
        # "reference" series). One range request per target; non-fatal on failure.
        if args.horizons:
            try:
                ssl_ctx = None
                if args.insecure:
                    import ssl
                    ssl_ctx = ssl._create_unverified_context()
                    print("(--insecure: TLS verification disabled for Horizons requests)")
                stop_dt = start_dt + timedelta(seconds=span_s)
                print("Fetching JPL Horizons sunElevation reference ...")
                h_sun = horizons_elevation_series(SUN_ID, args.lat, args.lon, start_dt, stop_dt, n_segments, ssl_ctx)
                print("Fetching JPL Horizons earthElevation reference ...")
                h_earth = horizons_elevation_series(EARTH_ID, args.lat, args.lon, start_dt, stop_dt, n_segments, ssl_ctx)
                profile_set["sunElevationHorizons"] = {
                    "type": "real", "schema": REAL_PROFILE_SCHEMA,
                    "segments": build_segments_from_series(h_sun, seg_dur_s, seg_dur_us)}
                profile_set["earthElevationHorizons"] = {
                    "type": "real", "schema": REAL_PROFILE_SCHEMA,
                    "segments": build_segments_from_series(h_earth, seg_dur_s, seg_dur_us)}
                stride = max(1, n_segments // 500)
                d_sun = max(abs(sun_segments[i]["dynamics"]["initial"] - h_sun[i]) for i in range(0, n_segments, stride))
                d_earth = max(abs(earth_segments[i]["dynamics"]["initial"] - h_earth[i]) for i in range(0, n_segments, stride))
                print(f"  computed vs Horizons: max |d| sun={d_sun:.3f} deg, earth={d_earth:.3f} deg")
                print("  (small => IAU_MOON adequate; large => consider MOON_ME)")
            except Exception as e:  # noqa: BLE001 -- network/format; non-fatal
                print(f"[horizons] skipped ({e}); writing computed-only dataset.")

        dataset = {
            "planId": args.plan_id,
            "datasetStart": doy_string(start_dt),
            "profileSet": profile_set,
        }

        out_path = Path(args.out) if args.out else Path(__file__).parent / "lunar_elevation_dataset.json"
        with out_path.open("w") as f:
            json.dump(dataset, f)

        sun_vals = [s["dynamics"]["initial"] for s in sun_segments]
        earth_vals = [s["dynamics"]["initial"] for s in earth_segments]
        print(f"\nWrote {out_path}  ({out_path.stat().st_size / 1_048_576:.1f} MiB)")
        print(f"  profiles: {list(profile_set)}")
        print(f"  sunElevation   range: [{min(sun_vals):.2f}, {max(sun_vals):.2f}] deg")
        print(f"  earthElevation range: [{min(earth_vals):.2f}, {max(earth_vals):.2f}] deg")
        print(f"  total segments: {sum(len(p['segments']) for p in profile_set.values()):,}")

        if args.fidelity:
            run_fidelity_check(et0, span_s, r_obs, up)
    finally:
        spice.kclear()


if __name__ == "__main__":
    main()
