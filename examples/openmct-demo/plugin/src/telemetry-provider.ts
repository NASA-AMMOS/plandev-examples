/**
 * Historical telemetry provider for PlanDev resource leaves. On request it
 * fetches the resource's profile, samples it (sample.ts), windows it to the
 * requested bounds, and honors the 'latest' strategy.
 *
 * Demo scope: completed sims, historical only — no realtime subscription. We
 * return all points in the window (PlanDev profiles are already change-point
 * sampled, so they're small); a connector pulling raw dense telemetry is where
 * min/max decimation would belong, not here.
 */
import { actualizeDatums } from './actuals';
import { RESOURCE_TYPE } from './constants';
import type { PluginContext } from './context';
import { parseKey } from './identifiers';
import type { DomainObject, RequestOptions, TelemetryProvider } from './openmct';
import { type Datum, sampleProfile } from './sample';

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

      const startMs = await context.getPlanStartMs(parsed.planId);
      const profile = await context.getProfile(parsed.datasetId, parsed.name);
      if (!profile) {
        return [];
      }

      const datums = isActual
        ? actualizeDatums(sampleProfile(profile, startMs), parsed.name)
        : sampleProfile(profile, startMs);
      if (options.strategy === 'latest') {
        const latest = lastAtOrBefore(datums, options.end);
        return latest ? [latest] : [];
      }

      return windowDatums(datums, options.start, options.end);
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
