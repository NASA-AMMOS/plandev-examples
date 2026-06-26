/**
 * Maps a PlanDev profile type (real/discrete + ValueSchema) onto an OpenMCT
 * telemetry metadata `values[]` array: one domain (time) value + one range
 * (data) value, plus units/enumerations where the schema provides them.
 */
import type { ProfileType, ValueSchema } from './types';

/** An OpenMCT telemetry value descriptor (subset of fields we set). */
export interface TelemetryValue {
  key: string;
  name: string;
  source?: string;
  format?: string;
  /** printf-style format applied to the value (OpenMCT's `formatString`), e.g. `%.3f`. */
  formatString?: string;
  /** OpenMCT is inconsistent: the plot series/legend reads `unit` (singular), the Y-axis
   * fallback reads `units` (plural) — set both. */
  unit?: string;
  units?: string;
  hints?: { domain?: number; range?: number };
  enumerations?: Array<{ value: number; string: string }>;
}

export const TIME_KEY = 'utc';
export const VALUE_KEY = 'value';

/**
 * Whether a profile holds a numeric (plottable) value.
 *
 * The `real`/`discrete` discriminator is about *interpolation* (linear vs step),
 * not value type: a `discrete` profile can still carry real/int values (e.g.
 * `BetaAngle_MARS`). So we decide numeric-ness from the value **schema**, except
 * `real` profiles whose schema is the linear `{initial, rate}` struct.
 */
export function isNumeric(profileType: ProfileType): boolean {
  if (profileType.type === 'real') {
    return true;
  }
  const schemaType = profileType.schema.type;
  return schemaType === 'real' || schemaType === 'int';
}

/**
 * Whether a resource can render in a Plot: numeric, or an *enumerable* discrete
 * (variant/boolean) whose states OpenMCT can map to numeric levels. Free-form
 * string discretes can't (no fixed value set) — they're table/LAD only.
 */
export function isPlottable(profileType: ProfileType): boolean {
  return isNumeric(profileType) || variantsOf(profileType.schema) !== undefined;
}

/** Builds the `telemetry.values` array for a resource leaf object. */
export function profileTypeToValues(profileType: ProfileType): TelemetryValue[] {
  const domain: TelemetryValue = {
    key: TIME_KEY,
    name: 'Time',
    format: 'utc',
    hints: { domain: 1 },
  };

  const range: TelemetryValue = {
    key: VALUE_KEY,
    name: 'Value',
    hints: { range: 1 },
  };

  if (isNumeric(profileType)) {
    range.format = 'float';
    const units = unitOf(profileType.schema);
    if (units) {
      range.units = units;
    }
  } else {
    // Discrete profiles. If the schema enumerates its states (variant/boolean),
    // declare `format: 'enum'` + `enumerations` — OpenMCT's value formatter then
    // maps the string state ↔ a numeric level, so the regular Plot renders it as a
    // stepped state line (there is no separate "discrete plot" view). Free-form
    // strings (no fixed value set) keep `format: 'string'` → table/LAD only.
    const enumerations = variantsOf(profileType.schema);
    if (enumerations) {
      range.format = 'enum';
      range.enumerations = enumerations;
    } else {
      range.format = 'string';
    }
  }

  return [range, domain];
}

function unitOf(schema: ValueSchema): string | undefined {
  const metadata = schema.metadata;
  return metadata?.unit?.value ?? metadata?.description?.value;
}

function variantsOf(schema: ValueSchema): Array<{ value: number; string: string }> | undefined {
  if (schema.type === 'variant') {
    // Each variant → a numeric level. We register BOTH the key and the label as
    // enum strings (label last, so it wins for the axis/legend) because a profile
    // segment's discrete value may serialize as either — OpenMCT's formatter maps
    // whichever the datum carries back to the level.
    return schema.variants.flatMap((variant, index) =>
      variant.key === variant.label
        ? [{ string: variant.label, value: index }]
        : [
            { string: variant.key, value: index },
            { string: variant.label, value: index },
          ],
    );
  }
  if (schema.type === 'boolean') {
    return [
      { string: 'false', value: 0 },
      { string: 'true', value: 1 },
    ];
  }
  return undefined;
}
