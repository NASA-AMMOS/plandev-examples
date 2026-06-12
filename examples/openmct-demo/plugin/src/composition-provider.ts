/**
 * Lazily lists each container node's children as identifiers:
 *   Root  → Plans
 *   Plan  → Sims
 *   Sim   → Activities (Plan object) + Resource leaves
 * OpenMCT then resolves each identifier through the object provider.
 */
import type { PluginContext } from './context';
import {
  activitiesKey,
  compareDirKey,
  compareKey,
  parseKey,
  planKey,
  plotKey,
  resourceKey,
  simKey,
} from './identifiers';
import type { CompositionProvider, DomainObject, Identifier } from './openmct';

export function createCompositionProvider(context: PluginContext): CompositionProvider {
  const ns = context.namespace;
  const id = (key: string): Identifier => ({ key, namespace: ns });

  return {
    appliesTo(domainObject: DomainObject): boolean {
      if (domainObject.identifier.namespace !== ns) {
        return false;
      }
      const kind = parseKey(domainObject.identifier.key).kind;
      return kind === 'root' || kind === 'plan' || kind === 'sim' || kind === 'compareDir';
    },

    async load(domainObject: DomainObject): Promise<Identifier[]> {
      const parsed = parseKey(domainObject.identifier.key);

      switch (parsed.kind) {
        case 'root': {
          const plans = await context.getPlans();
          if (plans[0]) {
            context.rememberBounds(plans[0]);
          }
          return plans.map(plan => id(planKey(plan.id)));
        }

        case 'plan': {
          const sims = await context.getSimulationDatasets(parsed.planId);
          return sims.map(sim => id(simKey(parsed.planId, sim.id, sim.dataset_id)));
        }

        case 'sim': {
          const profileTypes = await context.getProfileTypes(parsed.datasetId);
          // Ready-made displays first, then the raw resources.
          const children: Identifier[] = [
            id(plotKey(parsed.datasetId, parsed.planId)),
            id(compareDirKey(parsed.datasetId, parsed.planId)),
            id(activitiesKey(parsed.datasetId, parsed.planId)),
          ];
          for (const name of profileTypes.keys()) {
            children.push(id(resourceKey(parsed.datasetId, parsed.planId, name)));
          }
          return children;
        }

        case 'compareDir': {
          // One predict-vs-actual overlay plot per (first few) numeric resources.
          const names = await context.getNumericResourceNames(parsed.datasetId, 15);
          return names.map(name => id(compareKey(parsed.datasetId, parsed.planId, name)));
        }

        default:
          return [];
      }
    },
  };
}
