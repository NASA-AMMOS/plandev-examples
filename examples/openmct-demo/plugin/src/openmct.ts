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
  /** Present on a *dynamic* provider — OpenMCT subscribes here for live add/remove. */
  on?(
    domainObject: DomainObject,
    event: string,
    callback: (child: Identifier) => void,
    context?: unknown,
  ): void;
  off?(
    domainObject: DomainObject,
    event: string,
    callback: (child: Identifier) => void,
    context?: unknown,
  ): void;
}

export interface TelemetryProvider {
  supportsRequest(domainObject: DomainObject): boolean;
  request(domainObject: DomainObject, options: RequestOptions): Promise<object[]>;
}

/** A small throttled error notifier the providers use to surface failures to the planner. */
export interface Notifier {
  error(message: string): void;
}

/** OpenMCT's notification API (the slice we use): visible, dismissible toasts. */
export interface Notifications {
  alert(message: string): unknown;
  error(message: string): unknown;
  info(message: string): unknown;
}

/** One node of an OpenMCT inspector selection. For an object it's `context.item`; for a
 * selected Plan activity it's `context.type === 'activity'` + `context.activity`. */
export interface InspectorSelectionItem {
  context?: { item?: DomainObject; type?: string; activity?: Record<string, unknown> };
}
/** `selection[0][0].context.item` is the primary selected object. */
export type InspectorSelection = InspectorSelectionItem[][];

export interface InspectorView {
  destroy(): void;
  show(element: HTMLElement): void;
}

export interface InspectorViewProvider {
  canView(selection: InspectorSelection): boolean;
  glyph?: string;
  key: string;
  name: string;
  priority?(): number;
  view(selection: InspectorSelection): InspectorView;
}

export interface OpenMCT {
  types: { addType(key: string, definition: Record<string, unknown>): void };
  objects: {
    addRoot(identifier: Identifier | Identifier[], priority?: number): void;
    addProvider(namespace: string, provider: ObjectProvider): void;
  };
  composition: { addProvider(provider: CompositionProvider): void };
  telemetry: { addProvider(provider: TelemetryProvider): void };
  notifications: Notifications;
  inspectorViews: { addProvider(provider: InspectorViewProvider): void };
  /** Emits `'reload'` (with the reloaded object) when a planner uses the Reload action. */
  objectViews: {
    on(event: string, callback: (domainObject: DomainObject) => void): void;
    off(event: string, callback: (domainObject: DomainObject) => void): void;
  };
}

/** OpenMCT keyString form: `namespace:key`. */
export const keyString = (identifier: Identifier): string =>
  `${identifier.namespace}:${identifier.key}`;
