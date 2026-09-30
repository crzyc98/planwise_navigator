import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { employeeImpactParams, EmployeeImpactPage, getEmployeeImpacts, WinnersLosersResponse } from '../services/api';
import { BandImpactTable, EmployeeImpactTable, impactCurrency } from './WinnersLosersDetails';

const comparison = {
  plan_a_scenario_id: 'a', plan_b_scenario_id: 'b', final_year: 2026,
  plan_a_run_id: 'run-a', plan_b_run_id: 'run-b',
} as WinnersLosersResponse;
const page: EmployeeImpactPage = {
  ...comparison, age_band: '25-34', tenure_band: '< 2', total: 1, offset: 0, limit: 25,
  total_increases: 5000, total_decreases: 0, net_contribution_change: 5000, average_change: 5000,
  employees: [{ employee_id: 'SYNTHETIC ID', age_band: '25-34', tenure_band: '< 2', plan_a_amount: 100, plan_b_amount: 5100, delta: 5000, status: 'winner' }],
};

describe('Winners & Losers employee impact', () => {
  it('formats positive, negative, neutral and sub-dollar amounts to cents', () => {
    expect(impactCurrency(5000)).toBe('$5,000.00');
    expect(impactCurrency(-1)).toBe('-$1.00');
    expect(impactCurrency(0)).toBe('$0.00');
    expect(impactCurrency(0.01)).toBe('$0.01');
  });

  it('preserves selected year, both runs, filters and pagination in detail requests', () => {
    const params = employeeImpactParams(comparison, { age_band: '25-34', tenure_band: '< 2' }, 25);
    expect(Object.fromEntries(params)).toEqual({ plan_a: 'a', plan_b: 'b', comparison_year: '2026', plan_a_run_id: 'run-a', plan_b_run_id: 'run-b', age_band: '25-34', tenure_band: '< 2', offset: '25', limit: '25' });
    expect(employeeImpactParams({ ...comparison, plan_a_run_id: null, plan_b_run_id: null }, {}).has('plan_a_run_id')).toBe(false);
  });

  it('requests a bounded page through the existing API client', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(page), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    try {
      expect(await getEmployeeImpacts('ws', comparison, { age_band: '25-34' }, 25)).toEqual(page);
      expect(fetch.mock.calls[0][0]).toContain('/api/workspaces/ws/analytics/winners-losers/employees?');
      expect(fetch.mock.calls[0][0]).toContain('offset=25');
      expect(fetch.mock.calls[0][0]).toContain('plan_b_run_id=run-b');
    } finally { vi.unstubAllGlobals(); }
  });

  it('renders dollar amounts and an encoded two-plan timeline link without identity fields', () => {
    const html = renderToStaticMarkup(<MemoryRouter><EmployeeImpactTable page={page} workspaceId="ws" /></MemoryRouter>);
    expect(html).toContain('$100.00');
    expect(html).toContain('$5,100.00');
    expect(html).toContain('$5,000.00');
    expect(html).toContain('/w/ws/timeline/a/SYNTHETIC%20ID?compare=b');
    expect(html).not.toMatch(/SSN|name=/);
  });

  it('makes bands accessible drilldown controls and states empty groups explicitly', () => {
    const html = renderToStaticMarkup(<BandImpactTable bands={[{ ...page, band_label: '25-34', winners: 1, losers: 0, neutral: 0 }]} onSelect={() => {}} />);
    expect(html).toContain('aria-label="View employees in 25-34"');
    expect(html).toContain('$5,000.00');
    expect(renderToStaticMarkup(<EmployeeImpactTable page={{ ...page, total: 0, employees: [] }} workspaceId="ws" />)).toContain('No compared employees');
  });
});
