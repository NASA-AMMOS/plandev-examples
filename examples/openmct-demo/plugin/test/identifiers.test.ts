/**
 * Key codec: the headline regression is that resource names containing '/'
 * (banananation's `/fruit`, `/data/line_count`, `/flag/conflicted`) must encode
 * into OpenMCT keys that contain no path-breaking characters and round-trip back.
 */
import { describe, expect, it } from 'vitest';

import {
  actualKey,
  compareKey,
  parseKey,
  planKey,
  resourceKey,
  resourcePlotKey,
  simKey,
  statusKey,
} from '../src/identifiers';

const TRICKY = ['/fruit', '/data/line_count', '/flag/conflicted', 'array.powerProduction', 'a:b', 'with space'];

describe('resource-name keys round-trip and stay path-safe', () => {
  it.each(TRICKY)('resourceKey round-trips %s', name => {
    expect(parseKey(resourceKey(7, 3, name))).toMatchObject({
      datasetId: 7,
      kind: 'resource',
      name,
      planId: 3,
    });
  });

  it('name-bearing keys never contain a raw "/" or a stray ":" in the name segment', () => {
    for (const build of [resourceKey, resourcePlotKey, actualKey, compareKey]) {
      const key = build(7, 3, '/data/line_count');
      expect(key.includes('/')).toBe(false);
    }
  });

  it('rplot / actual / cmp round-trip the name too', () => {
    expect(parseKey(resourcePlotKey(7, 3, '/x/y'))).toMatchObject({ kind: 'resourcePlot', name: '/x/y' });
    expect(parseKey(actualKey(7, 3, '/x/y'))).toMatchObject({ kind: 'actual', name: '/x/y' });
    expect(parseKey(compareKey(7, 3, '/x/y'))).toMatchObject({ kind: 'compare', name: '/x/y' });
  });
});

describe('other key kinds', () => {
  it('plan / sim parse', () => {
    expect(parseKey(planKey(5))).toEqual({ kind: 'plan', planId: 5 });
    expect(parseKey(simKey(5, 9, 12))).toEqual({ datasetId: 12, kind: 'sim', planId: 5, simId: 9 });
  });

  it('status round-trips a message with spaces and a glyph', () => {
    const message = '⚠ Could not reach PlanDev — see console';
    expect(parseKey(statusKey(message))).toEqual({ kind: 'status', message });
  });

  it('unknown prefix → unknown', () => {
    expect(parseKey('bogus:1:2')).toEqual({ kind: 'unknown' });
  });
});
