/**
 * Synthesizes "as-flown" actuals from a sim's predicted profile, for the
 * close-the-U demo. Actual = predicted value perturbed by a slow drift plus a
 * small fast wiggle, so an Overlay Plot of predict vs actual shows believable
 * divergence — the signal a planner would replan against.
 *
 * The perturbation is a pure function of (timestamp, resource) so the actual
 * line is stable across pans/zooms (no flicker) and needs no stored state.
 */
import type { Datum } from './sample';

/** Stable phase in [0, 2π) derived from the resource name. */
function seedFor(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff;
  }
  return ((hash >>> 0) % 1000) / 1000 * Math.PI * 2;
}

const HOUR_MS = 3_600_000;
const MINUTE_MS = 60_000;

/** Applies the predict→actual perturbation to one numeric value at time `t`. */
function perturb(predicted: number, t: number, seed: number): number {
  const drift = 0.06 * Math.sin(t / (3 * HOUR_MS) + seed); // ±6% over ~hours
  const wiggle = 0.015 * Math.sin(t / (5 * MINUTE_MS) + seed * 3); // ±1.5% minute-scale
  return predicted * (1 + drift + wiggle);
}

/** Maps predicted datums to actuals. Non-numeric values pass through unchanged. */
export function actualizeDatums(datums: Datum[], name: string): Datum[] {
  const seed = seedFor(name);
  return datums.map(datum =>
    typeof datum.value === 'number'
      ? { utc: datum.utc, value: perturb(datum.value, datum.utc, seed) }
      : datum,
  );
}
