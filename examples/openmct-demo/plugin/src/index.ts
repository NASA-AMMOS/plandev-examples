/**
 * openmct-plandev — exposes a PlanDev (Aerie) deployment inside OpenMCT.
 *
 * EXPERIMENTAL DEMO — not a supported or production plugin. Built to
 * explore the integration shape; expect rough edges. See README.
 *
 * Builds a Root → Plans → Sims tree where each Sim node holds:
 *   • the simulated resources as OpenMCT telemetry (plottable), and
 *   • an "Activities" Plan object (the sim's spans) for Gantt / Time-List views,
 * so operators see the plan and predicted resources together.
 *
 * Reads PlanDev's Hasura GraphQL via a small framework-agnostic client
 * (plandev-api.ts) — the seed of the shared "AerieApi" the integration memo
 * calls Phase 0.
 *
 * Usage (in an OpenMCT host page, after installing default plugins + Plan):
 *   openmct.install(openmctPlandev({
 *     graphqlUrl: '/api/graphql',
 *     loginUrl: '/api/auth/login',
 *     username: 'openmct-demo',
 *   }));
 */
import { createCompositionProvider } from './composition-provider';
import { RESOURCE_TYPE } from './constants';
import { PluginContext } from './context';
import { ROOT_KEY } from './identifiers';
import type { OpenMCT } from './openmct';
import { createObjectProvider } from './object-provider';
import { PlandevApi } from './plandev-api';
import { createTelemetryProvider } from './telemetry-provider';

export interface OpenmctPlandevConfig {
  /** Hasura GraphQL endpoint (same-origin proxy path, or absolute URL). */
  graphqlUrl: string;
  /** Gateway login endpoint. With AUTH_TYPE=none it issues a token for any user. */
  loginUrl: string;
  /** Username to authenticate as (any value when PlanDev auth is disabled). */
  username: string;
  /** Hasura role to assume. Defaults to `aerie_admin`. */
  role?: string;
  /** OpenMCT namespace for PlanDev objects. Defaults to `plandev`. */
  namespace?: string;
  /**
   * Floor (ms) applied to zero-/short-duration activity spans so they remain
   * visible as Gantt bars at plan scale. Defaults to 0 (instantaneous events
   * render as point markers).
   */
  minActivityDurationMs?: number;
  /**
   * Per-plot frame height (px) in the ready-made "Resource Plot" Display Layout.
   * This is OpenMCT's only CSS-free way to set explicit plot height. Defaults to 240.
   */
  resourcePlotHeightPx?: number;
  /** Per-plot frame width (px) in the "Resource Plot" layout (fixed canvas). Defaults to 1000. */
  resourcePlotWidthPx?: number;
}

export default function openmctPlandev(config: OpenmctPlandevConfig) {
  const namespace = config.namespace ?? 'plandev';
  const layout = {
    minActivityDurationMs: config.minActivityDurationMs ?? 0,
    resourcePlotHeightPx: config.resourcePlotHeightPx ?? 240,
    resourcePlotWidthPx: config.resourcePlotWidthPx ?? 1000,
  };

  return function install(openmct: OpenMCT): void {
    const api = new PlandevApi({
      graphqlUrl: config.graphqlUrl,
      loginUrl: config.loginUrl,
      role: config.role,
      username: config.username,
    });
    const context = new PluginContext(api, namespace);

    openmct.types.addType(RESOURCE_TYPE, {
      cssClass: 'icon-telemetry',
      description: 'A PlanDev simulated resource profile, sampled as telemetry.',
      name: 'PlanDev Resource',
    });

    openmct.objects.addRoot({ key: ROOT_KEY, namespace });
    openmct.objects.addProvider(namespace, createObjectProvider(context, layout));
    openmct.composition.addProvider(createCompositionProvider(context));
    openmct.telemetry.addProvider(createTelemetryProvider(context));
  };
}
