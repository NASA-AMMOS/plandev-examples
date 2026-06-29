/**
 * Shared plugin state: the PlanDev API client, the OpenMCT namespace, and small
 * caches so the tree can be built and resolved without redundant round-trips.
 */
import { isNumeric, isPlottable } from './metadata';
import type { Notifier } from './openmct';
import { PlandevApi } from './plandev-api';
import { type Datum, getIntervalInMs, sampleProfile } from './sample';
import type { ExternalEvent, Plan, Profile, ProfileType, SimulationDataset, ValueSchema } from './types';

export class PluginContext {
  readonly api: PlandevApi;
  readonly namespace: string;
  /** Throttled error notifier — providers use it to surface failures to the planner. */
  readonly notifier: Notifier;
  /** Default OpenMCT time bounds (epoch ms) — the most recent plan's span. */
  defaultBounds: { start: number; end: number } | null = null;

  readonly #plans = new Map<number, Plan>();
  readonly #simsByPlan = new Map<number, SimulationDataset[]>();
  readonly #profileTypes = new Map<number, Map<string, ProfileType>>();
  readonly #profiles = new Map<string, Promise<Profile | null>>();
  readonly #datums = new Map<string, Datum[]>();
  readonly #resourceSchemas = new Map<number, Promise<Map<string, ValueSchema>>>();
  readonly #directiveNames = new Map<number, Promise<Map<number, string>>>();

  constructor(api: PlandevApi, namespace: string, notifier: Notifier) {
    this.api = api;
    this.namespace = namespace;
    this.notifier = notifier;
  }

  /**
   * Drops every cache so the next load re-fetches from PlanDev. Wired to OpenMCT's
   * Reload action — without it, an open folder's reload would re-serve cached
   * (stale) sims/resources. (Re-fetches are lazy: caches refill as the tree reloads.)
   */
  invalidate(): void {
    this.#plans.clear();
    this.#simsByPlan.clear();
    this.#profileTypes.clear();
    this.#profiles.clear();
    this.#datums.clear();
    this.#resourceSchemas.clear();
    this.#directiveNames.clear();
    this.defaultBounds = null;
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

  /** The first `limit` numeric resource names in a dataset, by name. Used for the
   * predict-vs-actual overlays, where perturbation only makes sense for real values. */
  async getNumericResourceNames(datasetId: number, limit: number): Promise<string[]> {
    return this.#resourceNamesWhere(datasetId, limit, isNumeric);
  }

  /** The first `limit` PLOTTABLE resource names (numeric or enumerable-discrete),
   * for the ready-made Resource Plot layout. */
  async getPlottableResourceNames(datasetId: number, limit: number): Promise<string[]> {
    return this.#resourceNamesWhere(datasetId, limit, isPlottable);
  }

  async #resourceNamesWhere(
    datasetId: number,
    limit: number,
    predicate: (type: ProfileType) => boolean,
  ): Promise<string[]> {
    const types = await this.getProfileTypes(datasetId);
    const names: string[] = [];
    for (const [name, type] of types) {
      if (predicate(type)) {
        names.push(name);
        if (names.length >= limit) {
          break;
        }
      }
    }
    return names;
  }

  /**
   * Distinct states of a free-form string resource (e.g. `/producer` = Frank/Chiquita),
   * as OpenMCT `enumerations` so the regular Plot can render it as a stepped state line.
   * Fetches the profile (cached) since the value set isn't in the schema. Returns null
   * when there's nothing to enumerate or too many distinct states to plot usefully
   * (keep it a table). `cap` bounds the level count.
   */
  async getStringEnumerations(
    datasetId: number,
    name: string,
    cap = 30,
  ): Promise<Array<{ string: string; value: number }> | null> {
    const profile = await this.getProfile(datasetId, name);
    if (!profile) {
      return null;
    }
    const seen: string[] = [];
    for (const segment of profile.profile_segments) {
      if (segment.is_gap || segment.dynamics == null) {
        continue;
      }
      const state = typeof segment.dynamics === 'string' ? segment.dynamics : String(segment.dynamics);
      if (!seen.includes(state)) {
        seen.push(state);
        if (seen.length > cap) {
          return null;
        }
      }
    }
    return seen.length > 0 ? seen.map((string, value) => ({ string, value })) : null;
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

  /**
   * Sampled telemetry datums for a resource, cached so pan/zoom re-windows (and
   * decimates) in memory instead of re-sampling the profile on every request.
   * `datasetStartMs` is the plan start (fixed per resource).
   */
  async getResourceDatums(
    datasetId: number,
    name: string,
    datasetStartMs: number,
  ): Promise<Datum[]> {
    const key = `${datasetId}:${name}`;
    let datums = this.#datums.get(key);
    if (!datums) {
      const profile = await this.getProfile(datasetId, name);
      datums = profile ? sampleProfile(profile, datasetStartMs) : [];
      this.#datums.set(key, datums);
    }
    return datums;
  }

  /**
   * A resource's units + description, from the plan's model resource types — the
   * authoritative source (a profile's inline schema usually omits them, esp. for real
   * resources). Cached per model; `{}` if unknown.
   */
  async getResourceMeta(planId: number, name: string): Promise<{ description?: string; unit?: string }> {
    const plan = await this.getPlan(planId);
    if (!plan) {
      return {};
    }
    let pending = this.#resourceSchemas.get(plan.model_id);
    if (!pending) {
      // Cache the in-flight promise so concurrent resources share one fetch; on failure
      // (e.g. the role can't read resource_type) resolve to an empty map and keep it, so
      // it's never retried — this enrichment must not loop or break resource resolution.
      pending = this.api
        .getResourceTypes(plan.model_id)
        .then(types => new Map(types.map(type => [type.name, type.schema])))
        .catch(() => new Map<string, ValueSchema>());
      this.#resourceSchemas.set(plan.model_id, pending);
    }
    const metadata = (await pending).get(name)?.metadata;
    return { description: metadata?.description?.value, unit: metadata?.unit?.value };
  }

  /** directiveId → directive name for a plan, cached — used to label simulated activities.
   * Failure-tolerant (empty map if the role can't read activity_directive). */
  async getActivityDirectiveNames(planId: number): Promise<Map<number, string>> {
    let pending = this.#directiveNames.get(planId);
    if (!pending) {
      pending = this.api
        .getActivityDirectives(planId)
        .then(directives => new Map(directives.map(directive => [directive.id, directive.name])))
        .catch(() => new Map<number, string>());
      this.#directiveNames.set(planId, pending);
    }
    return pending;
  }

  /** Derivation groups linked to a plan (re-fetched each call so the tree picks up
   * changes on reload, like sims; failure-tolerant). The composition uses this to decide
   * whether to show an "External Events" node. */
  getPlanDerivationGroups(planId: number): Promise<string[]> {
    return this.api.getPlanDerivationGroups(planId).catch(() => []);
  }

  /** A plan's external events (derived from its linked groups), sorted by start.
   * Re-fetched each call (not cached) so reload/reopen reflects newly-synced events —
   * matching how sims refresh; failure-tolerant. */
  async getExternalEvents(planId: number): Promise<ExternalEvent[]> {
    const groups = await this.getPlanDerivationGroups(planId);
    if (groups.length === 0) {
      return [];
    }
    const events = await this.api.getDerivedEvents(groups).catch(() => []);
    return [...events].sort((a, b) => Date.parse(a.start_time) - Date.parse(b.start_time));
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
