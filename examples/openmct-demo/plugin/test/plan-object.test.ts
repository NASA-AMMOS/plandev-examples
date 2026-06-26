/**
 * buildExternalEventsPlan groups a plan's external events by type into Gantt swimlanes,
 * labels each by its key, computes absolute times, and skips unparseable ones.
 */
import { describe, expect, it } from 'vitest';

import { buildExternalEventsPlan } from '../src/plan-object';
import type { ExternalEvent } from '../src/types';

function evt(partial: Partial<ExternalEvent>): ExternalEvent {
  return {
    attributes: {},
    derivation_group_name: 'dg',
    duration: '01:00:00',
    event_type_name: 'DSNContact',
    key: 'k',
    source_key: 's',
    start_time: '2024-01-01T00:00:00Z',
    ...partial,
  };
}

describe('buildExternalEventsPlan', () => {
  it('groups by event type, labels by key, and computes absolute times', () => {
    const body = buildExternalEventsPlan([
      evt({ duration: '01:00:00', event_type_name: 'DSNContact', key: 'c1' }),
      evt({ event_type_name: 'ViewPeriod', key: 'v1', start_time: '2024-01-01T02:00:00Z' }),
    ]);

    expect(Object.keys(body).sort()).toEqual(['DSNContact', 'ViewPeriod']);
    const contact = body.DSNContact[0];
    expect(contact.name).toBe('c1');
    expect(contact.isExternalEvent).toBe(true);
    expect(contact.derivationGroup).toBe('dg');
    expect(contact.end - contact.start).toBe(3_600_000);
  });

  it('skips events with an unparseable start time (no empty group)', () => {
    expect(Object.keys(buildExternalEventsPlan([evt({ start_time: 'nope' })]))).toHaveLength(0);
  });
});
