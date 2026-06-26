/**
 * Converts PlanDev profiles into flat OpenMCT telemetry datums.
 *
 * This is a focused port of plandev-ui's `sampleProfiles`
 * (src/utilities/resources.ts) for a single profile, emitting `{ utc, value }`
 * datums OpenMCT plots directly. Interval parsing uses the same
 * `postgres-interval` package plandev-ui uses, for exact parity.
 */
import parseInterval from 'postgres-interval';

import type { Profile } from './types';

/** A single OpenMCT telemetry point: epoch-ms timestamp + value. */
export interface Datum {
  utc: number;
  value: number | string;
}

/** Postgres interval text → milliseconds (mirrors plandev-ui getIntervalInMs). */
export function getIntervalInMs(interval: string | null | undefined): number {
  if (interval === null || interval === undefined || interval === '') {
    return 0;
  }
  try {
    const { days, hours, milliseconds, minutes, seconds } = parseInterval(interval);
    return (
      days * 24 * 60 * 60 * 1000 +
      hours * 60 * 60 * 1000 +
      minutes * 60 * 1000 +
      seconds * 1000 +
      milliseconds
    );
  } catch {
    // A malformed interval shouldn't take down the whole profile's telemetry.
    console.warn(`PlanDev: could not parse interval "${interval}" — treating as 0`);
    return 0;
  }
}

/**
 * Samples one profile at its change points, returning step/linear datums.
 *
 * @param profile        the PlanDev profile (with segments).
 * @param datasetStartMs epoch-ms anchor for offset 0 (the plan/sim start).
 */
export function sampleProfile(profile: Profile, datasetStartMs: number): Datum[] {
  const datums: Datum[] = [];
  const { duration, profile_segments: segments, type: profileType } = profile;
  const durationMs = getIntervalInMs(duration);
  const isReal = profileType.type === 'real';

  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i];
    if (segment.is_gap) {
      continue; // a gap means "no data here" — leave a break in the series
    }
    const next = segments[i + 1];
    const offsetMs = getIntervalInMs(segment.start_offset);
    const nextOffsetMs = next ? getIntervalInMs(next.start_offset) : durationMs;

    if (isReal) {
      // Guard against a malformed `{initial, rate}` (missing/non-numeric) so one
      // bad segment yields no points rather than NaN that breaks the y-axis.
      const dynamics = (segment.dynamics ?? {}) as { initial?: unknown; rate?: unknown };
      const initial = typeof dynamics.initial === 'number' ? dynamics.initial : 0;
      const rate = typeof dynamics.rate === 'number' ? dynamics.rate : 0;
      const endValue = initial + rate * ((nextOffsetMs - offsetMs) / 1000);
      if (Number.isNaN(initial) || Number.isNaN(endValue)) {
        continue;
      }
      datums.push({ utc: datasetStartMs + offsetMs, value: initial });
      datums.push({ utc: datasetStartMs + nextOffsetMs, value: endValue });
    } else {
      const value = coerceDiscrete(segment.dynamics);
      datums.push({ utc: datasetStartMs + offsetMs, value });
      datums.push({ utc: datasetStartMs + nextOffsetMs, value });
    }
  }
  return datums;
}

/** Discrete dynamics are usually a string/number/bool; render anything else as JSON. */
function coerceDiscrete(dynamics: unknown): number | string {
  if (typeof dynamics === 'number' || typeof dynamics === 'string') {
    return dynamics;
  }
  if (typeof dynamics === 'boolean') {
    return String(dynamics);
  }
  return JSON.stringify(dynamics);
}

/**
 * Min/max-preserving decimation for a numeric series, for plot requests that ask for a
 * bounded point count (`strategy: 'minmax'`, `size` ≈ pixel width). Keeps both endpoints
 * and, per time bucket, the min and max points — so spikes/troughs survive while the
 * point count drops to ~`maxPoints`. Returns the input unchanged when it's already small
 * (or `maxPoints` is too small to be worth it). Only meaningful for numeric values.
 */
export function minMaxDecimate(datums: Datum[], maxPoints: number): Datum[] {
  if (maxPoints < 4 || datums.length <= maxPoints) {
    return datums;
  }
  const buckets = Math.floor(maxPoints / 2); // 2 extrema per bucket + 2 endpoints
  const step = datums.length / buckets;
  const out: Datum[] = [datums[0]];
  for (let b = 0; b < buckets; b++) {
    const start = Math.floor(b * step);
    const end = Math.min(datums.length, Math.floor((b + 1) * step));
    let min = datums[start];
    let max = datums[start];
    for (let i = start; i < end; i++) {
      const value = datums[i].value;
      if (typeof value !== 'number') {
        continue;
      }
      if (typeof min.value !== 'number' || value < min.value) {
        min = datums[i];
      }
      if (typeof max.value !== 'number' || value > max.value) {
        max = datums[i];
      }
    }
    // Emit the two extrema in time order so the series stays ascending by utc.
    const [first, second] = min.utc <= max.utc ? [min, max] : [max, min];
    if (out[out.length - 1] !== first) {
      out.push(first);
    }
    if (first !== second) {
      out.push(second);
    }
  }
  const last = datums[datums.length - 1];
  if (out[out.length - 1] !== last) {
    out.push(last);
  }
  return out;
}
