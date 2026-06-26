/**
 * getStringEnumerations turns a free-form string resource's observed states into
 * OpenMCT enumerations, so a resource like `/producer` (Frank/Chiquita) can plot as
 * a stepped state line instead of only tabling.
 */
import { describe, expect, it } from 'vitest';

import { PluginContext } from '../src/context';
import type { Profile, ProfileSegment } from '../src/types';

function contextWithProfile(profile: Profile | null): PluginContext {
  const api = { getProfile: async () => profile } as unknown as ConstructorParameters<
    typeof PluginContext
  >[0];
  return new PluginContext(api, 'plandev', { error() {} });
}

function stringProfile(values: string[]): Profile {
  const segments: ProfileSegment[] = values.map((v, i) => ({
    dynamics: v,
    is_gap: false,
    start_offset: `0${i}:00:00`,
  }));
  return {
    duration: '10:00:00',
    name: '/producer',
    profile_segments: segments,
    type: { schema: { type: 'string' }, type: 'discrete' },
  };
}

describe('getStringEnumerations', () => {
  it('maps distinct states to enumerations in first-seen order', async () => {
    const ctx = contextWithProfile(stringProfile(['Chiquita', 'Frank', 'Chiquita', 'Frank']));
    expect(await ctx.getStringEnumerations(7, '/producer')).toEqual([
      { string: 'Chiquita', value: 0 },
      { string: 'Frank', value: 1 },
    ]);
  });

  it('returns null when there is no profile or nothing to enumerate', async () => {
    expect(await contextWithProfile(null).getStringEnumerations(7, 'x')).toBeNull();
    expect(await contextWithProfile(stringProfile([])).getStringEnumerations(7, 'x')).toBeNull();
  });

  it('returns null when there are too many distinct states (keep it a table)', async () => {
    const ctx = contextWithProfile(stringProfile(['a', 'b', 'c', 'd', 'e']));
    expect(await ctx.getStringEnumerations(7, 'x', 3)).toBeNull();
  });
});
