/**
 * Telemetry metadata mapping: numeric → float; enumerable discretes (variant /
 * boolean) → `enum` + `enumerations` (so OpenMCT plots them as a state line);
 * free-form strings stay `string` (table only). Every value keeps a range hint.
 */
import { describe, expect, it } from 'vitest';

import { isNumeric, isPlottable, profileTypeToValues, type TelemetryValue } from '../src/metadata';
import type { ProfileType } from '../src/types';

const REAL: ProfileType = { schema: { type: 'real' }, type: 'real' };
const INT_DISCRETE: ProfileType = { schema: { type: 'int' }, type: 'discrete' };
const BOOL: ProfileType = { schema: { type: 'boolean' }, type: 'discrete' };
const VARIANT: ProfileType = {
  schema: { type: 'variant', variants: [{ key: 'OFF', label: 'OFF' }, { key: 'ON', label: 'ON' }] },
  type: 'discrete',
};
const STRING: ProfileType = { schema: { type: 'string' }, type: 'discrete' };

const range = (type: ProfileType): TelemetryValue =>
  profileTypeToValues(type).find(v => v.key === 'value')!;

describe('isNumeric / isPlottable', () => {
  it('numeric covers real and int', () => {
    expect(isNumeric(REAL)).toBe(true);
    expect(isNumeric(INT_DISCRETE)).toBe(true);
    expect(isNumeric(STRING)).toBe(false);
  });

  it('plottable adds enumerable discretes but excludes free-form strings', () => {
    expect(isPlottable(REAL)).toBe(true);
    expect(isPlottable(BOOL)).toBe(true);
    expect(isPlottable(VARIANT)).toBe(true);
    expect(isPlottable(STRING)).toBe(false);
  });
});

describe('profileTypeToValues', () => {
  it('real → float', () => expect(range(REAL).format).toBe('float'));

  it('boolean → enum with false/true enumerations', () => {
    const r = range(BOOL);
    expect(r.format).toBe('enum');
    expect(r.enumerations).toEqual([
      { string: 'false', value: 0 },
      { string: 'true', value: 1 },
    ]);
  });

  it('variant → enum with one level per state', () => {
    const r = range(VARIANT);
    expect(r.format).toBe('enum');
    expect(r.enumerations).toEqual([
      { string: 'OFF', value: 0 },
      { string: 'ON', value: 1 },
    ]);
  });

  it('free-form string → string format, no enumerations (table only)', () => {
    const r = range(STRING);
    expect(r.format).toBe('string');
    expect(r.enumerations).toBeUndefined();
  });

  it('every range value carries a range hint (never rangeless → no PlotSeries crash)', () => {
    for (const type of [REAL, INT_DISCRETE, BOOL, VARIANT, STRING]) {
      expect(range(type).hints?.range).toBe(1);
    }
  });
});
