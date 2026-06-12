/**
 * Builds an OpenMCT Plan-object body from a simulation's activity spans.
 *
 * The Plan plugin's default (no `sourceMap`) shape is a map of
 * group-name → activity[], where each activity is `{ name, start, end, type }`
 * with epoch-ms times (see nasa/openmct src/plugins/plan/README.md). We group
 * spans by their activity type, so each type becomes a Gantt/Time-List swimlane.
 */
import { getIntervalInMs } from './sample';
import type { PlandevApi } from './plandev-api';

export interface PlanActivity {
  name: string;
  start: number;
  end: number;
  type: string;
}

export type PlanBody = Record<string, PlanActivity[]>;

/**
 * @param minDurationMs floor applied to zero-/short-duration spans so they stay
 *   visible as bars at plan scale. 0 keeps instantaneous events as point markers.
 */
export async function buildSimulatedActivitiesPlan(
  api: PlandevApi,
  datasetId: number,
  datasetStartMs: number,
  minDurationMs = 0,
): Promise<PlanBody> {
  const spans = await api.getSpans(datasetId);
  const body: PlanBody = {};

  for (const span of spans) {
    const start = datasetStartMs + getIntervalInMs(span.start_offset);
    const end = start + Math.max(getIntervalInMs(span.duration), minDurationMs);
    const group = (body[span.type] ??= []);
    group.push({ end, name: span.type, start, type: span.type });
  }

  return body;
}
