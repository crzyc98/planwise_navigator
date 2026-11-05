import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { baselineScenarioId, growthMetricSettings, isMissingRunError } from './calibrationScenario';
import { ApiError } from '../services/api';
import CalibrationPanel from './CalibrationPanel';

vi.mock('react-router-dom', () => ({ useOutletContext: () => ({
  activeWorkspace: { id: 'workspace', name: 'Synthetic workspace', base_config: {} },
}) }));
vi.mock('../hooks/useChartTheme', () => ({ useChartTheme: () => ({}) }));
vi.mock('./config/ConfigContext', () => ({ extractCensusPath: () => null }));

describe('growth metric settings', () => {
  it('leaves the active metric request unchanged', () => {
    expect(growthMetricSettings('active_average', true)).toEqual({});
  });

  it('sends the validated band and cap with two-dial total pay per head', () => {
    expect(growthMetricSettings('payroll_per_head', true)).toEqual({
      growth_metric: 'payroll_per_head',
      compound_band_pct: 0.04,
      salary_growth_max: 0.05,
      stop_on_plateau: true,
    });
  });

  it('sends only the metric when starting-pay growth is not solved', () => {
    expect(growthMetricSettings('payroll_per_head', false)).toEqual({
      growth_metric: 'payroll_per_head',
    });
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
