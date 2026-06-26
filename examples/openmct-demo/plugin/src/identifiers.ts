/**
 * Object-tree key encoding. Every node in the PlanDev tree is addressed by a
 * self-describing `key` string so the object provider can resolve any node
 * (including deep-links) without external state.
 *
 *   root      plandev-root
 *   plan      plan:<planId>
 *   sim       sim:<planId>:<simId>:<datasetId>
 *   resource  res:<datasetId>:<planId>:<encodedName>
 *   plan-obj  acts:<datasetId>:<planId>                  (simulated activities → Plan/Gantt)
 *   plot      plot:<datasetId>:<planId>                  (ready-made Display Layout of resource plots)
 *   res-plot  rplot:<datasetId>:<planId>:<encodedName>   (single-resource Overlay Plot, a layout frame)
 *   actual    actual:<datasetId>:<planId>:<encodedName>  (synthesized as-flown telemetry)
 *   compare   cmp:<datasetId>:<planId>:<encodedName>     (predict-vs-actual overlay plot)
 *   cmp-dir   cmpdir:<datasetId>:<planId>                ("Predict vs Actual" folder)
 *   status    status:<encodedMessage>                    (a leaf affordance: empty / error state)
 *
 * Resource names can contain '/' and ':' (e.g. banananation's `/data/line_count`,
 * `/flag/conflicted`). Those break OpenMCT object addressing — keyStrings
 * (`namespace:key`) live inside URL paths delimited by '/', so a raw '/' in the key
 * splits the path and the object resolves as "Missing". The name segment is therefore
 * `encodeURIComponent`d (encodes both '/'→%2F and ':'→%3A) and decoded on parse, so a
 * key round-trips ANY resource name.
 */

export const ROOT_KEY = 'plandev-root';

export type ParsedKey =
  | { kind: 'root' }
  | { kind: 'plan'; planId: number }
  | { kind: 'sim'; planId: number; simId: number; datasetId: number }
  | { kind: 'resource'; datasetId: number; planId: number; name: string }
  | { kind: 'activities'; datasetId: number; planId: number }
  | { kind: 'plot'; datasetId: number; planId: number }
  | { kind: 'resourcePlot'; datasetId: number; planId: number; name: string }
  | { kind: 'actual'; datasetId: number; planId: number; name: string }
  | { kind: 'compare'; datasetId: number; planId: number; name: string }
  | { kind: 'compareDir'; datasetId: number; planId: number }
  | { kind: 'externalEvents'; planId: number }
  | { kind: 'status'; message: string }
  | { kind: 'unknown' };

export const planKey = (planId: number): string => `plan:${planId}`;

export const simKey = (planId: number, simId: number, datasetId: number): string =>
  `sim:${planId}:${simId}:${datasetId}`;

export const resourceKey = (datasetId: number, planId: number, name: string): string =>
  `res:${datasetId}:${planId}:${encodeURIComponent(name)}`;

export const activitiesKey = (datasetId: number, planId: number): string =>
  `acts:${datasetId}:${planId}`;

export const plotKey = (datasetId: number, planId: number): string =>
  `plot:${datasetId}:${planId}`;

export const resourcePlotKey = (datasetId: number, planId: number, name: string): string =>
  `rplot:${datasetId}:${planId}:${encodeURIComponent(name)}`;

export const actualKey = (datasetId: number, planId: number, name: string): string =>
  `actual:${datasetId}:${planId}:${encodeURIComponent(name)}`;

export const compareKey = (datasetId: number, planId: number, name: string): string =>
  `cmp:${datasetId}:${planId}:${encodeURIComponent(name)}`;

export const compareDirKey = (datasetId: number, planId: number): string =>
  `cmpdir:${datasetId}:${planId}`;

export const externalEventsKey = (planId: number): string => `extevents:${planId}`;

export const statusKey = (message: string): string => `status:${encodeURIComponent(message)}`;

/** Decode the (URL-encoded) resource-name tail of a key. */
function decodeName(parts: string[]): string {
  return decodeURIComponent(parts.slice(3).join(':'));
}

export function parseKey(key: string): ParsedKey {
  if (key === ROOT_KEY) {
    return { kind: 'root' };
  }
  const parts = key.split(':');
  switch (parts[0]) {
    case 'plan':
      return { kind: 'plan', planId: Number(parts[1]) };
    case 'sim':
      return {
        datasetId: Number(parts[3]),
        kind: 'sim',
        planId: Number(parts[1]),
        simId: Number(parts[2]),
      };
    case 'res':
      return {
        datasetId: Number(parts[1]),
        kind: 'resource',
        name: decodeName(parts),
        planId: Number(parts[2]),
      };
    case 'acts':
      return { datasetId: Number(parts[1]), kind: 'activities', planId: Number(parts[2]) };
    case 'plot':
      return { datasetId: Number(parts[1]), kind: 'plot', planId: Number(parts[2]) };
    case 'rplot':
      return {
        datasetId: Number(parts[1]),
        kind: 'resourcePlot',
        name: decodeName(parts),
        planId: Number(parts[2]),
      };
    case 'actual':
      return {
        datasetId: Number(parts[1]),
        kind: 'actual',
        name: decodeName(parts),
        planId: Number(parts[2]),
      };
    case 'cmp':
      return {
        datasetId: Number(parts[1]),
        kind: 'compare',
        name: decodeName(parts),
        planId: Number(parts[2]),
      };
    case 'cmpdir':
      return { datasetId: Number(parts[1]), kind: 'compareDir', planId: Number(parts[2]) };
    case 'extevents':
      return { kind: 'externalEvents', planId: Number(parts[1]) };
    case 'status':
      return { kind: 'status', message: decodeURIComponent(parts.slice(1).join(':')) };
    default:
      return { kind: 'unknown' };
  }
}
