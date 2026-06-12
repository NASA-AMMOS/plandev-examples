/**
 * Object-tree key encoding. Every node in the PlanDev tree is addressed by a
 * self-describing `key` string so the object provider can resolve any node
 * (including deep-links) without external state.
 *
 *   root      plandev-root
 *   plan      plan:<planId>
 *   sim       sim:<planId>:<simId>:<datasetId>
 *   resource  res:<datasetId>:<planId>:<resourceName>
 *   plan-obj  acts:<datasetId>:<planId>            (simulated activities → Plan/Gantt)
 *   plot      plot:<datasetId>:<planId>            (ready-made Display Layout of resource plots)
 *   res-plot  rplot:<datasetId>:<planId>:<name>    (single-resource Overlay Plot, a layout frame)
 *   actual    actual:<datasetId>:<planId>:<name>   (synthesized as-flown telemetry)
 *   compare   cmp:<datasetId>:<planId>:<name>      (predict-vs-actual overlay plot)
 *   cmp-dir   cmpdir:<datasetId>:<planId>          ("Predict vs Actual" folder)
 *
 * Resource names may contain ':' is not expected (PlanDev names use '.'/'_'),
 * but we rejoin trailing segments defensively so a stray ':' can't corrupt one.
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
  | { kind: 'unknown' };

export const planKey = (planId: number): string => `plan:${planId}`;

export const simKey = (planId: number, simId: number, datasetId: number): string =>
  `sim:${planId}:${simId}:${datasetId}`;

export const resourceKey = (datasetId: number, planId: number, name: string): string =>
  `res:${datasetId}:${planId}:${name}`;

export const activitiesKey = (datasetId: number, planId: number): string =>
  `acts:${datasetId}:${planId}`;

export const plotKey = (datasetId: number, planId: number): string =>
  `plot:${datasetId}:${planId}`;

export const resourcePlotKey = (datasetId: number, planId: number, name: string): string =>
  `rplot:${datasetId}:${planId}:${name}`;

export const actualKey = (datasetId: number, planId: number, name: string): string =>
  `actual:${datasetId}:${planId}:${name}`;

export const compareKey = (datasetId: number, planId: number, name: string): string =>
  `cmp:${datasetId}:${planId}:${name}`;

export const compareDirKey = (datasetId: number, planId: number): string =>
  `cmpdir:${datasetId}:${planId}`;

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
        name: parts.slice(3).join(':'),
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
        name: parts.slice(3).join(':'),
        planId: Number(parts[2]),
      };
    case 'actual':
      return {
        datasetId: Number(parts[1]),
        kind: 'actual',
        name: parts.slice(3).join(':'),
        planId: Number(parts[2]),
      };
    case 'cmp':
      return {
        datasetId: Number(parts[1]),
        kind: 'compare',
        name: parts.slice(3).join(':'),
        planId: Number(parts[2]),
      };
    case 'cmpdir':
      return { datasetId: Number(parts[1]), kind: 'compareDir', planId: Number(parts[2]) };
    default:
      return { kind: 'unknown' };
  }
}
