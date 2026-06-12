/**
 * Resolves any node identifier in the PlanDev tree to an OpenMCT domain object:
 * Root → Plans → Sims → (Activities Plan object + Resource telemetry leaves).
 */
import {
  FOLDER_TYPE,
  LAYOUT_TYPE,
  OVERLAY_PLOT_TYPE,
  PLAN_TYPE,
  RESOURCE_TYPE,
} from './constants';
import type { PluginContext } from './context';
import {
  ROOT_KEY,
  actualKey,
  compareDirKey,
  parseKey,
  planKey,
  plotKey,
  resourceKey,
  resourcePlotKey,
  simKey,
} from './identifiers';
import { profileTypeToValues } from './metadata';
import type { DomainObject, Identifier, ObjectProvider } from './openmct';
import { keyString } from './openmct';
import { buildSimulatedActivitiesPlan } from './plan-object';

/** Tunables for the ready-made displays. */
export interface LayoutOptions {
  minActivityDurationMs: number;
  resourcePlotHeightPx: number;
  resourcePlotWidthPx: number;
}

export function createObjectProvider(
  context: PluginContext,
  options: LayoutOptions,
): ObjectProvider {
  const ns = context.namespace;
  const id = (key: string): Identifier => ({ key, namespace: ns });

  return {
    async get(identifier: Identifier): Promise<DomainObject> {
      const parsed = parseKey(identifier.key);

      switch (parsed.kind) {
        case 'root':
          return { identifier, location: 'ROOT', name: 'PlanDev', type: FOLDER_TYPE };

        case 'plan': {
          const plan = await context.getPlan(parsed.planId);
          return {
            identifier,
            location: keyString(id(ROOT_KEY)),
            name: plan?.name ?? `Plan ${parsed.planId}`,
            type: FOLDER_TYPE,
          };
        }

        case 'sim': {
          const sim = await context.getSimulationDataset(parsed.planId, parsed.simId);
          const status = sim?.status ?? 'unknown';
          return {
            identifier,
            location: keyString(id(planKey(parsed.planId))),
            name: `Sim ${parsed.simId} · ${status}`,
            type: FOLDER_TYPE,
          };
        }

        case 'resource': {
          const profileType = await context.getProfileType(parsed.datasetId, parsed.name);
          const parentSimKey = await findSimKey(context, parsed.planId, parsed.datasetId);
          return {
            identifier,
            location: parentSimKey ? keyString(id(parentSimKey)) : undefined,
            name: parsed.name,
            telemetry: profileType ? { values: profileTypeToValues(profileType) } : { values: [] },
            type: RESOURCE_TYPE,
          };
        }

        case 'plot': {
          // A ready-made Display Layout: one single-resource plot frame per
          // numeric resource, stacked vertically at a configurable height — the
          // CSS-free way to give each plot an explicit height. View-only: the
          // pre-populated `configuration.items` (one per composition member)
          // means the layout tracks them on init and never mutates on view.
          // layoutGrid [1,1] makes item x/y/width/height direct pixels.
          const names = await context.getNumericResourceNames(parsed.datasetId, 15);
          const { resourcePlotHeightPx: h, resourcePlotWidthPx: w } = options;
          const composition = names.map(name =>
            id(resourcePlotKey(parsed.datasetId, parsed.planId, name)),
          );
          const items = composition.map((childId, i) => ({
            type: 'subobject-view',
            id: `rplot-${i}`,
            identifier: childId,
            hasFrame: true,
            x: 0,
            y: i * h,
            width: w,
            height: h,
            fontSize: 'default',
            font: 'default',
          }));
          const parentSimKey = await findSimKey(context, parsed.planId, parsed.datasetId);
          return {
            composition,
            configuration: { items, layoutGrid: [1, 1] },
            identifier,
            location: parentSimKey ? keyString(id(parentSimKey)) : undefined,
            name: `Resource Plot (first ${composition.length})`,
            type: LAYOUT_TYPE,
          };
        }

        case 'resourcePlot': {
          // A single-series Overlay Plot wrapping one resource, used as a layout
          // frame. Pre-populated series → no mutate on view.
          const resourceId = id(resourceKey(parsed.datasetId, parsed.planId, parsed.name));
          return {
            composition: [resourceId],
            configuration: { series: [{ identifier: resourceId }], xAxis: {}, yAxis: {} },
            identifier,
            location: keyString(id(plotKey(parsed.datasetId, parsed.planId))),
            name: parsed.name,
            type: OVERLAY_PLOT_TYPE,
          };
        }

        case 'compareDir': {
          const parentSimKey = await findSimKey(context, parsed.planId, parsed.datasetId);
          return {
            identifier,
            location: parentSimKey ? keyString(id(parentSimKey)) : undefined,
            name: 'Predict vs Actual',
            type: FOLDER_TYPE,
          };
        }

        case 'compare': {
          // Close-the-U: an Overlay Plot of one resource's predicted profile and
          // its synthesized actual on shared axes. Pre-populate configuration.series
          // (with BOTH identifiers) so the immutable plot object never mutates on view.
          const predictId = id(resourceKey(parsed.datasetId, parsed.planId, parsed.name));
          const actualId = id(actualKey(parsed.datasetId, parsed.planId, parsed.name));
          return {
            composition: [predictId, actualId],
            configuration: {
              series: [{ identifier: predictId }, { identifier: actualId }],
              xAxis: {},
              yAxis: {},
            },
            identifier,
            location: keyString(id(compareDirKey(parsed.datasetId, parsed.planId))),
            name: `${parsed.name}: predict vs actual`,
            type: OVERLAY_PLOT_TYPE,
          };
        }

        case 'actual': {
          const profileType = await context.getProfileType(parsed.datasetId, parsed.name);
          return {
            identifier,
            location: keyString(id(compareDirKey(parsed.datasetId, parsed.planId))),
            name: `${parsed.name} (actual)`,
            telemetry: profileType ? { values: profileTypeToValues(profileType) } : { values: [] },
            type: RESOURCE_TYPE,
          };
        }

        case 'activities': {
          const startMs = await context.getPlanStartMs(parsed.planId);
          const body = await buildSimulatedActivitiesPlan(
            context.api,
            parsed.datasetId,
            startMs,
            options.minActivityDurationMs,
          );
          const parentSimKey = await findSimKey(context, parsed.planId, parsed.datasetId);
          // The Plan view stores per-swimlane visibility in `configuration` and
          // tries to mutate the object to initialize it. Provider-supplied
          // objects are immutable, so we MUST pre-populate visibility for every
          // group — otherwise the mutation throws and the Gantt renders empty.
          const swimlaneVisibility: Record<string, boolean> = {};
          for (const group of Object.keys(body)) {
            swimlaneVisibility[group] = true;
          }
          return {
            configuration: { clipActivityNames: false, swimlaneVisibility },
            identifier,
            location: parentSimKey ? keyString(id(parentSimKey)) : undefined,
            name: 'Activities (simulated)',
            selectFile: { body, name: 'activities.json' },
            type: PLAN_TYPE,
          };
        }

        default:
          throw new Error(`PlanDev object provider: unknown key "${identifier.key}"`);
      }
    },
  };
}

/** Recovers the sim node key (which carries simId) from plan + dataset ids. */
async function findSimKey(
  context: PluginContext,
  planId: number,
  datasetId: number,
): Promise<string | undefined> {
  const sim = await context.findSimByDataset(planId, datasetId);
  return sim ? simKey(planId, sim.id, datasetId) : undefined;
}
