import { describe, expect, it } from 'vitest';
import type { DCPlanAnalytics } from '../services/api';
import { buildCostSummary, costMatrixTSV, cumulativeCostRows, type CostSummaryInputs } from './costSummary';
import {
  UNAVAILABLE_YEAR_NOTE,
  effectiveYearBlockedReason,
  effectiveYearOptions,
  restoreEffectiveYear,
  unavailableYears,
} from './effectiveYear';

type Year = [year: number, match: number, core: number];

function analytics(id: string, years: Year[], sources: DCPlanAnalytics['year_sources'] = []): DCPlanAnalytics {
  return {
    scenario_id: id,
    scenario_name: id,
    resolved_first_simulation_year: 2025,
    contribution_by_year: years.map(([year, match, core]) => ({
      year,
      total_employer_match: match,
      total_employer_core: core,
      total_employer_cost: match + core,
      total_compensation: 100_000,
      total_capped_compensation: 100_000,
    })),
    year_sources: sources,
  } as DCPlanAnalytics;
}

function source(year: number, scenarioId: string, available = true) {
  return { year, scenario_id: scenarioId, run_id: `run-${scenarioId}`, available };
}

// What the API returns for effective year 2026: "rich" shows the anchor's 2025.
const BASE = analytics('base', [[2025, 1000, 500], [2026, 1100, 500], [2027, 1200, 500]]);
const COMBINED = analytics('rich', [[2025, 1000, 500], [2026, 2200, 500], [2027, 2400, 500]],
  [source(2025, 'base'), source(2026, 'rich'), source(2027, 'rich')]);
// A run one year shorter than the anchor: 2027 has no result.
const SHORT = analytics('short', [[2025, 1000, 500], [2026, 4400, 500]],
  [source(2025, 'base'), source(2026, 'short'), source(2027, 'short', false)]);

function inputs(scenarios: DCPlanAnalytics[], split = false): CostSummaryInputs {
  return {
    analytics: [BASE, ...scenarios],
    scenarioIds: ['base', ...scenarios.map(item => item.scenario_id)],
    anchorId: 'base',
    years: [2025, 2026, 2027],
    cohort: 'all',
    grandfather: null,
    net: null,
    split,
  };
}

describe('effective year rules', () => {
  it('offers every year from the first simulation year to the last', () => {
    expect(effectiveYearOptions(2025, [2025, 2026, 2027])).toEqual([2025, 2026, 2027]);
    expect(effectiveYearOptions(undefined, [2025])).toEqual([]);
  });

  it('restores only a whole stored year; anything else is the first year', () => {
    expect(restoreEffectiveYear(2027)).toBe(2027);
    expect(restoreEffectiveYear('2027')).toBeNull();
    expect(restoreEffectiveYear(undefined)).toBeNull();
  });

  it('is blocked by grandfathering and by net of forfeitures', () => {
    expect(effectiveYearBlockedReason(false, 'gross')).toBeNull();
    expect(effectiveYearBlockedReason(true, 'gross')).toMatch(/grandfathering/);
    expect(effectiveYearBlockedReason(false, 'net')).toMatch(/net of forfeitures/);
  });

  it('reads the years a combined series cannot show', () => {
    expect(unavailableYears(SHORT)).toEqual(new Set([2027]));
    expect(unavailableYears(BASE)).toEqual(new Set());
  });
});

describe('cost tables on a combined series', () => {
  it('shows the anchor before the effective year and the scenario from it on', () => {
    const [, rich] = buildCostSummary(inputs([COMBINED]));

    expect(rich.years.map(year => year.employer_cost)).toEqual([1500, 2700, 2900]);
    expect(rich.years.map(year => year.employer_cost_vs_anchor)).toEqual([0, 1100, 1200]);
    expect(rich.totals.employer_cost).toBe(7100);
    expect(rich.totals.employer_cost_vs_anchor).toBe(7100 - 4800);
  });

  it('keeps a year with no result unavailable, and every total that needs it', () => {
    const [, short] = buildCostSummary(inputs([SHORT], true));
    const missing = short.years[2];

    expect(missing.has_data).toBe(true);
    expect(missing.employer_cost).toBeNull();
    expect(missing.notes.employer_cost).toBe(UNAVAILABLE_YEAR_NOTE);
    expect(short.totals.employer_cost).toBeNull();
    expect(short.totals.total_compensation).toBeNull();
    expect(short.totals.employer_match).toBeNull();
    expect(short.totals.employer_core).toBeNull();
    const line = costMatrixTSV(buildCostSummary(inputs([SHORT])), [2025, 2026, 2027], { short: 'Short' }, [], false)
      .split('\n').find(text => text.startsWith('Short\t'));
    expect(line).toBe('Short\t$1.5K\t$4.9K\tunavailable\tunavailable\t--');
  });

  it('accumulates the combined years and stops at an unavailable one', () => {
    const rows = [
      { year: 2025, base: 1500, rich: 1500, short: 1500 },
      { year: 2026, base: 1600, rich: 2700, short: 4900 },
      { year: 2027, base: 1700, rich: 2900, short: null },
    ];

    const cumulative = cumulativeCostRows(rows, ['base', 'rich', 'short'], 'base');

    expect(cumulative.map(row => row.rich)).toEqual([1500, 4200, 7100]);
    expect(cumulative.map(row => row.rich_delta)).toEqual([0, 1100, 2300]);
    expect(cumulative.map(row => row.short)).toEqual([1500, 6400, null]);
    expect(cumulative[2].short_delta).toBeNull();
  });
});
