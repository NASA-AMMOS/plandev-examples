/**
 * boundsFromMeta derives time-conductor bounds from the `plandevMeta` the object
 * provider attaches: a plan's span, or a sim's own run window (falling back to the
 * plan span), and nothing for non-plan/sim nodes or unusable ranges.
 */
import { describe, expect, it } from 'vitest';

import { boundsFromMeta } from '../src/conductor-action';

const A = '2024-01-01T00:00:00Z';
const B = '2024-01-10T00:00:00Z';
const ms = (iso: string) => Date.parse(iso);

describe('boundsFromMeta', () => {
  it('uses the plan span for a plan', () => {
    expect(boundsFromMeta({ endTime: B, kind: 'plan', startTime: A })).toEqual({
      end: ms(B),
      start: ms(A),
    });
  });

  it('prefers a sim run window over the plan span', () => {
    expect(
      boundsFromMeta({
        endTime: B,
        kind: 'sim',
        simEnd: '2024-01-03T00:00:00Z',
        simStart: '2024-01-02T00:00:00Z',
        startTime: A,
      }),
    ).toEqual({ end: ms('2024-01-03T00:00:00Z'), start: ms('2024-01-02T00:00:00Z') });
  });

  it('falls back to the plan span when a sim has no run window', () => {
    expect(
      boundsFromMeta({ endTime: B, kind: 'sim', simEnd: null, simStart: null, startTime: A }),
    ).toEqual({ end: ms(B), start: ms(A) });
  });

  it('returns null for non-plan/sim nodes, missing meta, and bad ranges', () => {
    expect(boundsFromMeta(undefined)).toBeNull();
    expect(boundsFromMeta({ endTime: B, kind: 'resource', startTime: A })).toBeNull();
    expect(boundsFromMeta({ endTime: A, kind: 'plan', startTime: B })).toBeNull(); // inverted
    expect(boundsFromMeta({ endTime: 'nope', kind: 'plan', startTime: 'nope' })).toBeNull();
    expect(boundsFromMeta({ kind: 'plan', startTime: A })).toBeNull(); // no end
  });
});
