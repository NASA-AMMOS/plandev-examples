/**
 * PlanDev (Aerie) GraphQL data shapes, narrowed to the fields this plugin reads.
 * These mirror the shapes in plandev-ui (src/types/simulation.ts, src/types/schema.ts).
 */

/** PlanDev ValueSchema — describes the type of a resource/profile value. */
export type ValueSchema =
  | { type: 'boolean'; metadata?: ValueSchemaMetadata }
  | { type: 'duration'; metadata?: ValueSchemaMetadata }
  | { type: 'int'; metadata?: ValueSchemaMetadata }
  | { type: 'path'; metadata?: ValueSchemaMetadata }
  | { type: 'real'; metadata?: ValueSchemaMetadata }
  | { type: 'secret'; metadata?: ValueSchemaMetadata }
  | { type: 'series'; items: ValueSchema; metadata?: ValueSchemaMetadata }
  | { type: 'string'; metadata?: ValueSchemaMetadata }
  | { type: 'struct'; items: Record<string, ValueSchema>; metadata?: ValueSchemaMetadata }
  | { type: 'variant'; variants: Variant[]; metadata?: ValueSchemaMetadata };

export interface ValueSchemaMetadata {
  description?: { value: string };
  unit?: { value: string };
  [key: string]: unknown;
}

export interface Variant {
  key: string;
  label: string;
}

/** The `type` JSONB column on a profile: the real/discrete discriminator + inner schema. */
export interface ProfileType {
  schema: ValueSchema;
  type: 'discrete' | 'real';
}

export interface ProfileSegment {
  dynamics: unknown; // number-ish for `real` ({initial, rate}), scalar for `discrete`
  is_gap: boolean;
  start_offset: string; // Postgres interval relative to dataset start
}

export interface Profile {
  duration: string; // Postgres interval
  name: string;
  type: ProfileType;
  profile_segments: ProfileSegment[];
}

/** A profile with only metadata (no segments) — used to build the tree cheaply. */
export interface ProfileDescriptor {
  name: string;
  type: ProfileType;
}

export interface Plan {
  id: number;
  name: string;
  model_id: number;
  start_time: string; // ISO timestamptz
  duration: string; // Postgres interval
}

export interface SimulationDataset {
  id: number; // simulation_dataset.id (the "simulation dataset id" shown in the UI)
  dataset_id: number; // FK into the dataset table — profiles/spans key on this
  status: 'pending' | 'incomplete' | 'failed' | 'success' | string;
  simulation_start_time: string | null;
  simulation_end_time: string | null;
}

export interface Span {
  span_id: number;
  parent_id: number | null;
  type: string;
  start_offset: string; // interval relative to dataset start
  duration: string; // interval
  attributes: unknown;
}
