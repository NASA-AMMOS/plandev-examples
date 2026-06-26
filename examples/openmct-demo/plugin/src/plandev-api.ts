/**
 * Minimal, framework-agnostic typed client over PlanDev's (Aerie's) Hasura GraphQL
 * API. No Svelte / OpenMCT imports — just `fetch`.
 *
 * **Auth-agnostic:** the plugin sends no credentials. It POSTs queries to the
 * configured endpoint and relies on the deployment's proxy to attach auth (a bearer
 * token + `x-hasura-role`). The bundled `host/server.mjs` does this server-side with a
 * service account and a pinned role, so the browser never holds a token or picks a
 * role. (See the README's Authentication section.)
 *
 * Intentionally self-contained — this plugin owns its ~6 read queries and their result
 * types (./types) rather than depending on @plandev/api. That shared client re-exports
 * plandev-ui's query selections + result types, so coupling this thin read-only consumer
 * to it would let routine UI query changes break the plugin. @plandev/api is the right
 * call for broad / write-heavy consumers (the e2e harness, the extension SDK), not a
 * 6-query browser plugin. See plandev-openmct-integration.md for the rationale.
 */
import type {
  ActivityDirective,
  ExternalEvent,
  Plan,
  Profile,
  ProfileDescriptor,
  ResourceType,
  SimulationDataset,
  Span,
} from './types';

export interface PlandevApiConfig {
  /** Hasura GraphQL endpoint (a same-origin proxy path that attaches auth, or absolute). */
  graphqlUrl: string;
  /** Per-request timeout (ms) before aborting a fetch. Defaults to 30000. */
  requestTimeoutMs?: number;
}

interface GraphQLResponse<T> {
  data?: T;
  errors?: Array<{ message: string }>;
}

/**
 * Caps how many GraphQL requests are in flight at once. OpenMCT can ask for
 * hundreds of telemetry items simultaneously (e.g. a folder grid previews every
 * child); without a cap the browser floods its connection pool and fails with
 * net::ERR_INSUFFICIENT_RESOURCES. Excess requests queue and run as slots free.
 */
const MAX_CONCURRENT_REQUESTS = 6;

export class PlandevApi {
  readonly #config: Required<PlandevApiConfig>;

  #active = 0;
  readonly #waiters: Array<() => void> = [];

  constructor(config: PlandevApiConfig) {
    this.#config = {
      graphqlUrl: config.graphqlUrl,
      requestTimeoutMs: config.requestTimeoutMs ?? 30_000,
    };
  }

  /** fetch() bounded by an AbortController timeout; a timeout becomes a clear error. */
  async #fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.#config.requestTimeoutMs);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error(
          `PlanDev request timed out after ${this.#config.requestTimeoutMs}ms (${url})`,
        );
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async #acquireSlot(): Promise<void> {
    if (this.#active >= MAX_CONCURRENT_REQUESTS) {
      await new Promise<void>(resolve => this.#waiters.push(resolve));
    }
    this.#active++;
  }

  #releaseSlot(): void {
    this.#active--;
    this.#waiters.shift()?.();
  }

  /** Runs a GraphQL operation. Sends no credentials — the proxy attaches them. */
  async gql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
    await this.#acquireSlot();
    try {
      const response = await this.#fetchWithTimeout(this.#config.graphqlUrl, {
        body: JSON.stringify({ query, variables }),
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
      });
      return await this.#handleResponse<T>(response);
    } finally {
      this.#releaseSlot();
    }
  }

  async #handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      // Surface the upstream/proxy error body (host/server.mjs returns a 502 JSON
      // with the real reason — e.g. an auth failure at the proxy) instead of a code.
      const body = await response.text().catch(() => '');
      throw new Error(
        `PlanDev GraphQL request failed (${response.status})${body ? `: ${body}` : ''}`,
      );
    }
    const json = (await response.json()) as GraphQLResponse<T>;
    if (json.errors?.length) {
      throw new Error(`PlanDev GraphQL error: ${json.errors.map(e => e.message).join('; ')}`);
    }
    if (json.data === undefined) {
      throw new Error('PlanDev GraphQL response had no data');
    }
    return json.data;
  }

  // ---- typed queries ------------------------------------------------------

  async getPlans(): Promise<Plan[]> {
    const data = await this.gql<{ plan: Plan[] }>(`
      query OpenMctGetPlans {
        plan(order_by: { id: desc }) {
          id
          name
          model_id
          start_time
          duration
          owner
          created_at
          updated_at
          model: mission_model {
            name
            version
          }
          tags {
            tag {
              name
              color
            }
          }
        }
      }
    `);
    return data.plan;
  }

  async getPlan(planId: number): Promise<Plan | null> {
    const data = await this.gql<{ plan: Plan[] }>(
      `
      query OpenMctGetPlan($id: Int!) {
        plan(where: { id: { _eq: $id } }, limit: 1) {
          id
          name
          model_id
          start_time
          duration
          owner
          created_at
          updated_at
          model: mission_model {
            name
            version
          }
          tags {
            tag {
              name
              color
            }
          }
        }
      }
    `,
      { id: planId },
    );
    return data.plan[0] ?? null;
  }

  async getSimulationDatasets(planId: number): Promise<SimulationDataset[]> {
    const data = await this.gql<{
      simulation: Array<{ simulation_datasets: SimulationDataset[] }>;
    }>(
      `
      query OpenMctGetSimulationDatasets($planId: Int!) {
        simulation(where: { plan_id: { _eq: $planId } }, order_by: { id: desc }) {
          simulation_datasets(order_by: { id: desc }) {
            id
            dataset_id
            status
            simulation_start_time
            simulation_end_time
          }
        }
      }
    `,
      { planId },
    );
    return data.simulation.flatMap(sim => sim.simulation_datasets);
  }

  /** Lists the profiles in a dataset with their type/schema, but without segments. */
  async getProfileDescriptors(datasetId: number): Promise<ProfileDescriptor[]> {
    const data = await this.gql<{ profile: ProfileDescriptor[] }>(
      `
      query OpenMctGetProfileDescriptors($datasetId: Int!) {
        profile(where: { dataset_id: { _eq: $datasetId } }, order_by: { name: asc }) {
          name
          type
        }
      }
    `,
      { datasetId },
    );
    return data.profile;
  }

  /** Fetches a single profile (with segments) — mirrors plandev-ui's GET_PROFILE. */
  async getProfile(datasetId: number, name: string): Promise<Profile | null> {
    const data = await this.gql<{ profile: Profile[] }>(
      `
      query OpenMctGetProfile($datasetId: Int!, $name: String!) {
        profile(where: { dataset_id: { _eq: $datasetId }, name: { _eq: $name } }, limit: 1) {
          name
          duration
          type
          profile_segments(order_by: { start_offset: asc }) {
            start_offset
            dynamics
            is_gap
          }
        }
      }
    `,
      { datasetId, name },
    );
    return data.profile[0] ?? null;
  }

  /** Fetches simulated activity spans for a dataset — mirrors plandev-ui's GET_SPANS. */
  async getSpans(datasetId: number): Promise<Span[]> {
    const data = await this.gql<{ span: Span[] }>(
      `
      query OpenMctGetSpans($datasetId: Int!) {
        span(where: { dataset_id: { _eq: $datasetId } }, order_by: { start_offset: asc }) {
          span_id
          parent_id
          type
          start_offset
          duration
          attributes
        }
      }
    `,
      { datasetId },
    );
    return data.span;
  }

  /** Resource types for a model — the source of resource units/descriptions (the
   * profile's inline schema often omits them). */
  async getResourceTypes(modelId: number): Promise<ResourceType[]> {
    const data = await this.gql<{ resource_type: ResourceType[] }>(
      `
      query OpenMctGetResourceTypes($modelId: Int!) {
        resource_type(where: { model_id: { _eq: $modelId } }, order_by: { name: asc }) {
          name
          schema
        }
      }
    `,
      { modelId },
    );
    return data.resource_type;
  }

  /** Planned activity directives for a plan — names label the simulated Gantt bars. */
  async getActivityDirectives(planId: number): Promise<ActivityDirective[]> {
    const data = await this.gql<{ activity_directive: ActivityDirective[] }>(
      `
      query OpenMctGetActivityDirectives($planId: Int!) {
        activity_directive(where: { plan_id: { _eq: $planId } }) {
          id
          name
          type
        }
      }
    `,
      { planId },
    );
    return data.activity_directive;
  }

  /** Derivation groups linked to a plan (external events derive from these). */
  async getPlanDerivationGroups(planId: number): Promise<string[]> {
    const data = await this.gql<{ plan_derivation_group: Array<{ derivation_group_name: string }> }>(
      `
      query OpenMctGetPlanDerivationGroups($planId: Int!) {
        plan_derivation_group(where: { plan_id: { _eq: $planId } }) {
          derivation_group_name
        }
      }
    `,
      { planId },
    );
    return data.plan_derivation_group.map(group => group.derivation_group_name);
  }

  /** External events derived for the given derivation groups (a plan's external events). */
  async getDerivedEvents(derivationGroupNames: string[]): Promise<ExternalEvent[]> {
    if (derivationGroupNames.length === 0) {
      return [];
    }
    const data = await this.gql<{ derived_events: Array<{ external_event: ExternalEvent }> }>(
      `
      query OpenMctGetDerivedEvents($names: [String!]!) {
        derived_events(where: { derivation_group_name: { _in: $names } }) {
          external_event {
            key
            event_type_name
            start_time
            duration
            derivation_group_name
            source_key
            attributes
          }
        }
      }
    `,
      { names: derivationGroupNames },
    );
    return data.derived_events.map(row => row.external_event);
  }
}
