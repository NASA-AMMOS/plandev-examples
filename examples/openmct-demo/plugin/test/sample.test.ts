/**
 * Profile sampling: linear interp for `real`, step values for `discrete`, gaps
 * dropped, and the hardening guards — a malformed interval or dynamics must not
 * throw or emit NaN.
 */
import { describe, expect, it } from 'vitest';

import { type Datum, getIntervalInMs, minMaxDecimate, sampleProfile } from '../src/sample';
import type { Profile, ProfileSegment, ProfileType } from '../src/types';

function profile(type: ProfileType, segments: ProfileSegment[], duration = '02:00:00'): Profile {
  return { duration, name: 'r', profile_segments: segments, type };
}

const REAL: ProfileType = { schema: { type: 'real' }, type: 'real' };
const VARIANT: ProfileType = {
  schema: { type: 'variant', variants: [{ key: 'A', label: 'A' }, { key: 'B', label: 'B' }] },
  type: 'discrete',
};

describe('getIntervalInMs', () => {
  it('parses HH:MM:SS', () => expect(getIntervalInMs('01:00:00')).toBe(3_600_000));
  it('empty / null → 0', () => {
    expect(getIntervalInMs('')).toBe(0);
    expect(getIntervalInMs(null)).toBe(0);
  });
  it('a malformed interval returns 0 instead of throwing', () => {
    expect(() => getIntervalInMs('not-an-interval')).not.toThrow();
    expect(getIntervalInMs('not-an-interval')).toBe(0);
  });
});

describe('sampleProfile', () => {
  it('real profile emits 2 points per segment (linear interp endpoints)', () => {
    const datums = sampleProfile(
      profile(REAL, [
        { dynamics: { initial: 10, rate: 0 }, is_gap: false, start_offset: '00:00:00' },
        { dynamics: { initial: 20, rate: 0 }, is_gap: false, start_offset: '01:00:00' },
      ]),
      0,
    );
    expect(datums).toHaveLength(4);
    expect(datums[0]).toEqual({ utc: 0, value: 10 });
  });

  it('gap segments leave a break (no datums)', () => {
    const datums = sampleProfile(
      profile(REAL, [{ dynamics: null, is_gap: true, start_offset: '00:00:00' }]),
      0,
    );
    expect(datums).toHaveLength(0);
  });

  it('discrete passes the string state through (OpenMCT enum-maps it for plotting)', () => {
    const datums = sampleProfile(
      profile(VARIANT, [{ dynamics: 'A', is_gap: false, start_offset: '00:00:00' }]),
      0,
    );
    expect(datums[0].value).toBe('A');
  });

  it('malformed real dynamics never yields NaN', () => {
    const datums = sampleProfile(
      profile(REAL, [{ dynamics: { initial: 'oops' }, is_gap: false, start_offset: '00:00:00' }]),
      0,
    );
    expect(datums.every(d => typeof d.value !== 'number' || !Number.isNaN(d.value))).toBe(true);
  });
});

describe('minMaxDecimate', () => {
  const series = (n: number): Datum[] =>
    Array.from({ length: n }, (_, i) => ({ utc: i, value: i === 500 ? 9999 : i % 10 }));

  it('returns the input unchanged when already under the budget', () => {
    const datums = series(20);
    expect(minMaxDecimate(datums, 100)).toBe(datums);
  });

  it('returns the input unchanged when the budget is too small to bucket', () => {
    const datums = series(100);
    expect(minMaxDecimate(datums, 2)).toBe(datums);
  });

  it('thins a large series, keeping both endpoints and the spike, ascending by utc', () => {
    const datums = series(1000);
    const out = minMaxDecimate(datums, 50);

    expect(out.length).toBeLessThanOrEqual(52); // ~budget + 2 endpoints
    expect(out[0]).toBe(datums[0]);
    expect(out.at(-1)).toBe(datums[999]);
    expect(out.some(d => d.value === 9999)).toBe(true); // extremum preserved
    for (let i = 1; i < out.length; i++) {
      expect(out[i].utc).toBeGreaterThanOrEqual(out[i - 1].utc);
    }
  });
});
