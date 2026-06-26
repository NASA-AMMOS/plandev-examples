/**
 * Lazily lists each container node's children as identifiers:
 *   Root  → Plans
 *   Plan  → Sims
 *   Sim   → Activities (Plan object) + Resource leaves
 * OpenMCT then resolves each identifier through the object provider.
 *
 * It's a **dynamic** provider: it implements `on`/`off` and a `refresh()` that
 * re-loads a node and emits add/remove diffs, so the Reload action updates the
 * browse tree in place (OpenMCT's reload otherwise only reloads the open object
 * view). The diff is by a per-child **signature**, not just identifier: a sim's
 * signature includes its status, so a sim finishing (pending→success) is detected
 * and that one node is re-resolved (fresh label + subtree) while every unchanged
 * node — including expanded ones — is left untouched. Loads are wrapped so a failed
 * PlanDev call surfaces a toast (and a root status node) instead of an empty tree.
 */
import type { PluginContext } from './context';
import {
  activitiesKey,
  compareDirKey,
  compareKey,
  externalEventsKey,
  parseKey,
  planKey,
  plotKey,
  resourceKey,
  simKey,
  statusKey,
} from './identifiers';
import type { CompositionProvider, DomainObject, Identifier } from './openmct';
import { keyString } from './openmct';

type ChildListener = { callback: (child: Identifier) => void; context?: unknown };

/** A child identifier plus a signature that changes when the child should re-resolve. */
interface Child {
  id: Identifier;
  signature: string;
}

/** Our provider also exposes `refresh()` so the reload hook can re-pull a node. */
export interface PlandevCompositionProvider extends CompositionProvider {
  refresh(domainObject: DomainObject): Promise<void>;
}

export function createCompositionProvider(context: PluginContext): PlandevCompositionProvider {
  const ns = context.namespace;
  const id = (key: string): Identifier => ({ key, namespace: ns });
  /** A child whose signature is its key, plus optional volatile state (e.g. sim status). */
  const child = (key: string, volatile?: string): Child => ({
    id: id(key),
    signature: volatile === undefined ? key : `${key}#${volatile}`,
  });

  // Dynamic-composition state: who's listening to each node, and its last children.
  const listeners = new Map<string, { add: ChildListener[]; remove: ChildListener[] }>();
  const lastChildren = new Map<string, Child[]>();

  /** The actual child-listing logic, wrapped so failures stay legible. */
  async function loadChildren(domainObject: DomainObject): Promise<Child[]> {
    const parsed = parseKey(domainObject.identifier.key);

    try {
      switch (parsed.kind) {
        case 'root': {
          const plans = await context.getPlans();
          if (plans.length === 0) {
            return [child(statusKey('No PlanDev plans found'))];
          }
          context.rememberBounds(plans[0]); // newest (plans are id-desc)
          // Signature includes the name so a rename re-resolves the node.
          return plans.map(plan => child(planKey(plan.id), plan.name));
        }

        case 'plan': {
          const [sims, groups] = await Promise.all([
            context.getSimulationDatasets(parsed.planId),
            context.getPlanDerivationGroups(parsed.planId),
          ]);
          // Signature includes status → a sim finishing (pending→success) re-resolves.
          const children = sims.map(sim =>
            child(simKey(parsed.planId, sim.id, sim.dataset_id), sim.status),
          );
          // Plan-level external events, when the plan links any derivation groups.
          if (groups.length > 0) {
            children.push(child(externalEventsKey(parsed.planId)));
          }
          return children;
        }

        case 'sim': {
          const profileTypes = await context.getProfileTypes(parsed.datasetId);
          // Ready-made displays first, then the raw resources.
          const children: Child[] = [
            child(plotKey(parsed.datasetId, parsed.planId)),
            child(compareDirKey(parsed.datasetId, parsed.planId)),
            child(activitiesKey(parsed.datasetId, parsed.planId)),
          ];
          for (const name of profileTypes.keys()) {
            children.push(child(resourceKey(parsed.datasetId, parsed.planId, name)));
          }
          return children;
        }

        case 'compareDir': {
          // One predict-vs-actual overlay plot per (first few) numeric resources.
          const names = await context.getNumericResourceNames(parsed.datasetId, 15);
          return names.map(name => child(compareKey(parsed.datasetId, parsed.planId, name)));
        }

        default:
          return [];
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      context.notifier.error(`PlanDev: ${message}`);
      // At the root, surface a persistent node so the failure is visible in the
      // tree, not just a transient toast. Deeper levels render empty under their
      // (already-visible) parent, which the toast explains.
      return parsed.kind === 'root'
        ? [child(statusKey('⚠ Could not reach PlanDev — see console'))]
        : [];
    }
  }

  function notify(targets: ChildListener[], childId: Identifier): void {
    for (const listener of targets) {
      if (listener.context) {
        listener.callback.call(listener.context, childId);
      } else {
        listener.callback(childId);
      }
    }
  }

  return {
    appliesTo(domainObject: DomainObject): boolean {
      if (domainObject.identifier.namespace !== ns) {
        return false;
      }
      const kind = parseKey(domainObject.identifier.key).kind;
      return kind === 'root' || kind === 'plan' || kind === 'sim' || kind === 'compareDir';
    },

    async load(domainObject: DomainObject): Promise<Identifier[]> {
      const children = await loadChildren(domainObject);
      lastChildren.set(keyString(domainObject.identifier), children);
      return children.map(c => c.id);
    },

    on(domainObject: DomainObject, event: string, callback: (child: Identifier) => void, ctx?: unknown): void {
      const key = keyString(domainObject.identifier);
      const entry = listeners.get(key) ?? { add: [], remove: [] };
      (event === 'add' ? entry.add : entry.remove).push({ callback, context: ctx });
      listeners.set(key, entry);
    },

    off(domainObject: DomainObject, event: string, callback: (child: Identifier) => void, ctx?: unknown): void {
      const entry = listeners.get(keyString(domainObject.identifier));
      if (!entry) {
        return;
      }
      const targets = event === 'add' ? entry.add : entry.remove;
      const index = targets.findIndex(l => l.callback === callback && l.context === ctx);
      if (index >= 0) {
        targets.splice(index, 1);
      }
    },

    /**
     * Re-pull a node and emit a minimal diff to its listeners. A child is removed +
     * re-added only when it's new, gone, or its signature changed (e.g. a sim's
     * status) — so a changed node re-resolves (fresh label/subtree) while every
     * unchanged node stays put (expanded nodes are not collapsed). A re-added child
     * lands at the end (OpenMCT appends on add), so a status change moves that sim to
     * the bottom of its list; a true in-place update would need mutable objects.
     */
    async refresh(domainObject: DomainObject): Promise<void> {
      const key = keyString(domainObject.identifier);
      const previous = lastChildren.get(key) ?? [];
      const next = await loadChildren(domainObject);
      lastChildren.set(key, next);

      const entry = listeners.get(key);
      if (!entry) {
        return; // node not currently observed (e.g. collapsed) — nothing to emit
      }
      const previousByKey = new Map(previous.map(c => [keyString(c.id), c]));
      const nextByKey = new Map(next.map(c => [keyString(c.id), c]));

      for (const prev of previous) {
        const match = nextByKey.get(keyString(prev.id));
        if (!match || match.signature !== prev.signature) {
          notify(entry.remove, prev.id);
        }
      }
      for (const candidate of next) {
        const match = previousByKey.get(keyString(candidate.id));
        if (!match || match.signature !== candidate.signature) {
          notify(entry.add, candidate.id);
        }
      }
    },
  };
}
