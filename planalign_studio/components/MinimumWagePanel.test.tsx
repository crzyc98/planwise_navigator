import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import MinimumWagePanel from './MinimumWagePanel';
import type { MinimumWageYear } from '../services/api';

vi.mock('../services/api', () => ({}));

const rows: MinimumWageYear[] = [
  {
    simulation_year: 2025, effective_date: null, minimum_hourly_rate: null, people_raised: null, people_with_rate: null,
    people_without_rate: null, people_not_covered: null, added_annual_pay: null, raised_still_active: 0, estimated_added_pay: 0,
  },
  {
    simulation_year: 2026, effective_date: '2026-07-01', minimum_hourly_rate: 20, people_raised: 18, people_with_rate: 86,
    people_without_rate: 39, people_not_covered: 31, added_annual_pay: 888615.46, raised_still_active: 16, estimated_added_pay: 914299.05,
  },
];

const render = (value: MinimumWageYear[] | undefined) =>
  renderToStaticMarkup(<MemoryRouter><MinimumWagePanel rows={value} comparePath="/w/ws/compare" /></MemoryRouter>);

describe('Minimum wage results', () => {
  it('shows nothing for a run without a minimum wage', () => {
    expect(render([])).toBe('');
    expect(render(undefined)).toBe('');
  });

  it('shows each year: who was raised, who had no rate, and the estimate', () => {
    const html = render(rows);
    expect(html).toContain('$20.00 from Jul 1, 2026');
    for (const value of ['18', '$888,615', '39', '31', '16', '$914,299']) expect(html).toContain(`>${value}</td>`);
    expect(html).toContain('Added pay at year end (est.)');
  });

  it('sends the analyst to Cost Comparison for employer contributions', () => {
    const html = render(rows);
    expect(html).toContain("Added employer contributions can&#x27;t be separated within one run.");
    expect(html).toContain('href="/w/ws/compare"');
  });
});
