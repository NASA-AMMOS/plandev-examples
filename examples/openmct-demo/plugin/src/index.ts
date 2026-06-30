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
 *   openmct.install(openmctPlandev({ graphqlUrl: '/api/graphql' }));
 * (The plugin sends no credentials — front `graphqlUrl` with a proxy that attaches
 *  auth; `host/server.mjs` is a reference.)
 */
import { createCompositionProvider } from './composition-provider';
import { registerConductorAction } from './conductor-action';
import { RESOURCE_TYPE } from './constants';
import { PluginContext } from './context';
import { ROOT_KEY } from './identifiers';
import { createPlandevActivityInspectorView, createPlandevInspectorView } from './inspector-view';
import type { Notifier, OpenMCT } from './openmct';
import { createObjectProvider } from './object-provider';
import { PlandevApi } from './plandev-api';
import { createTelemetryProvider } from './telemetry-provider';

export interface OpenmctPlandevConfig {
  /**
   * Hasura GraphQL endpoint (same-origin proxy path, or absolute URL). The plugin sends
   * no credentials — front this endpoint with a proxy that attaches auth (the bundled
   * `host/server.mjs` does this server-side with a service account + pinned role).
   */
  graphqlUrl: string;
  /**
   * Liveness endpoint for the status-bar connectivity light (Hasura's `/healthz`, or a
   * same-origin proxy path to it). When set, the plugin self-installs a `URLIndicator`
   * so the light travels with it in any host. Omit to skip the light.
   */
  healthUrl?: string;
  /** OpenMCT namespace for PlanDev objects. Defaults to `plandev`. */
  namespace?: string;
  /** Base URL of the PlanDev (Aerie) UI for "Open in PlanDev" backlinks in the
   * inspector (e.g. `http://localhost:3000`). Omit to hide the link. */
  planDevUiUrl?: string;
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
  /**
   * printf-style format for real resource values (OpenMCT `formatString`), e.g. `%.3f`.
   * Defaults to `%.3f`. Note: a fixed-decimal format can clip very small magnitudes —
   * tune (or set `''` to disable) for your data.
   */
  resourceValueFormat?: string;
}

export default function openmctPlandev(config: OpenmctPlandevConfig) {
  if (!config || !config.graphqlUrl) {
    throw new Error('openmct-plandev: missing required config — graphqlUrl is required.');
  }
  const namespace = config.namespace ?? 'plandev';
  const layout = {
    minActivityDurationMs: config.minActivityDurationMs ?? 0,
    resourcePlotHeightPx: config.resourcePlotHeightPx ?? 240,
    resourcePlotWidthPx: config.resourcePlotWidthPx ?? 1000,
    resourceValueFormat: config.resourceValueFormat ?? '%.3f',
  };

  return function install(openmct: OpenMCT): void {
    const notifier = createNotifier(openmct);
    const api = new PlandevApi({ graphqlUrl: config.graphqlUrl });
    const context = new PluginContext(api, namespace, notifier);

    openmct.types.addType(RESOURCE_TYPE, {
      cssClass: 'icon-telemetry',
      description: 'A PlanDev simulated resource profile, sampled as telemetry.',
      name: 'PlanDev Resource',
    });

    const compositionProvider = createCompositionProvider(context);
    openmct.objects.addRoot({ key: ROOT_KEY, namespace });
    openmct.objects.addProvider(namespace, createObjectProvider(context, layout));
    openmct.composition.addProvider(compositionProvider);
    openmct.telemetry.addProvider(createTelemetryProvider(context));
    openmct.inspectorViews.addProvider(
      createPlandevInspectorView(namespace, config.planDevUiUrl ?? ''),
    );
    openmct.inspectorViews.addProvider(
      createPlandevActivityInspectorView(config.planDevUiUrl ?? ''),
    );

    // A context-menu action to snap the conductor to a plan/sim span — PlanDev data is
    // historical, so this is how a planner lands on the data in a host whose default
    // clock is realtime or set elsewhere (the demo host pre-sets it; others may not).
    registerConductorAction(openmct, namespace);

    // Ambient connectivity light in the status bar (green = reachable / yellow = offline),
    // self-installed so it travels with the plugin instead of relying on the host. Polls
    // the configured health endpoint; complements the per-action error toasts + tree
    // status node. Guarded: skipped if the host's openmct lacks the bundled URLIndicator.
    if (config.healthUrl && typeof openmct.plugins?.URLIndicator === 'function') {
      openmct.install(
        openmct.plugins.URLIndicator({
          iconClass: 'icon-database',
          interval: 15_000,
          label: 'PlanDev',
          url: config.healthUrl,
        }),
      );
    }

    // OpenMCT's Reload action only reloads the open object view, never the browse
    // tree. So on reload of a PlanDev node we drop caches (fresh fetch) AND refresh
    // the dynamic composition provider, which re-pulls children and emits add/remove
    // diffs — updating the tree in place.
    openmct.objectViews.on('reload', domainObject => {
      if (domainObject?.identifier?.namespace === namespace) {
        context.invalidate();
        void compositionProvider.refresh(domainObject);
      }
    });
  };
}

/**
 * Wraps OpenMCT's error notifications with a short dedupe window, so a burst of
 * identical failures (e.g. a folder whose resources all hit a downed backend)
 * surfaces one toast instead of dozens.
 */
function createNotifier(openmct: OpenMCT): Notifier {
  const lastShownMs = new Map<string, number>();
  const WINDOW_MS = 5_000;
  return {
    error(message: string): void {
      const now = Date.now();
      const prev = lastShownMs.get(message);
      if (prev !== undefined && now - prev < WINDOW_MS) {
        return;
      }
      lastShownMs.set(message, now);
      openmct.notifications.error(message);
    },
  };
}
