/** OpenMCT type keys used across the providers. */

/** Built-in folder type — used for the Root / Plan / Sim container nodes. */
export const FOLDER_TYPE = 'folder';

/** Our telemetry leaf type (a sampled PlanDev resource profile). */
export const RESOURCE_TYPE = 'plandev.resource';

/** Built-in Plan type — provided by openmct.plugins.Plan(), rendered as Gantt/Time-List. */
export const PLAN_TYPE = 'plan';

/** Built-in Overlay Plot type — one or more series on shared axes. */
export const OVERLAY_PLOT_TYPE = 'telemetry.plot.overlay';

/**
 * Built-in Display Layout type — a fixed canvas of explicitly-sized frames. We
 * use it for the ready-made "Resource Plot" so each resource gets a configurable
 * height (the one OpenMCT-native, CSS-free way to size plots). Frames hold
 * single-series Overlay Plots (raw telemetry in a layout renders as a value, not
 * a plot). View-only: pre-populated `configuration.items` means no mutate on view.
 */
export const LAYOUT_TYPE = 'layout';
