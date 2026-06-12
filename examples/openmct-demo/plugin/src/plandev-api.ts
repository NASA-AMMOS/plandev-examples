/**
 * Minimal, framework-agnostic typed client over PlanDev's (Aerie's) Hasura
 * GraphQL API + gateway auth. No Svelte / OpenMCT imports — just `fetch`.
 *
 * This is the seed of the "AerieApi" the integration memo calls Phase 0: when
 * that shared client is packaged as @plandev/api, this file's query methods
 * move there and the plugin imports them instead of re-declaring the GraphQL.
 */
import type { Plan, Profile, ProfileDescriptor, SimulationDataset, Span } from './types';

export interface PlandevApiConfig {
  /** Hasura GraphQL endpoint (proxied same-origin by the host, or absolute). */
  graphqlUrl: string;
  /** Gateway login endpoint. With AUTH_TYPE=none it returns a token for any user. */
  loginUrl: string;
  /** Username to log in as (any value when auth is disabled). */
  username: string;
  /** Hasura role to assume. Defaults to `aerie_admin`. */
  role?: string;
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
  #token: string | null = null;
  #loginPromise: Promise<string> | null = null;

  #active = 0;
  readonly #waiters: Array<() => void> = [];

  constructor(config: PlandevApiConfig) {
    this.#config = { role: 'aerie_admin', ...config };
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

  /** Logs in via the gateway (once) and caches the JWT. */
  async #login(): Promise<string> {
    if (this.#token) {
      return this.#token;
    }
    if (!this.#loginPromise) {
      this.#loginPromise = (async () => {
        const response = await fetch(this.#config.loginUrl, {
          body: JSON.stringify({ password: '', username: this.#config.username }),
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
        });
        if (!response.ok) {
          throw new Error(`PlanDev login failed (${response.status}) at ${this.#config.loginUrl}`);
        }
        const json = (await response.json()) as { token?: string; ssoToken?: string };
        const token = json.token ?? json.ssoToken;
        if (!token) {
          throw new Error('PlanDev login returned no token');
        }
        this.#token = token;
        return token;
      })();
      this.#loginPromise.catch(() => {
        // Allow a retry on the next call if login rejected.
        this.#loginPromise = null;
      });
    }
    return this.#loginPromise;
  }

  /** Runs a GraphQL operation, transparently (re)authenticating on a 401. */
  async gql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
    const send = async (token: string) =>
      fetch(this.#config.graphqlUrl, {
        body: JSON.stringify({ query, variables }),
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'x-hasura-role': this.#config.role,
        },
        method: 'POST',
      });

    await this.#acquireSlot();
    try {
      let token = await this.#login();
      let response = await send(token);
      if (response.status === 401) {
        // Token likely expired — drop it and retry once.
        this.#token = null;
        this.#loginPromise = null;
        token = await this.#login();
        response = await send(token);
      }
      if (!response.ok) {
        throw new Error(`PlanDev GraphQL request failed (${response.status})`);
      }
      const json = (await response.json()) as GraphQLResponse<T>;
      if (json.errors?.length) {
        throw new Error(`PlanDev GraphQL error: ${json.errors.map(e => e.message).join('; ')}`);
      }
      if (json.data === undefined) {
        throw new Error('PlanDev GraphQL response had no data');
      }
      return json.data;
    } finally {
      this.#releaseSlot();
    }
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
}
