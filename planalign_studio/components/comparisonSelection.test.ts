import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { listScenarios, Scenario } from '../services/api';
import { hasComparisonResult, loadDiffSelection, restoreComparisonSelection } from './comparisonSelection';
import SelectedComparisonRuns from './SelectedComparisonRuns';

vi.mock('../services/api', () => ({ listScenarios: vi.fn() }));

function scenario(id: string, status: Scenario['status'], available = true): Scenario {
  return {
    id, status, name: id, workspace_id: 'workspace', config_overrides: {},
    description: null, last_run_at: null, provenance: null, results_summary: null,
    created_at: '2026-09-29', has_selected_result: available,
    last_run_id: 'latest-attempt', selected_result_run_id: available ? `success-${id}` : null,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('comparison selection using retained successful results', () => {
  it.each(['completed', 'running', 'failed', 'cancelled'] as const)(
    'restores URL selections and accepts direct diff inputs during a %s attempt', async status => {
      const retained = scenario('retained', status);
      const baseline = scenario('baseline', 'completed');
      const scenarios = [baseline, retained, scenario('no-success', status, false)];
      expect(restoreComparisonSelection(scenarios, 'retained', 'baseline')).toEqual(['retained', 'baseline']);
      expect(scenarios.filter(hasComparisonResult)).toEqual([baseline, retained]);
      vi.mocked(listScenarios).mockResolvedValue(scenarios);
      expect(await loadDiffSelection('workspace', 'retained', 'baseline')).toEqual([retained, baseline]);
      expect(listScenarios).toHaveBeenCalledWith('workspace');
    },
  );

  it('rejects missing results even when an attempt ID and completed status exist', async () => {
    const scenarios = [scenario('baseline', 'completed'), scenario('empty', 'completed', false)];
    expect(restoreComparisonSelection(scenarios, 'empty', 'baseline')).toEqual(['baseline', '']);
    vi.mocked(listScenarios).mockResolvedValue(scenarios);
    await expect(loadDiffSelection('workspace', 'baseline', 'empty')).rejects.toThrow('successful results');
    await expect(loadDiffSelection('workspace', 'baseline', 'outside')).rejects.toThrow('active workspace');
  });

  it('defaults to retained baseline results and clears unavailable selections', () => {
    expect(restoreComparisonSelection([scenario('other', 'cancelled'), scenario('baseline', 'failed')], null, null))
      .toEqual(['baseline', 'other']);
    expect(restoreComparisonSelection([], 'old-a', 'old-b')).toEqual(['', '']);
  });

  it('shows the selected run identity separately from the latest attempt', () => {
    const html = renderToStaticMarkup(React.createElement(SelectedComparisonRuns, {
      scenarios: [scenario('baseline', 'running')],
    }));
    expect(html).toContain('success-baseline');
    expect(html).toContain('Latest attempt: running');
    expect(html).not.toContain('latest-attempt');
  });
});
