/**
 * Read-only "PlanDev" inspector panels:
 *  - for plan/sim nodes (owner, start/end/duration, tags, sim status), and
 *  - for a selected Plan activity (type, span id, arguments, computed attributes),
 * each with an "Open in PlanDev" deep-link. Non-invasive: separate inspector views
 * (`openmct.inspectorViews.addProvider`) that read what the object provider attaches
 * (`domainObject.plandevMeta`) or what the Plan view selects (`context.activity`).
 *
 * Content is rendered as stacked OpenMCT "inspect-properties" groups — a header bar
 * (`Metadata` / `Arguments` / `Computed attributes`) above each two-column section.
 */
import type { DomainObject, InspectorSelection, InspectorViewProvider } from './openmct';

/** Metadata the object provider attaches to plan / sim / resource domain objects. */
interface PlandevMeta {
  kind?: 'plan' | 'sim' | 'resource';
  planId?: number;
  datasetId?: number;
  owner?: string | null;
  model?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  duration?: string;
  tags?: string[];
  createdAt?: string;
  updatedAt?: string;
  status?: string;
  simStart?: string | null;
  simEnd?: string | null;
  // resource
  name?: string;
  dataType?: string;
  unit?: string | null;
  description?: string | null;
}

/** The activity object the Plan view selects (`context.activity`), enriched in plan-object.ts.
 * Covers both simulated activities and external events (`isExternalEvent`). */
interface ActivityCtx {
  name?: string;
  type?: string;
  spanId?: number;
  directiveId?: number;
  arguments?: Record<string, unknown>;
  computedAttributes?: Record<string, unknown>;
  planId?: number;
  simulationDatasetId?: number;
  planStartTime?: string | null;
  planEndTime?: string | null;
  // external event
  isExternalEvent?: boolean;
  eventKey?: string;
  sourceKey?: string;
  derivationGroup?: string;
  eventAttributes?: unknown;
}

// --- plan / sim metadata panel ------------------------------------------------

export function createPlandevInspectorView(
  namespace: string,
  planDevUiUrl: string,
): InspectorViewProvider {
  return {
    canView(selection: InspectorSelection): boolean {
      const item = selectedItem(selection);
      return item?.identifier?.namespace === namespace && metaOf(item) !== undefined;
    },
    glyph: 'icon-info',
    key: 'plandev.metadata',
    name: 'PlanDev',
    priority(): number {
      return 10;
    },
    view(selection: InspectorSelection) {
      const meta = metaOf(selectedItem(selection));
      return {
        destroy(): void {},
        show(element: HTMLElement): void {
          element.innerHTML = meta ? renderMeta(meta, planDevUiUrl) : '';
        },
      };
    },
  };
}

// --- selected-activity panel --------------------------------------------------

export function createPlandevActivityInspectorView(planDevUiUrl: string): InspectorViewProvider {
  return {
    canView(selection: InspectorSelection): boolean {
      return selection?.[0]?.[0]?.context?.type === 'activity';
    },
    glyph: 'icon-info',
    key: 'plandev.activity',
    name: 'PlanDev',
    priority(): number {
      return 10;
    },
    view(selection: InspectorSelection) {
      const activity = selection?.[0]?.[0]?.context?.activity as ActivityCtx | undefined;
      return {
        destroy(): void {},
        show(element: HTMLElement): void {
          element.innerHTML = activity ? renderActivity(activity, planDevUiUrl) : '';
        },
      };
    },
  };
}

// --- rendering ----------------------------------------------------------------

function selectedItem(selection: InspectorSelection): DomainObject | undefined {
  return selection?.[0]?.[0]?.context?.item;
}

function metaOf(item: DomainObject | undefined): PlandevMeta | undefined {
  const meta = (item as { plandevMeta?: unknown } | undefined)?.plandevMeta;
  return meta && typeof meta === 'object' ? (meta as PlandevMeta) : undefined;
}

function renderMeta(meta: PlandevMeta, planDevUiUrl: string): string {
  let rows: string[];
  if (meta.kind === 'sim') {
    rows = [
      row('Status', meta.status),
      row('Dataset', meta.datasetId),
      row('Sim start', fmtTime(meta.simStart)),
      row('Sim end', fmtTime(meta.simEnd)),
    ];
  } else if (meta.kind === 'resource') {
    rows = [
      row('Name', meta.name),
      row('Type', meta.dataType),
      row('Unit', meta.unit || '—'),
      row('Description', meta.description || '—'),
    ];
  } else {
    rows = [
      row('Owner', meta.owner),
      row('Model', meta.model || '—'),
      row('Start', fmtTime(meta.startTime)),
      row('End', fmtTime(meta.endTime)),
      row('Duration', meta.duration),
      row('Tags', meta.tags && meta.tags.length ? meta.tags.join(', ') : '—'),
      row('Created', fmtTime(meta.createdAt)),
      row('Updated', fmtTime(meta.updatedAt)),
    ];
  }

  // Resource panels have no planId → no backlink; plan/sim link to the Aerie UI.
  const href = aerieUrl(planDevUiUrl, {
    endTime: meta.endTime,
    planId: meta.planId,
    simulationDatasetId: meta.kind === 'sim' ? meta.datasetId : undefined,
    startTime: meta.startTime,
  });
  return panel(group('Metadata', rows.join('')), href);
}

function renderActivity(activity: ActivityCtx, planDevUiUrl: string): string {
  // External events (DSN contacts, view periods, …) carry different identity than
  // simulated activities — render their source/group/attributes instead.
  if (activity.isExternalEvent) {
    const metadata = group(
      'Metadata',
      [
        row('Key', activity.eventKey ?? activity.name),
        row('Type', activity.type),
        row('Source', activity.sourceKey),
        row('Derivation group', activity.derivationGroup),
      ].join(''),
    );
    return panel(
      metadata + kvGroup('Attributes', activity.eventAttributes as Record<string, unknown> | undefined),
      '',
    );
  }

  const metadata = group(
    'Metadata',
    [
      row('Name', activity.name),
      row('Type', activity.type),
      row('Span id', activity.spanId),
      row('Directive id', activity.directiveId ?? '—'),
    ].join(''),
  );
  const href = aerieUrl(planDevUiUrl, {
    endTime: activity.planEndTime,
    planId: activity.planId,
    simulationDatasetId: activity.simulationDatasetId,
    spanId: activity.spanId,
    startTime: activity.planStartTime,
  });
  return panel(
    metadata + kvGroup('Arguments', activity.arguments) + kvGroup('Computed attributes', activity.computedAttributes),
    href,
  );
}

/** Wraps stacked groups + an optional "Open in PlanDev" link in the panel chrome. */
function panel(groupsHtml: string, href: string): string {
  const link = href
    ? `<a class="c-inspect-properties__row" style="display:block;padding-top:12px" href="${esc(
        href,
      )}" target="_blank" rel="noopener noreferrer">Open in PlanDev ↗</a>`
    : '';
  return `<div class="c-inspect-properties">${groupsHtml}${link}</div>`;
}

/** A header bar above a two-column section of rows. Empty `rowsHtml` → nothing. */
function group(header: string, rowsHtml: string): string {
  if (!rowsHtml) {
    return '';
  }
  return `<div class="c-inspect-properties__header">${esc(header)}</div>
    <ul class="c-inspect-properties__section">${rowsHtml}</ul>`;
}

/** A `group()` built from an object's key/value pairs (arguments, computed attrs).
 * Scalars render inline; nested objects/arrays are pretty-printed JSON in a `<pre>`
 * (readable without a full tree widget — fine for the rare deeply-nested arg). */
function kvGroup(header: string, obj: Record<string, unknown> | undefined): string {
  if (!obj || typeof obj !== 'object' || Object.keys(obj).length === 0) {
    return '';
  }
  const rows = Object.entries(obj)
    .map(([key, value]) =>
      value !== null && typeof value === 'object'
        ? rawRow(
            key,
            `<pre style="white-space:pre-wrap;word-break:break-word;margin:0">${esc(
              JSON.stringify(value, null, 2),
            )}</pre>`,
          )
        : row(key, value),
    )
    .join('');
  return group(header, rows);
}

function row(label: string, value: unknown): string {
  return rawRow(label, esc(value));
}

/** Like `row()`, but the value cell holds pre-built HTML (caller escapes any data). */
function rawRow(label: string, valueHtml: string): string {
  return `<li class="c-inspect-properties__row">
    <div class="c-inspect-properties__label">${esc(label)}</div>
    <div class="c-inspect-properties__value">${valueHtml}</div>
  </li>`;
}

/**
 * Aerie UI deep-link: `/plans/<id>?startTime&endTime[&simulationDatasetId][&spanId]`.
 * `URLSearchParams` encodes `:` → `%3A`, matching PlanDev's own URL shape.
 */
function aerieUrl(
  planDevUiUrl: string,
  opts: {
    planId?: number;
    startTime?: string | null;
    endTime?: string | null;
    simulationDatasetId?: number;
    spanId?: number;
  },
): string {
  const base = planDevUiUrl.replace(/\/$/, '');
  if (!base || opts.planId == null) {
    return '';
  }
  const params = new URLSearchParams();
  if (opts.startTime) {
    params.set('startTime', opts.startTime);
  }
  if (opts.endTime) {
    params.set('endTime', opts.endTime);
  }
  if (opts.simulationDatasetId != null) {
    params.set('simulationDatasetId', String(opts.simulationDatasetId));
  }
  if (opts.spanId != null) {
    params.set('spanId', String(opts.spanId));
  }
  const query = params.toString();
  return `${base}/plans/${opts.planId}${query ? `?${query}` : ''}`;
}

/** ISO timestamp → readable UTC string; passthrough if unparseable, '—' if empty. */
function fmtTime(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? iso : new Date(ms).toUTCString();
}

/** HTML-escape interpolated values (owner/tag/argument strings come from PlanDev data). */
function esc(value: unknown): string {
  const map: Record<string, string> = {
    '"': '&quot;',
    '&': '&amp;',
    "'": '&#39;',
    '<': '&lt;',
    '>': '&gt;',
  };
  return String(value ?? '—').replace(/[&<>"']/g, c => map[c]);
}
