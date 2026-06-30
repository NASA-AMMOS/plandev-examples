/**
 * A context-menu action that snaps the OpenMCT time conductor to a PlanDev plan's
 * (or sim's) span, in fixed mode.
 *
 * Why: PlanDev data is historical — each plan lives at its own past span — but a host
 * may boot the conductor in realtime ("now − 30m → now") or on an unrelated range, so
 * a planner opening a PlanDev resource sees an empty plot until the conductor overlaps
 * the plan. This action fixes that in one click. The demo host pre-sets the latest
 * plan's span at startup; this action makes the plugin self-sufficient in *any* host
 * (e.g. one whose default clock is realtime).
 */
import type { DomainObject, OpenMCT, TimeBounds } from './openmct';

/** The bounds-relevant fields the object provider attaches as `plandevMeta`. */
interface BoundsMeta {
  kind?: string;
  startTime?: string | null;
  endTime?: string | null;
  simStart?: string | null;
  simEnd?: string | null;
}

/**
 * Time bounds (epoch ms) for a plan/sim domain object, from the metadata the object
 * provider attaches. Prefers a sim's own run window when present, else the plan span.
 * Returns null when there's no usable range — a sim that never ran (with no plan span),
 * a resource/other node, or an unparseable/inverted range.
 */
export function boundsFromMeta(meta: BoundsMeta | undefined): TimeBounds | null {
  if (!meta || (meta.kind !== 'plan' && meta.kind !== 'sim')) {
    return null;
  }
  const startIso = (meta.kind === 'sim' && meta.simStart) || meta.startTime;
  const endIso = (meta.kind === 'sim' && meta.simEnd) || meta.endTime;
  if (!startIso || !endIso) {
    return null;
  }
  const start = Date.parse(startIso);
  const end = Date.parse(endIso);
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) {
    return null;
  }
  return { end, start };
}

/** Switches the conductor to fixed mode on `bounds`, tolerant of 3.x/4.x time APIs. */
export function setConductorBounds(openmct: OpenMCT, bounds: TimeBounds): void {
  const time = openmct.time;
  if (typeof time.setMode === 'function') {
    time.setMode('fixed', bounds); // 4.x: fixed mode + bounds (also clears the clock)
  } else if (typeof time.stopClock === 'function') {
    time.stopClock(); // 3.x: leave realtime so bounds aren't overwritten by the clock
  }
  if (typeof time.setBounds === 'function') {
    time.setBounds(bounds);
  } else if (typeof time.bounds === 'function') {
    time.bounds(bounds);
  }
}

/** Registers the "Set conductor to plan span" action for PlanDev plan/sim nodes. */
export function registerConductorAction(openmct: OpenMCT, namespace: string): void {
  if (!openmct.actions || typeof openmct.actions.register !== 'function') {
    return; // host's action API absent — skip rather than throw (stay self-contained)
  }
  openmct.actions.register({
    appliesTo(objectPath: DomainObject[]): boolean {
      const object = objectPath?.[0];
      return (
        object?.identifier?.namespace === namespace &&
        boundsFromMeta(object.plandevMeta as BoundsMeta | undefined) != null
      );
    },
    cssClass: 'icon-clock',
    description: "Snap the time conductor to this PlanDev plan/sim's span (fixed mode).",
    group: 'action',
    invoke(objectPath: DomainObject[]): void {
      const bounds = boundsFromMeta(objectPath?.[0]?.plandevMeta as BoundsMeta | undefined);
      if (bounds) {
        setConductorBounds(openmct, bounds);
      }
    },
    key: 'plandev.set-conductor',
    name: 'Set conductor to plan span',
    priority: 5,
  });
}
