import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import CensusAsOfDateField, { isCensusAsOfDate } from './CensusAsOfDateField';

describe('Census as-of date field', () => {
  it('accepts only a complete date', () => {
    expect(isCensusAsOfDate('2025-12-31')).toBe(true);
    expect(isCensusAsOfDate('')).toBe(false);
    expect(isCensusAsOfDate('2025-12')).toBe(false);
    expect(isCensusAsOfDate('2025-13-45')).toBe(false);
    expect(isCensusAsOfDate('2025-02-30')).toBe(false);
    expect(isCensusAsOfDate('2024-02-29')).toBe(true);
  });

  it('renders the prefilled date as a required input', () => {
    const html = renderToStaticMarkup(<CensusAsOfDateField value="2025-12-31" onChange={() => undefined} />);
    expect(html).toContain('type="date"');
    expect(html).toContain('required');
    expect(html).toContain('value="2025-12-31"');
  });
});
