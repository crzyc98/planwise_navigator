import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { getScenarioRunChanges, RunChange, RunChangesResponse } from '../services/api';
import { RunChangesLines } from './RunChangesSince';
import { summarizeRunChanges } from './comparisonIntegrity';

const PREVIOUS_AT = '2026-11-13T09:00:00-05:00';
const DATE = new Date(PREVIOUS_AT).toLocaleDateString();

function change(overrides: Partial<RunChange>): RunChange {
  return { code: 'config_differs', path: null, group: null, previous_value: null, current_value: null, ...overrides };
}

function response(overrides: Partial<RunChangesResponse>): RunChangesResponse {
  return {
    scenario_id: 'a', scenario_name: 'Baseline', has_previous_run: true, previous_run_id: 'r1',
    previous_run_at: PREVIOUS_AT, changes: [], unevaluated: [], ...overrides,
  };
}

describe('summarizeRunChanges', () => {
  it('names each change with both values, previous first', () => {
    const summary = summarizeRunChanges(response({
      changes: [
        change({ code: 'engine_version_differs', previous_value: '3.1.0', current_value: '3.2.0' }),
        change({ code: 'census_differs', previous_value: 'a.parquet', current_value: 'b.parquet' }),
        change({ path: 'workforce.total_termination_rate', group: 'workforce_and_pay', previous_value: 0.12, current_value: 0.15 }),
        change({ path: 'dc_plan.match_cap_percent', group: 'plan_design', previous_value: 4, current_value: 6 }),
      ],
    }));
    expect(summary.headline).toBe(`Since the previous run (${DATE}):`);
    expect(summary.changes).toEqual([
      'Engine version: 3.1.0 → 3.2.0',
      'Census: a.parquet → b.parquet',
      'Turnover: 12% → 15%',
      'Match cap percent: 4% → 6%',
    ]);
  });

  it('says when nothing changed, and when there is no previous run', () => {
    expect(summarizeRunChanges(response({})).headline).toBe(`Same settings as the previous run (${DATE}).`);
    expect(summarizeRunChanges(response({ has_previous_run: false, previous_run_at: null })).headline)
      .toBe('No previous run to compare.');
  });

  it("doesn't claim nothing changed when a run didn't record something", () => {
    const summary = summarizeRunChanges(response({ unevaluated: ['census', 'engine_version'] }));
    expect(summary.headline).not.toContain('Same settings');
    expect(summary.missing).toBe("Couldn't compare the census and engine version: one of the runs didn't record it.");
  });

  it('caps a long change list', () => {
    const changes = Array.from({ length: 10 }, (_, index) => change({ path: `dc_plan.knob_${index}`, previous_value: index, current_value: index + 1 }));
    const summary = summarizeRunChanges(response({ changes }));
    expect(summary.changes).toHaveLength(9);
    expect(summary.changes.at(-1)).toBe('and 2 more settings');
  });
});

describe('RunChangesLines', () => {
  it('renders plain words only', () => {
    const html = renderToStaticMarkup(<RunChangesLines result={response({
      changes: [change({ code: 'seed_differs', previous_value: 42, current_value: 7 })],
    })} />);
    expect(html).toContain('Random seed: 42 → 7');
    expect(html).not.toMatch(/provenance|fingerprint|manifest/i);
  });
});

describe('getScenarioRunChanges', () => {
  it('requests one scenario', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(response({})), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    vi.stubGlobal('window', { dispatchEvent: vi.fn() });
    try {
      await getScenarioRunChanges('ws', 'a');
      expect(fetch.mock.calls[0][0]).toContain('/api/workspaces/ws/scenarios/a/run-changes');
    } finally { vi.unstubAllGlobals(); }
  });
});
