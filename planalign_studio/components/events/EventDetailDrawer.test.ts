import { describe, expect, it } from 'vitest';

import { formatEventField } from './EventDetailDrawer';

describe('event detail formatting', () => {
  it('shows missing values as an em dash', () => {
    expect(formatEventField('event_details', null)).toBe('—');
    expect(formatEventField('created_at', undefined)).toBe('—');
  });

  it('formats compensation as currency', () => {
    expect(formatEventField('compensation_amount', 1234.5)).toBe('$1,234.50');
  });

  it('keeps employee SSNs unredacted', () => {
    expect(formatEventField('employee_ssn', '123-45-6789')).toBe('123-45-6789');
  });
});
