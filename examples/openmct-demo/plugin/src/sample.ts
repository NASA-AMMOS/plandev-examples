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
  const { days, hours, milliseconds, minutes, seconds } = parseInterval(interval);
  return (
    days * 24 * 60 * 60 * 1000 +
    hours * 60 * 60 * 1000 +
    minutes * 60 * 1000 +
    seconds * 1000 +
    milliseconds
  );
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
      const { initial, rate } = (segment.dynamics ?? {}) as { initial: number; rate: number };
      datums.push({ utc: datasetStartMs + offsetMs, value: initial });
      datums.push({
        utc: datasetStartMs + nextOffsetMs,
        value: initial + rate * ((nextOffsetMs - offsetMs) / 1000),
      });
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
