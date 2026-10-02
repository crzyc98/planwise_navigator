import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import ComplianceOverview from './ComplianceOverview';
import { ComplianceSummary, getComplianceEmployees } from '../services/api';

const summary: ComplianceSummary = {
  scenario_id: 's', scenario_name: 'Synthetic scenario', year: 2027, run_id: 'successful', evidence: 'e'.repeat(64),
  warning_threshold: 0.95, participant_count: 3,
  limits: { year: 2027, base_limit: 24000, catch_up_limit: 31500, super_catch_up_limit: 35250, compensation_limit: 355000, annual_additions_limit: 71000, catch_up_age_threshold: 50, super_catch_up_age_min: 60, super_catch_up_age_max: 63, is_estimated: true, differs_from_current_seed: true },
  deferrals: { below_threshold: 1, near_limit: 1, at_limit: 1, over_limit: 0, unavailable: 0, excess: 0 },
  annual_additions: { below_threshold: 3, near_limit: 0, at_limit: 0, over_limit: 0, unavailable: 0, excess: 0 },
  compensation: { below_threshold: 2, near_limit: 0, at_limit: 0, over_limit: 1, unavailable: 0, excess: 0.01 },
  catch_up: { eligible_count: 0, available_count: 0, utilizing_count: 0, capacity: 0, used: 0, remaining_capacity: 0, utilization: null },
  super_catch_up: { eligible_count: 1, available_count: 1, utilizing_count: 1, capacity: 11250, used: 500, remaining_capacity: 10750, utilization: 500 / 11250 },
  ndt: [{ test_type: 'adp', result: 'pass', margin: 0.01, message: null }], notes: ['Synthetic coverage note'],
};

describe('Compliance overview', () => {
  it('renders provenance, estimated limits, cap impact and catch-up coverage', () => {
    const html = renderToStaticMarkup(<ComplianceOverview workspaceId="w" summary={summary} onOpenTest={() => {}} />);
    expect(html).toContain('Estimated IRS limits');
    expect(html).toContain('Recorded limits differ from current seed');
    expect(html).toContain('successful');
    expect(html).toContain('Compensation above cap');
    expect(html).toContain('$0.01');
    expect(html).toContain('Remaining catch-up capacity');
    expect(html).toContain('Unavailable');
    expect(html).toContain('ADP: PASS');
    expect(html).not.toMatch(/SSN|first_name|last_name/);
  });

  it('does not label missing limits as confirmed or estimated', () => {
    const html = renderToStaticMarkup(<ComplianceOverview workspaceId="w" summary={{ ...summary, limits: null }} onOpenTest={() => {}} />);
    expect(html).toContain('IRS limits unavailable');
    expect(html).not.toContain('Estimated IRS limits');
  });

  it('pins employee requests to the summary evidence, year, threshold and filter', async () => {
    vi.stubGlobal('window', new EventTarget());
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ evidence: summary.evidence, total: 0, offset: 50, limit: 50, employees: [] }), { status: 200 })));
    try {
      await getComplianceEmployees('w', summary, '402g', 'near_limit', 50);
      const url = new URL(vi.mocked(fetch).mock.calls[0][0] as string, 'http://localhost');
      expect(Object.fromEntries(url.searchParams)).toEqual({ scenario_id: 's', year: '2027', evidence: summary.evidence, metric: '402g', offset: '50', limit: '50', warning_threshold: '0.95', limit_status: 'near_limit' });
    } finally { vi.unstubAllGlobals(); }
  });
});
