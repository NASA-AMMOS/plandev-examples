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
    // Discrete profiles carry string state values (e.g. "ON"/"OFF"); the
    // `string` format renders them faithfully. We still surface the schema's
    // variants as enumerations so they appear in limit/legend tooling.
    range.format = 'string';
    const enumerations = variantsOf(profileType.schema);
    if (enumerations) {
      range.enumerations = enumerations;
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
    return schema.variants.map((variant, index) => ({ string: variant.label, value: index }));
  }
  if (schema.type === 'boolean') {
    return [
      { string: 'false', value: 0 },
      { string: 'true', value: 1 },
    ];
  }
  return undefined;
}
