import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import {
  ComparisonIntegrityResponse,
  getComparisonIntegrity,
  IntegrityReason,
  ScenarioIntegrity,
} from '../services/api';
import { ComparisonIntegrityLines } from './ComparisonIntegrityBanner';
import { formatSetting, integrityRequest, planDesignSummary, summarizeIntegrity } from './comparisonIntegrity';

function reason(overrides: Partial<IntegrityReason>): IntegrityReason {
  return {
    code: 'config_differs', effect: 'breaks', anchor_value: null, scenario_value: null,
    path: null, group: null, files: [], scenario_id: null, ...overrides,
  };
}

function scenario(overrides: Partial<ScenarioIntegrity>): ScenarioIntegrity {
  return {
    scenario_id: 'b', scenario_name: 'Richer match', verdict: 'like_for_like', reasons: [],
    unevaluated: [], plan_design_differences: [], engine_version: '3.2.0', ...overrides,
  };
}

function response(scenarios: ScenarioIntegrity[]): ComparisonIntegrityResponse {
  return { anchor_scenario_id: 'a', anchor_scenario_name: 'Baseline', anchor_engine_version: '3.2.0', scenarios };
}

describe('like-for-like copy', () => {
  it('confirms a like-for-like scenario quietly and names what differs', () => {
    const [line] = summarizeIntegrity(response([scenario({
      plan_design_differences: [{ path: 'dc_plan.match_tiers', a: [], b: [], status: 'changed' }],
    })])).lines;
    expect(line.tone).toBe('ok');
    expect(line.headline).toBe('Richer match is like-for-like with Baseline. Only the employer match differs.');
    expect(line.details).toEqual([]);
  });

  it('names each breaking reason with both values', () => {
    const [line] = summarizeIntegrity(response([scenario({
      verdict: 'not_like_for_like',
      reasons: [
        reason({ code: 'seed_differs', anchor_value: 42, scenario_value: 7 }),
        reason({ code: 'census_differs', anchor_value: 'census_a.parquet', scenario_value: 'census_b.parquet' }),
        reason({ code: 'engine_version_differs', anchor_value: '3.2.0', scenario_value: '3.1.9' }),
        reason({ path: 'simulation.target_growth_rate', anchor_value: 0.03, scenario_value: 0.05, group: 'workforce_and_pay' }),
      ],
    })])).lines;
    expect(line.tone).toBe('warning');
    expect(line.headline).toContain('part of the difference is not the plan design');
    expect(line.details).toEqual([
      'Random seed: 42 vs 7',
      'Census: census_a.parquet vs census_b.parquet',
      'Engine version: 3.2.0 vs 3.1.9',
      'Headcount growth: 3% vs 5%',
    ]);
  });

  it('reads unknown as "can\'t tell" with the cause', () => {
    const [line] = summarizeIntegrity(response([scenario({
      verdict: 'unknown',
      unevaluated: [{ check: 'census', scenario_id: 'b', cause: 'not_recorded' }],
    })])).lines;
    expect(line.tone).toBe('unknown');
    expect(line.headline).toBe("Can't tell whether Richer match is like-for-like with Baseline: Richer match's run did not record its census.");
  });

  it('keeps notes separate and shows anchor notes once', () => {
    const summary = summarizeIntegrity(response([scenario({
      reasons: [
        reason({ code: 'edited_since_run', effect: 'note', scenario_id: 'a' }),
        reason({ code: 'edited_since_run', effect: 'note', scenario_id: 'b' }),
      ],
    })]));
    expect(summary.anchorNotes).toEqual(['Baseline was edited after its result ran. This compares the settings it ran with.']);
    expect(summary.lines[0].notes).toEqual(['Richer match was edited after its result ran. This compares the settings it ran with.']);
    expect(summary.lines[0].tone).toBe('ok');
  });

  it('lists a mixed-generation result as a reason, not a note', () => {
    const [line] = summarizeIntegrity(response([scenario({
      verdict: 'not_like_for_like',
      reasons: [reason({ code: 'mixed_generation', scenario_id: 'b' })],
    })])).lines;
    expect(line.tone).toBe('warning');
    expect(line.details).toEqual(["Richer match's result mixes rows from runs with different settings or seeds."]);
    expect(line.notes).toEqual([]);
  });

  it('names differing seed tables and engine builds', () => {
    const files = ['a.csv', 'b.csv', 'c.csv', 'd.csv', 'e.csv'];
    const [line] = summarizeIntegrity(response([scenario({
      verdict: 'not_like_for_like',
      reasons: [
        reason({ code: 'engine_build_differs', anchor_value: '1111111', scenario_value: '1111111 with local changes' }),
        reason({ code: 'seed_files_differ', files }),
        reason({ code: 'seed_files_differ', files: ['x.csv'] }),
        reason({ code: 'seed_files_differ' }),
      ],
    })])).lines;
    expect(line.details).toEqual([
      'Engine build differs: 1111111 vs 1111111 with local changes',
      'Model seed tables differ: a.csv, b.csv, c.csv and 2 more',
      'Model seed tables differ: x.csv',
      'Model seed tables differ',
    ]);
  });

  it('only says "same file name" when both census names are known and equal', () => {
    const census = (anchor_value: string | null, scenario_value: string | null) => summarizeIntegrity(response([scenario({
      verdict: 'not_like_for_like',
      reasons: [reason({ code: 'census_differs', anchor_value, scenario_value })],
    })])).lines[0].details;
    expect(census('census.parquet', 'census.parquet')).toEqual(['Census: same file name, different data']);
    expect(census('census.parquet', null)).toEqual(['Census data differs']);
    expect(census(null, null)).toEqual(['Census data differs']);
  });

  it('shows a mirrored setting once, before capping, with the same text', () => {
    const reasons = [
      reason({ path: 'compensation.cola_rate', anchor_value: 0.02, scenario_value: 0.03 }),
      reason({ path: 'compensation.cola_rate_percent', anchor_value: 2, scenario_value: 3 }),
      reason({ path: 'compensation.merit_budget', anchor_value: 0.035, scenario_value: 0.04 }),
      reason({ path: 'compensation.merit_budget_percent', anchor_value: 3.5, scenario_value: 4 }),
      reason({ path: 'dc_plan.deferral_match_response.enabled', anchor_value: false, scenario_value: true }),
      reason({ path: 'deferral_match_response.enabled', anchor_value: false, scenario_value: true }),
      reason({ path: 'workforce.total_termination_rate', anchor_value: 0.12, scenario_value: 0.15 }),
      reason({ path: 'workforce.new_hire_termination_rate', anchor_value: 0.25, scenario_value: 0.3 }),
      reason({ path: 'workforce.knob', anchor_value: 1, scenario_value: 2 }),
    ];
    const [line] = summarizeIntegrity(response([scenario({ verdict: 'not_like_for_like', reasons })])).lines;
    expect(line.details).toEqual([
      'Cost-of-living raise: 2% vs 3%',
      'Merit budget: 3.5% vs 4%',
      'Deferral match response enabled: off vs on',
      'Turnover: 12% vs 15%',
      'and 2 more settings',
    ]);
    expect(new Set(line.details).size).toBe(line.details.length);
  });

  it('notes a scenario whose assumptions changed since its previous run', () => {
    const summary = summarizeIntegrity(response([scenario({
      reasons: [
        reason({ code: 'changed_since_previous_run', effect: 'note', scenario_id: 'a' }),
        reason({ code: 'changed_since_previous_run', effect: 'note', scenario_id: 'b' }),
      ],
    })]));
    expect(summary.anchorNotes).toEqual(["Baseline's assumptions or inputs changed since its previous run."]);
    expect(summary.lines[0].notes).toEqual(["Richer match's assumptions or inputs changed since its previous run."]);
    expect(summary.lines[0].tone).toBe('ok');
  });

  it('says once when every result ran on the same engine version', () => {
    expect(summarizeIntegrity(response([scenario({}), scenario({ scenario_id: 'c' })])).versionNote)
      .toBe('All results ran on engine version 3.2.0.');
  });

  it('makes no shared-version claim when versions differ or one is unknown', () => {
    expect(summarizeIntegrity(response([scenario({ engine_version: '3.1.0' })])).versionNote).toBeNull();
    expect(summarizeIntegrity(response([scenario({ engine_version: null })])).versionNote).toBeNull();
    expect(summarizeIntegrity({ ...response([scenario({})]), anchor_engine_version: null }).versionNote).toBeNull();
  });

  it('caps long setting lists', () => {
    const reasons = Array.from({ length: 6 }, (_, index) => reason({ path: `workforce.knob_${index}`, anchor_value: index, scenario_value: index + 1 }));
    const [line] = summarizeIntegrity(response([scenario({ verdict: 'not_like_for_like', reasons })])).lines;
    expect(line.details).toHaveLength(5);
    expect(line.details.at(-1)).toBe('and 2 more settings');
  });

  it('formats settings in plain words', () => {
    expect(formatSetting('compensation.merit_budget_percent', 3.5)).toBe('3.5%');
    expect(formatSetting('dc_plan.max_voluntary_deferral_percent', 0.75)).toBe('75%');
    expect(formatSetting('dc_plan.match_cap_percent', 0.06)).toBe('6%');
    expect(formatSetting('workforce.total_termination_rate', 0.12)).toBe('12%');
    expect(formatSetting('dc_plan.auto_enroll', true)).toBe('on');
    expect(formatSetting('new_hire.age_distribution', [{ age: 25 }])).toBeNull();
    expect(planDesignSummary([])).toBe('No settings differ.');
    expect(planDesignSummary([
      { path: 'dc_plan.core_contribution_rate_percent', a: 2, b: 3, status: 'changed' },
      { path: 'dc_plan.escalation_cap_percent', a: 6, b: 10, status: 'changed' },
    ])).toBe('Only the employer core contribution and auto-escalation differ.');
  });
});

describe('ComparisonIntegrityLines', () => {
  it('links each line to the workspace-scoped two-scenario diff', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ComparisonIntegrityLines diffBase="/w/ws" result={response([scenario({})])} />
      </MemoryRouter>,
    );
    expect(html).toContain('href="/w/ws/analytics/diff?a=a&amp;b=b"');
    expect(html).toContain('Richer match is like-for-like with Baseline.');
    expect(html).toContain('All results ran on engine version 3.2.0.');
    expect(html).not.toMatch(/provenance|fingerprint/i);
  });
});

describe('integrityRequest', () => {
  it('asks the same question for the same scenarios on every page', () => {
    // Cost Comparison: selection plus its chosen anchor.
    const cost = integrityRequest('ws', ['b', 'a'], 'a');
    // Winners & Losers: Plan A is the reference.
    const winnersLosers = integrityRequest('ws', ['a', 'b'], 'a');
    // DC Plan comparison: the first column is the reference.
    const dcPlan = integrityRequest('ws', ['a', 'b'], 'a');
    expect(cost).toEqual(winnersLosers);
    expect(dcPlan).toEqual(winnersLosers);
    expect(cost?.scenarioIds).toEqual(['a', 'b']);
  });

  it('refetches when the anchor changes and skips single selections', () => {
    expect(integrityRequest('ws', ['a', 'b'], 'a')?.key).not.toBe(integrityRequest('ws', ['a', 'b'], 'b')?.key);
    expect(integrityRequest('ws', ['a'], 'a')).toBeNull();
    expect(integrityRequest(undefined, ['a', 'b'], 'a')).toBeNull();
    expect(integrityRequest('ws', ['a', 'b'], '')).toBeNull();
  });

  it('asks nothing when the anchor is not among the compared scenarios', () => {
    expect(integrityRequest('ws', ['a', 'b'], 'z')).toBeNull();
  });
});

describe('getComparisonIntegrity', () => {
  it('requests the selection and the anchor', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(response([])), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    vi.stubGlobal('window', { dispatchEvent: vi.fn() });
    try {
      await getComparisonIntegrity('ws', ['a', 'b'], 'b');
      expect(fetch.mock.calls[0][0]).toContain('/api/workspaces/ws/analytics/compare/integrity?scenarios=a%2Cb&anchor=b');
    } finally { vi.unstubAllGlobals(); }
  });
});
