/**
 * Shared plugin state: the PlanDev API client, the OpenMCT namespace, and small
 * caches so the tree can be built and resolved without redundant round-trips.
 */
import { isNumeric } from './metadata';
import { PlandevApi } from './plandev-api';
import { getIntervalInMs } from './sample';
import type { Plan, Profile, ProfileType, SimulationDataset } from './types';

export class PluginContext {
  readonly api: PlandevApi;
  readonly namespace: string;
  /** Default OpenMCT time bounds (epoch ms) — the most recent plan's span. */
  defaultBounds: { start: number; end: number } | null = null;

  readonly #plans = new Map<number, Plan>();
  readonly #simsByPlan = new Map<number, SimulationDataset[]>();
  readonly #profileTypes = new Map<number, Map<string, ProfileType>>();
  readonly #profiles = new Map<string, Promise<Profile | null>>();

  constructor(api: PlandevApi, namespace: string) {
    this.api = api;
    this.namespace = namespace;
  }

  async getPlans(): Promise<Plan[]> {
    const plans = await this.api.getPlans();
    for (const plan of plans) {
      this.#plans.set(plan.id, plan);
    }
    return plans;
  }

  async getPlan(planId: number): Promise<Plan | null> {
    const cached = this.#plans.get(planId);
    if (cached) {
      return cached;
    }
    const plan = await this.api.getPlan(planId);
    if (plan) {
      this.#plans.set(plan.id, plan);
    }
    return plan;
  }

  /** Epoch-ms anchor for a plan's profile offsets (the plan start time). */
  async getPlanStartMs(planId: number): Promise<number> {
    const plan = await this.getPlan(planId);
    return plan ? Date.parse(plan.start_time) : 0;
  }

  async getSimulationDatasets(planId: number): Promise<SimulationDataset[]> {
    const sims = await this.api.getSimulationDatasets(planId);
    this.#simsByPlan.set(planId, sims);
    return sims;
  }

  async getSimulationDataset(planId: number, simId: number): Promise<SimulationDataset | undefined> {
    const sims = await this.#getSimulationDatasetsCached(planId);
    return sims.find(sim => sim.id === simId);
  }

  async findSimByDataset(planId: number, datasetId: number): Promise<SimulationDataset | undefined> {
    const sims = await this.#getSimulationDatasetsCached(planId);
    return sims.find(sim => sim.dataset_id === datasetId);
  }

  async #getSimulationDatasetsCached(planId: number): Promise<SimulationDataset[]> {
    return this.#simsByPlan.get(planId) ?? (await this.getSimulationDatasets(planId));
  }

  /** Profile descriptors for a dataset (name → type), cached for object resolution. */
  async getProfileTypes(datasetId: number): Promise<Map<string, ProfileType>> {
    const cached = this.#profileTypes.get(datasetId);
    if (cached) {
      return cached;
    }
    const descriptors = await this.api.getProfileDescriptors(datasetId);
    const map = new Map<string, ProfileType>();
    for (const descriptor of descriptors) {
      map.set(descriptor.name, descriptor.type);
    }
    this.#profileTypes.set(datasetId, map);
    return map;
  }

  async getProfileType(datasetId: number, name: string): Promise<ProfileType | undefined> {
    return (await this.getProfileTypes(datasetId)).get(name);
  }

  /** The first `limit` numeric (plottable) resource names in a dataset, by name. */
  async getNumericResourceNames(datasetId: number, limit: number): Promise<string[]> {
    const types = await this.getProfileTypes(datasetId);
    const names: string[] = [];
    for (const [name, type] of types) {
      if (isNumeric(type)) {
        names.push(name);
        if (names.length >= limit) {
          break;
        }
      }
    }
    return names;
  }

  /**
   * Fetches a profile (with segments), cached by dataset+name. Caches the
   * promise so concurrent requests for the same resource (e.g. a grid preview
   * and a plot) share one fetch, and pans/zooms reuse it instead of refetching.
   */
  getProfile(datasetId: number, name: string): Promise<Profile | null> {
    const key = `${datasetId}:${name}`;
    let pending = this.#profiles.get(key);
    if (!pending) {
      pending = this.api.getProfile(datasetId, name);
      this.#profiles.set(key, pending);
      // If the fetch rejects, drop it so a later request can retry.
      pending.catch(() => this.#profiles.delete(key));
    }
    return pending;
  }

  /** Records the most-recent plan's span as the default conductor bounds. */
  rememberBounds(plan: Plan): void {
    if (this.defaultBounds) {
      return;
    }
    const start = Date.parse(plan.start_time);
    const end = start + getIntervalInMs(plan.duration);
    if (!Number.isNaN(start) && end > start) {
      this.defaultBounds = { end, start };
    }
  }
}
