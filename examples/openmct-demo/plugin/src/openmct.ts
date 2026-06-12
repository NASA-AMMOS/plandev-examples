/**
 * Minimal structural types for the slice of the OpenMCT plugin API this plugin
 * uses. OpenMCT ships limited types, so we declare just what we touch — enough
 * for strict TypeScript without depending on OpenMCT's own typings.
 */
import type { TelemetryValue } from './metadata';

export interface Identifier {
  namespace: string;
  key: string;
}

export interface DomainObject {
  identifier: Identifier;
  type: string;
  name: string;
  location?: string;
  telemetry?: { values: TelemetryValue[] };
  /** Plan ('plan' type) objects read their JSON from here (string or object). */
  selectFile?: { name: string; body: unknown };
  [key: string]: unknown;
}

export interface RequestOptions {
  start: number;
  end: number;
  domain?: string;
  strategy?: 'minmax' | 'latest';
  size?: number;
}

export interface ObjectProvider {
  get(identifier: Identifier): Promise<DomainObject>;
}

export interface CompositionProvider {
  appliesTo(domainObject: DomainObject): boolean;
  load(domainObject: DomainObject): Promise<Identifier[]>;
}

export interface TelemetryProvider {
  supportsRequest(domainObject: DomainObject): boolean;
  request(domainObject: DomainObject, options: RequestOptions): Promise<object[]>;
}

export interface OpenMCT {
  types: { addType(key: string, definition: Record<string, unknown>): void };
  objects: {
    addRoot(identifier: Identifier | Identifier[], priority?: number): void;
    addProvider(namespace: string, provider: ObjectProvider): void;
  };
  composition: { addProvider(provider: CompositionProvider): void };
  telemetry: { addProvider(provider: TelemetryProvider): void };
}

/** OpenMCT keyString form: `namespace:key`. */
export const keyString = (identifier: Identifier): string =>
  `${identifier.namespace}:${identifier.key}`;
