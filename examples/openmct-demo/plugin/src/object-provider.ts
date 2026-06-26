/**
 * Resolves any node identifier in the PlanDev tree to an OpenMCT domain object:
 * Root → Plans → Sims → (Activities Plan object + Resource telemetry leaves).
 *
 * Every resolution is wrapped: a failed PlanDev call surfaces a visible error
 * toast and a `⚠ Failed to load` placeholder instead of a bare "Missing" node.
 * Resource leaves always carry a valid range-hinted telemetry value (even when
 * the profile type can't be loaded) so OpenMCT's Plot view can't crash on them.
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
import { isPlottable, profileTypeToValues, VALUE_KEY, type TelemetryValue } from './metadata';
import type { DomainObject, Identifier, ObjectProvider } from './openmct';
import { keyString } from './openmct';
import { buildExternalEventsPlan, buildSimulatedActivitiesPlan } from './plan-object';
import { getIntervalInMs } from './sample';
import type { Plan, ProfileType } from './types';

/** Tunables for the ready-made displays. */
export interface LayoutOptions {
  minActivityDurationMs: number;
  resourcePlotHeightPx: number;
  resourcePlotWidthPx: number;
  /** printf-style format for real resource values (OpenMCT `formatString`), e.g. `%.3f`. */
  resourceValueFormat: string;
}

/** Fallback type for a resource whose profile type couldn't be loaded — keeps the
 * telemetry metadata range-valued (a real/float series) so OpenMCT never crashes. */
const DEFAULT_PROFILE_TYPE: ProfileType = { schema: { type: 'real' }, type: 'real' };

/**
 * Telemetry `values` that ALWAYS include a range-hinted value. A missing profile
 * type would otherwise yield `{ values: [] }`, and OpenMCT's `PlotSeries` reads
 * `.unit` off the (absent) range value → `Cannot read properties of undefined`.
 * We emit default numeric metadata and report the failure so the caller can alert.
 */
function resourceValues(profileType: ProfileType | undefined): {
  failed: boolean;
  values: TelemetryValue[];
} {
  return profileType
    ? { failed: false, values: profileTypeToValues(profileType) }
    : { failed: true, values: profileTypeToValues(DEFAULT_PROFILE_TYPE) };
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

      try {
        switch (parsed.kind) {
          case 'root':
            return { identifier, location: 'ROOT', name: 'PlanDev', type: FOLDER_TYPE };

          case 'status':
            // A leaf affordance (empty / unreachable). Not expandable — the
            // composition provider doesn't claim 'status' keys.
            return {
              identifier,
              location: keyString(id(ROOT_KEY)),
              name: parsed.message,
              type: FOLDER_TYPE,
            };

          case 'plan': {
            const plan = await context.getPlan(parsed.planId);
            return {
              identifier,
              location: keyString(id(ROOT_KEY)),
              name: plan?.name ?? `Plan ${parsed.planId}`,
              // PlanDev metadata surfaced by the inspector view (Workstream F).
              plandevMeta: plan ? planMeta(parsed.planId, plan) : undefined,
              type: FOLDER_TYPE,
            };
          }

          case 'sim': {
            const sim = await context.getSimulationDataset(parsed.planId, parsed.simId);
            const plan = await context.getPlan(parsed.planId);
            const status = sim?.status ?? 'unknown';
            const startMs = plan ? Date.parse(plan.start_time) : NaN;
            const endMs = plan ? startMs + getIntervalInMs(plan.duration) : NaN;
            return {
              identifier,
              location: keyString(id(planKey(parsed.planId))),
              name: `Sim ${parsed.simId} · ${status}`,
              plandevMeta: {
                datasetId: parsed.datasetId,
                endTime: Number.isNaN(endMs) ? null : new Date(endMs).toISOString(),
                kind: 'sim',
                planId: parsed.planId,
                simEnd: sim?.simulation_end_time ?? null,
                simStart: sim?.simulation_start_time ?? null,
                startTime: plan?.start_time ?? null,
                status,
              },
              type: FOLDER_TYPE,
            };
          }

          case 'resource': {
            const profileType = await context.getProfileType(parsed.datasetId, parsed.name);
            const parentSimKey = await findSimKey(context, parsed.planId, parsed.datasetId);
            const { failed, values } = resourceValues(profileType);
            if (failed) {
              context.notifier.error(
                `PlanDev: could not load resource "${parsed.name}" — no profile type`,
              );
            } else if (!isPlottable(profileType!)) {
              // Free-form string discrete (e.g. /producer = Frank/Chiquita): its
              // states aren't in the schema, so discover them from the profile and
              // attach enumerations — OpenMCT then plots it as a stepped state line
              // instead of only showing a table.
              const enumerations = await context.getStringEnumerations(parsed.datasetId, parsed.name);
              const range = enumerations && values.find(v => v.key === VALUE_KEY);
              if (range) {
                range.format = 'enum';
                range.enumerations = enumerations;
              }
            }
            // Units + description come from the model's resource types (the profile's
            // inline schema usually omits them); apply units + a value format to the plot.
            const meta = await context.getResourceMeta(parsed.planId, parsed.name);
            enrichRange(values, meta.unit, options.resourceValueFormat);
            return {
              identifier,
              location: parentSimKey ? keyString(id(parentSimKey)) : undefined,
              name: failed ? `⚠ ${parsed.name}` : parsed.name,
              plandevMeta: {
                dataType: profileType ? profileType.type : 'unknown',
                description: meta.description ?? null,
                kind: 'resource',
                name: parsed.name,
                unit: meta.unit ?? null,
              },
              telemetry: { values },
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
            const names = await context.getPlottableResourceNames(parsed.datasetId, 15);
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
              name:
                composition.length > 0
                  ? `Resource Plot (first ${composition.length})`
                  : 'Resource Plot (no plottable resources)',
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
            const { failed, values } = resourceValues(profileType);
            if (failed) {
              context.notifier.error(
                `PlanDev: could not load actual "${parsed.name}" — no profile type`,
              );
            }
            const meta = await context.getResourceMeta(parsed.planId, parsed.name);
            enrichRange(values, meta.unit, options.resourceValueFormat);
            return {
              identifier,
              location: keyString(id(compareDirKey(parsed.datasetId, parsed.planId))),
              name: failed ? `⚠ ${parsed.name} (actual)` : `${parsed.name} (actual)`,
              telemetry: { values },
              type: RESOURCE_TYPE,
            };
          }

          case 'activities': {
            const startMs = await context.getPlanStartMs(parsed.planId);
            const plan = await context.getPlan(parsed.planId);
            const planEndMs = plan
              ? Date.parse(plan.start_time) + getIntervalInMs(plan.duration)
              : NaN;
            const directiveNames = await context.getActivityDirectiveNames(parsed.planId);
            const body = await buildSimulatedActivitiesPlan(
              context.api,
              parsed.datasetId,
              startMs,
              options.minActivityDurationMs,
              {
                planEndTime: Number.isNaN(planEndMs) ? null : new Date(planEndMs).toISOString(),
                planId: parsed.planId,
                planStartTime: plan?.start_time ?? null,
                simulationDatasetId: parsed.datasetId,
              },
              directiveNames,
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

          case 'externalEvents': {
            // A plan's external events (DSN contacts, view periods, …) as a Gantt,
            // grouped by event type — alongside the plan's activities + resources.
            const events = await context.getExternalEvents(parsed.planId);
            const body = buildExternalEventsPlan(events, options.minActivityDurationMs);
            const swimlaneVisibility: Record<string, boolean> = {};
            for (const eventType of Object.keys(body)) {
              swimlaneVisibility[eventType] = true;
            }
            return {
              configuration: { clipActivityNames: false, swimlaneVisibility },
              identifier,
              location: keyString(id(planKey(parsed.planId))),
              name: 'External Events',
              selectFile: { body, name: 'external-events.json' },
              type: PLAN_TYPE,
            };
          }

          default:
            throw new Error(`PlanDev object provider: unknown key "${identifier.key}"`);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        context.notifier.error(`PlanDev: ${message}`);
        // A thrown get() becomes a bare "Missing" node; return a named placeholder
        // so the failure is legible in the tree.
        return { identifier, name: '⚠ Failed to load', type: FOLDER_TYPE };
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

/** Apply units (from the model's resource types) + a value format to a resource's range
 * value. Units only fill in if absent; the printf format only applies to real (float). */
function enrichRange(values: TelemetryValue[], unit: string | undefined, valueFormat: string): void {
  const range = values.find(value => value.key === VALUE_KEY);
  if (!range) {
    return;
  }
  if (range.format === 'float' && valueFormat) {
    range.formatString = valueFormat;
  }
  if (unit) {
    range.unit = unit; // series / legend / hover read the singular `unit`
    range.units = unit; // Y-axis fallback reads the plural `units`
    // OpenMCT's Y-axis label uses the value `name` first (units only as a fallback when
    // there's no name), so fold the unit into the name to surface it on the axis too.
    range.name = `${range.name} (${unit})`;
  }
}

/** PlanDev metadata for the inspector view (Workstream F). `endTime` is derived
 * from `start_time` + `duration`; `tags` are flattened to names. */
function planMeta(planId: number, plan: Plan): Record<string, unknown> {
  const startMs = Date.parse(plan.start_time);
  const endMs = startMs + getIntervalInMs(plan.duration);
  return {
    createdAt: plan.created_at,
    duration: plan.duration,
    endTime: Number.isNaN(endMs) ? null : new Date(endMs).toISOString(),
    kind: 'plan',
    model: plan.model ? `${plan.model.name} (v${plan.model.version})` : null,
    owner: plan.owner ?? null,
    planId,
    startTime: plan.start_time,
    tags: (plan.tags ?? []).map(t => t.tag?.name).filter(Boolean),
    updatedAt: plan.updated_at,
  };
}
