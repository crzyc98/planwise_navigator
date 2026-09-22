import { describe, expect, it } from 'vitest';

import { buildEventQueryParams } from './EventFilterBar';

describe('event filter query parameters', () => {
  it('omits empty filter values', () => {
    expect(buildEventQueryParams({ simulation_year: '', event_type: '', event_category: '', employee_id: '' })).toEqual({});
  });

  it('drops whitespace-only employee IDs and coerces simulation years', () => {
    expect(buildEventQueryParams({ simulation_year: ' 2026 ', event_type: '', event_category: '', employee_id: '   ' })).toEqual({ simulation_year: 2026 });
  });

  it('keeps all meaningful combined filters', () => {
    expect(buildEventQueryParams({ simulation_year: '2025', event_type: ' hire ', event_category: ' employment ', employee_id: ' emp_a ' })).toEqual({ simulation_year: 2025, event_type: 'hire', event_category: 'employment', employee_id: 'emp_a' });
  });
});
