/**
 * Builds an OpenMCT Plan-object body from a simulation's activity spans.
 *
 * The Plan plugin's default (no `sourceMap`) shape is a map of
 * group-name → activity[], where each activity is `{ name, start, end, type }`
 * with epoch-ms times (see nasa/openmct src/plugins/plan/README.md). We group
 * spans by their activity type, so each type becomes a Gantt/Time-List swimlane.
 *
 * Each activity also carries PlanDev enrichment (span id, arguments, computed
 * attributes, and deep-link context). OpenMCT passes the whole activity object
 * through in the selection context (`context.activity`), so our activity inspector
 * view can surface those and build an "Open in PlanDev" link to the exact span.
 */
import { getIntervalInMs } from './sample';
import type { PlandevApi } from './plandev-api';
import type { ExternalEvent } from './types';

export interface PlanActivity {
  name: string;
  start: number;
  end: number;
  type: string;
  /** OpenMCT uses `id` as the activity key; we use the span id. */
  id?: number;
  // --- simulated-activity enrichment (rides in `context.activity` for the inspector) ---
  spanId?: number;
  directiveId?: number;
  arguments?: Record<string, unknown>;
  computedAttributes?: Record<string, unknown>;
  // --- deep-link context for "Open in PlanDev" ---
  planId?: number;
  simulationDatasetId?: number;
  planStartTime?: string | null;
  planEndTime?: string | null;
  // --- external-event enrichment (the inspector branches on `isExternalEvent`) ---
  isExternalEvent?: boolean;
  eventKey?: string;
  sourceKey?: string;
  derivationGroup?: string;
  eventAttributes?: unknown;
}

export type PlanBody = Record<string, PlanActivity[]>;

/** Link/identity context threaded onto every activity so the inspector can deep-link. */
export interface PlanActivityMeta {
  planId: number;
  simulationDatasetId: number;
  planStartTime: string | null;
  planEndTime: string | null;
}

/** A span's `attributes` JSONB — args the activity ran with + sim-computed outputs. */
interface SpanAttributes {
  arguments?: Record<string, unknown>;
  computedAttributes?: Record<string, unknown>;
  directiveId?: number;
}

/**
 * @param minDurationMs floor applied to zero-/short-duration spans so they stay
 *   visible as bars at plan scale. 0 keeps instantaneous events as point markers.
 * @param meta plan/sim identity threaded onto each activity for deep-linking.
 */
export async function buildSimulatedActivitiesPlan(
  api: PlandevApi,
  datasetId: number,
  datasetStartMs: number,
  minDurationMs = 0,
  meta?: PlanActivityMeta,
  directiveNames?: Map<number, string>,
): Promise<PlanBody> {
  const spans = await api.getSpans(datasetId);
  const body: PlanBody = {};

  for (const span of spans) {
    const start = datasetStartMs + getIntervalInMs(span.start_offset);
    const end = start + Math.max(getIntervalInMs(span.duration), minDurationMs);
    const attributes = (span.attributes ?? {}) as SpanAttributes;
    // Label by the directive's user-given name when resolvable; else the activity type.
    const directiveName =
      attributes.directiveId != null ? directiveNames?.get(attributes.directiveId) : undefined;
    const group = (body[span.type] ??= []); // swimlane per activity type
    group.push({
      arguments: attributes.arguments,
      computedAttributes: attributes.computedAttributes,
      directiveId: attributes.directiveId,
      end,
      id: span.span_id,
      name: directiveName ?? span.type,
      planEndTime: meta?.planEndTime,
      planId: meta?.planId,
      planStartTime: meta?.planStartTime,
      simulationDatasetId: meta?.simulationDatasetId,
      spanId: span.span_id,
      start,
      type: span.type,
    });
  }

  return body;
}

/**
 * Builds a Plan body from a plan's external events (absolute-time), grouped by event
 * type into swimlanes — so DSN contacts, view periods, etc. render as a Gantt alongside
 * the plan's activities + resources. Each activity carries the event's identity for the
 * inspector (which branches on `isExternalEvent`).
 */
export function buildExternalEventsPlan(events: ExternalEvent[], minDurationMs = 0): PlanBody {
  const body: PlanBody = {};
  for (const event of events) {
    const start = Date.parse(event.start_time);
    if (Number.isNaN(start)) {
      continue;
    }
    const end = start + Math.max(getIntervalInMs(event.duration), minDurationMs);
    const group = (body[event.event_type_name] ??= []); // swimlane per event type
    group.push({
      derivationGroup: event.derivation_group_name,
      end,
      eventAttributes: event.attributes,
      eventKey: event.key,
      isExternalEvent: true,
      name: event.key,
      sourceKey: event.source_key,
      start,
      type: event.event_type_name,
    });
  }
  return body;
}
