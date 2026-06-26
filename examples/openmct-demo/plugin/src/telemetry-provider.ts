/**
 * Historical telemetry provider for PlanDev resource leaves. On request it gets the
 * resource's sampled datums (sample.ts, cached via context.getResourceDatums), windows
 * them to the requested bounds, and honors the 'latest' strategy.
 *
 * Demo scope: completed sims, historical only — no realtime subscription. For a plot
 * request (`strategy: 'minmax'`, `size` ≈ pixel width) on a continuous (real) profile we
 * min/max-decimate to ~`size` points, so thousands of segments stay responsive while
 * spikes survive. Discrete/state series (step values) and non-plot strategies (tables,
 * LAD/meters) keep full data, so they stay exact. Decimation is in-memory on the cached
 * datums, so pan/zoom never refetches.
 */
import { actualizeDatums } from './actuals';
import { RESOURCE_TYPE } from './constants';
import type { PluginContext } from './context';
import { parseKey } from './identifiers';
import type { DomainObject, RequestOptions, TelemetryProvider } from './openmct';
import { type Datum, minMaxDecimate } from './sample';

export function createTelemetryProvider(context: PluginContext): TelemetryProvider {
  return {
    supportsRequest(domainObject: DomainObject): boolean {
      return domainObject.type === RESOURCE_TYPE;
    },

    async request(domainObject: DomainObject, options: RequestOptions): Promise<Datum[]> {
      const parsed = parseKey(domainObject.identifier.key);
      // Both predicted resources and synthesized actuals are served here; they
      // share the same profile, with actuals perturbed (close-the-U).
      if (parsed.kind !== 'resource' && parsed.kind !== 'actual') {
        return [];
      }
      const isActual = parsed.kind === 'actual';

      try {
        const startMs = await context.getPlanStartMs(parsed.planId);
        const base = await context.getResourceDatums(parsed.datasetId, parsed.name, startMs);
        if (base.length === 0) {
          // No data for this resource — a legitimately empty series, not a failure.
          return [];
        }
        const datums = isActual ? actualizeDatums(base, parsed.name) : base;

        if (options.strategy === 'latest') {
          const latest = lastAtOrBefore(datums, options.end);
          return latest ? [latest] : [];
        }

        const windowed = windowDatums(datums, options.start, options.end);

        // Plot request on a continuous (real) profile → decimate to the point budget.
        if (options.strategy === 'minmax' && options.size) {
          const profileType = await context.getProfileType(parsed.datasetId, parsed.name);
          if (profileType?.type === 'real') {
            return minMaxDecimate(windowed, options.size);
          }
        }
        return windowed;
      } catch (error) {
        // A genuine load failure (backend dropped, bad data) — alert the planner
        // instead of spinning on an empty plot.
        const message = error instanceof Error ? error.message : String(error);
        context.notifier.error(`PlanDev: failed to load data for "${parsed.name}" — ${message}`);
        return [];
      }
    },
  };
}

/** Last datum at or before `t` (datums are ascending by utc). */
function lastAtOrBefore(datums: Datum[], t: number): Datum | undefined {
  let found: Datum | undefined;
  for (const datum of datums) {
    if (datum.utc <= t) {
      found = datum;
    } else {
      break;
    }
  }
  return found ?? datums[0];
}

/** Datums within [start, end], plus the bracketing points so lines reach edges. */
function windowDatums(datums: Datum[], start: number, end: number): Datum[] {
  const out: Datum[] = [];
  for (let i = 0; i < datums.length; i++) {
    const datum = datums[i];
    const inWindow = datum.utc >= start && datum.utc <= end;
    const bracketsStart = datum.utc < start && datums[i + 1]?.utc >= start;
    const bracketsEnd = datum.utc > end && datums[i - 1]?.utc <= end;
    if (inWindow || bracketsStart || bracketsEnd) {
      out.push(datum);
    }
  }
  return out;
}
