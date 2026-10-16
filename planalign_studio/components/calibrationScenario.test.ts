import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { baselineScenarioId } from './calibrationScenario';
import CalibrationPanel from './CalibrationPanel';

vi.mock('react-router-dom', () => ({ useOutletContext: () => ({
  activeWorkspace: { id: 'workspace', name: 'Synthetic workspace', base_config: {} },
}) }));
vi.mock('../hooks/useChartTheme', () => ({ useChartTheme: () => ({}) }));
vi.mock('./config/ConfigContext', () => ({ extractCensusPath: () => null }));

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
});
