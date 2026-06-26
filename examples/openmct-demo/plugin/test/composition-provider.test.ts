/**
 * The dynamic composition provider's refresh diff: on reload, only children that are
 * new, gone, or changed-signature (a sim's status) are emitted as remove/add — so a
 * finished sim re-resolves while unchanged (expanded) nodes are left alone.
 */
import { describe, expect, it } from 'vitest';

import { createCompositionProvider } from '../src/composition-provider';
import type { PluginContext } from '../src/context';
import type { DomainObject, Identifier } from '../src/openmct';
import type { SimulationDataset } from '../src/types';

const PLAN: DomainObject = { identifier: { key: 'plan:3', namespace: 'plandev' }, name: 'p', type: 'folder' };

/** A context whose sim list is read live from `ref`, so a test can mutate it between calls. */
function contextWithSims(ref: { sims: SimulationDataset[] }): PluginContext {
  return {
    getNumericResourceNames: async () => [],
    getPlanDerivationGroups: async () => [],
    getPlans: async () => [],
    getProfileTypes: async () => new Map(),
    getSimulationDatasets: async () => ref.sims,
    namespace: 'plandev',
    notifier: { error() {} },
    rememberBounds() {},
  } as unknown as PluginContext;
}

function sim(id: number, status: string): SimulationDataset {
  return { dataset_id: id * 10, id, simulation_end_time: null, simulation_start_time: null, status };
}

/** Subscribe and capture emitted add/remove child keys. */
function track(provider: ReturnType<typeof createCompositionProvider>) {
  const added: string[] = [];
  const removed: string[] = [];
  provider.on(PLAN, 'add', (c: Identifier) => added.push(c.key));
  provider.on(PLAN, 'remove', (c: Identifier) => removed.push(c.key));
  return { added, removed };
}

describe('composition refresh diff', () => {
  it('re-resolves only the sim whose status changed; leaves others untouched', async () => {
    const ref = { sims: [sim(1, 'pending'), sim(2, 'success')] };
    const provider = createCompositionProvider(contextWithSims(ref));
    await provider.load(PLAN);
    const { added, removed } = track(provider);

    ref.sims = [sim(1, 'success'), sim(2, 'success')]; // sim 1 finished
    await provider.refresh(PLAN);

    expect(removed).toEqual(['sim:3:1:10']);
    expect(added).toEqual(['sim:3:1:10']); // removed + re-added → re-resolves the label
  });

  it('adds a new sim and removes a deleted one, touching nothing else', async () => {
    const ref = { sims: [sim(1, 'success'), sim(2, 'success')] };
    const provider = createCompositionProvider(contextWithSims(ref));
    await provider.load(PLAN);
    const { added, removed } = track(provider);

    ref.sims = [sim(2, 'success'), sim(3, 'success')]; // sim 1 gone, sim 3 new
    await provider.refresh(PLAN);

    expect(removed).toEqual(['sim:3:1:10']);
    expect(added).toEqual(['sim:3:3:30']);
  });

  it('emits nothing when nothing changed', async () => {
    const ref = { sims: [sim(1, 'success'), sim(2, 'success')] };
    const provider = createCompositionProvider(contextWithSims(ref));
    await provider.load(PLAN);
    const { added, removed } = track(provider);

    await provider.refresh(PLAN);

    expect(added).toEqual([]);
    expect(removed).toEqual([]);
  });
});
