import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { baselineScenarioId, costSummary, growthMetricSettings, isMissingRunError, searchLimitNotes } from './calibrationScenario';
import { ApiError } from '../services/api';
import CalibrationPanel from './CalibrationPanel';

vi.mock('react-router-dom', () => ({ useOutletContext: () => ({
  activeWorkspace: { id: 'workspace', name: 'Synthetic workspace', base_config: {} },
}) }));
vi.mock('../hooks/useChartTheme', () => ({ useChartTheme: () => ({}) }));
vi.mock('./config/ConfigContext', () => ({ extractCensusPath: () => null }));

describe('growth metric settings', () => {
  it('leaves the active metric request unchanged without a budget', () => {
    expect(growthMetricSettings('active_average', true)).toEqual({});
  });

  it('sets the raise budget from the target under the active metric too', () => {
    expect(growthMetricSettings('active_average', true, true)).toEqual({ solve_raise_budget: true });
    expect(growthMetricSettings('active_average', false, true)).toEqual({});
  });

  it('sends the validated band with two-dial total pay per head and leaves limits to the analyst', () => {
    expect(growthMetricSettings('payroll_per_head', true)).toEqual({
      growth_metric: 'payroll_per_head',
      compound_band_pct: 0.04,
      stop_on_plateau: true,
      solve_raise_budget: false,
    });
  });

  it('sets the raise budget from the target only when asked', () => {
    expect(growthMetricSettings('payroll_per_head', true, true)).toMatchObject({
      solve_raise_budget: true,
    });
    expect(growthMetricSettings('payroll_per_head', false, true)).toEqual({
      growth_metric: 'payroll_per_head',
    });
  });

  it('sends only the metric when starting-pay growth is not solved', () => {
    expect(growthMetricSettings('payroll_per_head', false)).toEqual({
      growth_metric: 'payroll_per_head',
    });
  });
});

describe('search limit notes', () => {
  const limits = { scaleMax: 3, salaryGrowthMaxPct: 8 };

  it('stays quiet when no dial reached a limit', () => {
    expect(searchLimitNotes(1.4, 0.05, limits)).toEqual([]);
    expect(searchLimitNotes(null, undefined, limits)).toEqual([]);
  });

  it('names each dial that finished at its limit', () => {
    expect(searchLimitNotes(3, 0.08, limits)).toEqual([
      'New-hire scale ended at its 3.00× limit.',
      'Starting-pay growth ended at its 8.0%/yr limit.',
    ]);
  });
});

describe('cost summary', () => {
  const row = (year: number, pay: number, cost: number) => ({
    simulation_year: year,
    current_total_pay: pay,
    solved_total_pay: pay * 0.9,
    current_employer_cost: cost,
    estimated_employer_cost: cost * 0.9,
  });

  it('shows nothing when no estimate is available', () => {
    expect(costSummary([])).toBeNull();
  });

  it('reports the final year and the whole horizon', () => {
    const summary = costSummary([row(2027, 200, 20), row(2026, 100, 10)]);
    expect(summary).toMatchObject({ firstYear: 2026, lastYear: 2027, pay: [200, 180], cost: [20, 18] });
    expect(summary?.horizonCost[0]).toBeCloseTo(30);
    expect(summary?.horizonCost[1]).toBeCloseTo(27);
  });
});

describe('calibration scenario defaults', () => {
  it('selects the real Baseline ID even when another scenario is first', () => {
    expect(baselineScenarioId([
      { id: 'other', name: 'Core_3pc' }, { id: 'baseline-id', name: 'Baseline' },
    ])).toBe('baseline-id');
  });

  it('accepts case and surrounding whitespace but prefers the exact name', () => {
    const alternate = { id: 'alternate', name: ' baseline ' };
    expect(baselineScenarioId([alternate])).toBe('alternate');
    expect(baselineScenarioId([alternate, { id: 'exact', name: 'Baseline' }])).toBe('exact');
  });

  it('requires a selection when no Baseline exists rather than guessing', () => {
    expect(baselineScenarioId([])).toBeNull();
    expect(baselineScenarioId([{ id: 'other', name: 'Baseline 2027' }])).toBeNull();
  });

  it('renders a non-runnable placeholder while scenarios and settings load', () => {
    const html = renderToStaticMarkup(createElement(CalibrationPanel));
    expect(html).toContain('Select a scenario');
    expect(html).not.toContain('Workspace baseline');
    expect(html).toMatch(/<option[^>]*disabled=""[^>]*>Select a scenario<\/option>/);
    expect(html).toContain('Start new-hire scale at');
    expect(html).toContain('New-hire scale limit');
    expect(html).toContain('Starting-pay growth limit');
    const runButton = html.match(/<button\b[^>]*>.*?<\/button>/g)
      ?.find(button => button.includes('Auto-Calibrate'));
    expect(runButton).toContain('disabled=""');
  });

  it('recognizes only the no-matching-run 409 as offering a scenario run', () => {
    const detail = 'No completed simulation matches this workspace census, target config, seed, and horizon.';
    expect(isMissingRunError(new ApiError(409, 'Conflict', detail))).toBe(true);
    expect(isMissingRunError(new ApiError(409, 'Conflict', 'The target workspace census is missing.'))).toBe(false);
    expect(isMissingRunError(new ApiError(422, 'Unprocessable', detail))).toBe(false);
    expect(isMissingRunError(new Error(detail))).toBe(false);
  });
});
