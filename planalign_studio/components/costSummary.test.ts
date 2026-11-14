import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type {
  CostSummaryView,
  DCPlanAnalytics,
  EmployerCostOffsetRow,
  GrandfatheredCostComparisonResponse,
} from '../services/api';
import {
  ANCHOR_NOTE,
  buildCostSummary,
  costMatrixTSV,
  formatCurrency,
  formatPercent,
  formatSigned,
  toSummaryExportRequest,
  type CostSummaryInputs,
  type ScenarioSummary,
} from './costSummary';
import { CompensationMatrixTable, CostMatrixTable } from './CostSummaryTables';

// The same request the Python workbook test reads (tests/api/test_comparison_summary_export.py).
const FIXTURE = fileURLToPath(new URL('../../tests/api/snapshots/cost_summary_request.json', import.meta.url));

type Year = [year: number, match: number, core: number, compensation: number, capped: number];

function analytics(id: string, years: Year[]): DCPlanAnalytics {
  return {
    scenario_id: id,
    scenario_name: id,
    resolved_first_simulation_year: 2025,
    contribution_by_year: years.map(([year, match, core, compensation, capped]) => ({
      year,
      total_employer_match: match,
      total_employer_core: core,
      total_employer_cost: match + core,
      total_compensation: compensation,
      total_capped_compensation: capped,
    })),
  } as DCPlanAnalytics;
}

function offset(year: number, amount: number | null, allocation = 0): EmployerCostOffsetRow {
  return {
    simulation_year: year,
    source_year: amount === null ? null : year - 1,
    forfeitures_generated: amount,
    offset_amount: amount,
    participant_allocation: amount === null ? null : allocation,
    basis_available: amount !== null,
    unavailable_reason: amount === null ? 'No prior plan year within the simulation horizon.' : null,
  } as EmployerCostOffsetRow;
}

// Anchor "base" has every year; "rich" (new hires cohort) has no one in 2025.
const ANALYTICS = [
  analytics('base', [[2025, 80_000, 20_000, 2_000_000, 1_900_000], [2026, 90_000, 30_000, 2_100_000, 2_000_000],
    [2027, 100_000, 40_000, 2_200_000, 2_100_000]]),
  analytics('rich', [[2026, 150_000, 30_000, 2_100_000, 2_000_000], [2027, 160_000, 40_000, 2_250_000, 2_150_000]]),
];

const OFFSETS = new Map([
  ['base', new Map([[2025, offset(2025, null)], [2026, offset(2026, 4_000)], [2027, offset(2027, 5_000)]])],
  ['rich', new Map([[2025, offset(2025, null)], [2026, offset(2026, null)], [2027, offset(2027, 7_500)]])],
]);

const NET_INPUTS: CostSummaryInputs = {
  analytics: ANALYTICS,
  scenarioIds: ['base', 'rich'],
  anchorId: 'base',
  years: [2025, 2026, 2027],
  cohort: 'new_hires',
  grandfather: null,
  net: { offsets: OFFSETS, policyReducesCost: true },
  split: false,
};

const NET_VIEW: CostSummaryView = {
  anchor_scenario_id: 'base',
  cohort: 'new_hires',
  first_simulation_year: 2025,
  cost_view: 'net',
  breakdown: 'total',
  vesting_schedule: 'graded_5_year',
  forfeiture_policy: 'offset_employer_contributions',
  grandfather_cutoff_year: null,
};

const byId = (summary: ScenarioSummary[], id: string) => summary.find(item => item.scenario_id === id)!;

describe('cost summary derivation', () => {
  const summary = buildCostSummary(NET_INPUTS);
  const base = byId(summary, 'base');
  const rich = byId(summary, 'rich');

  it('derives totals, differences and rates once, for the page and the workbook', () => {
    expect(base.totals.employer_cost).toBe(360_000);
    expect(rich.totals.employer_cost).toBe(380_000);
    expect(rich.totals.employer_cost_vs_anchor).toBe(20_000);
    expect(base.totals.cost_pct_of_capped_pay).toBeCloseTo(360_000 / 6_000_000 * 100);
    expect(rich.totals.cost_pct_vs_anchor_pp).toBeCloseTo(380_000 / 4_150_000 * 100 - 6);
    expect(rich.years[1].employer_cost_vs_anchor).toBe(60_000);
    expect(rich.totals.total_compensation_vs_anchor).toBe(4_350_000 - 6_300_000);
  });

  it('nets offsets per year and keeps unmeasurable years gross in the horizon total', () => {
    expect(base.years[1].net_employer_cost).toBe(116_000);
    expect(base.totals.forfeiture_offset).toBe(9_000);
    expect(base.totals.net_employer_cost).toBe(351_000);
    expect(rich.totals.net_employer_cost).toBe(372_500);
    expect(rich.totals.net_employer_cost_vs_anchor).toBe(21_500);
  });

  it('leaves unavailable figures null with a reason, never zero', () => {
    const missing = rich.years[0];
    expect(missing.has_data).toBe(false);
    expect(missing.employer_cost).toBeNull();
    expect(missing.notes.employer_cost).toBe('No employees in cohort');
    expect(missing.employer_cost_vs_anchor).toBeNull();
    expect(rich.years[1].forfeiture_offset).toBeNull();
    expect(rich.years[1].notes.forfeiture_offset).toContain('No prior plan year');
    expect(rich.years[1].notes.net_employer_cost).toMatch(/^Gross only — /);
    expect(base.totals.employer_cost_vs_anchor).toBeNull();
    expect(base.totals.notes.employer_cost_vs_anchor).toBe(ANCHOR_NOTE);
  });

  it('marks grandfathered years unavailable, and the totals that depend on them', () => {
    const grandfather: GrandfatheredCostComparisonResponse = {
      baseline_scenario_id: 'base', cutoff_year: 2026, forfeiture_policy: 'offset_employer_contributions',
      warnings: [],
      scenarios: ['base', 'rich'].map(id => ({
        scenario_id: id, scenario_name: id, employer_cost_offsets: [],
        years: [2025, 2026, 2027].map(year => ({
          year, total_employer_cost: year === 2027 ? null : 1_000, baseline_cohort_cost: null,
          new_hire_cohort_cost: null, available: year !== 2027,
          unavailable_reason: year === 2027 ? 'Populations differ in 2027.' : null,
        })),
      })),
    };
    const result = buildCostSummary({
      ...NET_INPUTS, cohort: 'all', net: null,
      grandfather: { data: grandfather, loading: false, error: null },
    });
    const anchor = byId(result, 'base');
    expect(anchor.years[0].employer_cost).toBe(1_000);
    expect(anchor.years[2].employer_cost).toBeNull();
    expect(anchor.years[2].notes.employer_cost).toBe('Populations differ in 2027.');
    expect(anchor.totals.employer_cost).toBeNull();
    expect(anchor.totals.cost_pct_of_capped_pay).toBeNull();

    // Net subtracts the cohort-spliced offset from the grandfathered cost, not raw gross,
    // and an unavailable gross total leaves the net total unavailable too.
    const net = byId(buildCostSummary({
      ...NET_INPUTS, cohort: 'all', grandfather: { data: grandfather, loading: false, error: null },
    }), 'base');
    expect(net.years[1].net_employer_cost).toBe(1_000 - 4_000);
    expect(net.totals.net_employer_cost).toBeNull();
  });

  it('splits match and core only when the split is shown', () => {
    const split = byId(buildCostSummary({ ...NET_INPUTS, cohort: 'all', net: null, split: true }), 'rich');
    expect(split.years[1].employer_match).toBe(150_000);
    expect(split.totals.employer_core).toBe(70_000);
    expect(rich.totals.employer_match).toBeNull();
  });
});

describe('page tables render the summary figures', () => {
  const summary = buildCostSummary(NET_INPUTS);
  const names = { base: 'Baseline', rich: 'Rich match' };

  function cellTexts(markup: string): string[] {
    return [...markup.matchAll(/<td[^>]*>(.*?)<\/td>/g)].map(match => match[1].replace(/<[^>]+>/g, ''));
  }

  it('shows every cost-matrix figure as the summary has it', () => {
    const markup = renderToStaticMarkup(React.createElement(CostMatrixTable, {
      summary, years: NET_INPUTS.years, names, cohort: 'new_hires', netActive: true,
      policyReducesCost: true, grandfatherLoading: false,
    }));
    const cells = cellTexts(markup);
    const rich = byId(summary, 'rich');
    // Rows per scenario: gross, rate, offset, net — each name + 3 years + total + variance.
    const richGross = cells.slice(24, 30);
    expect(richGross).toEqual([
      'Rich match', '—', formatCurrency(180_000), formatCurrency(200_000),
      formatCurrency(rich.totals.employer_cost!), formatSigned(rich.totals.employer_cost_vs_anchor!),
    ]);
    expect(cells.slice(30, 36)).toEqual([
      'Employer cost / capped pay (all employees)', '—',
      formatPercent(rich.years[1].cost_pct_of_capped_pay!, 2), formatPercent(rich.years[2].cost_pct_of_capped_pay!, 2),
      formatPercent(rich.totals.cost_pct_of_capped_pay!, 2), `+${rich.totals.cost_pct_vs_anchor_pp!.toFixed(2)} pp`,
    ]);
    expect(cells.slice(36, 42)).toEqual(['Forfeiture offset', 'n/a', 'n/a', '-$7.5K', '-$7.5K', '--']);
    expect(cells.slice(42, 48)).toEqual([
      'Net employer cost', 'gross only', 'gross only', formatCurrency(192_500),
      formatCurrency(rich.totals.net_employer_cost!), formatSigned(rich.totals.net_employer_cost_vs_anchor!),
    ]);
  });

  it('shows the compensation figures as the summary has them', () => {
    const markup = renderToStaticMarkup(React.createElement(CompensationMatrixTable, {
      summary, years: NET_INPUTS.years, names,
    }));
    expect(cellTexts(markup).slice(6, 12)).toEqual([
      'Rich match', '-', '$2.10M', '$2.25M', '$4.35M', formatSigned(-1_950_000),
    ]);
  });

  it('copies the same figures to the clipboard', () => {
    const lines = costMatrixTSV(summary, NET_INPUTS.years, names, [], true).split('\n');
    expect(lines[5]).toBe(`Rich match\t-\t$180.0K\t$200.0K\t$380.0K\t+$20.0K`);
  });
});

describe('summary workbook request', () => {
  it('posts exactly the figures the page renders (shared with the Python workbook test)', () => {
    const request = toSummaryExportRequest(buildCostSummary(NET_INPUTS), NET_VIEW, { base: 'run-base', rich: 'run-rich' });
    if (process.env.UPDATE_COST_SUMMARY_FIXTURE) writeFileSync(FIXTURE, `${JSON.stringify(request, null, 2)}\n`);
    expect(request).toEqual(JSON.parse(readFileSync(FIXTURE, 'utf8')));
  });
});
