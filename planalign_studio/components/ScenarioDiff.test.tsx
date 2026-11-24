import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { ComparisonIntegrityResponse, ConfigDiffResponse, IntegrityReason } from '../services/api';
import { ComparisonIntegrityLines } from './ComparisonIntegrityBanner';
import { configDiffRows } from './configDiff';
import { ConfigDeltaRow, ProvenanceWarnings } from './ScenarioDiff';

function reason(overrides: Partial<IntegrityReason>): IntegrityReason {
  return {
    code: 'config_differs', effect: 'breaks', anchor_value: null, scenario_value: null,
    path: null, group: null, files: [], scenario_id: null, ...overrides,
  };
}

// The diff page's own check: census re-uploaded under the same name, seed
// tables changed and a different engine, with no setting differences.
const result: ComparisonIntegrityResponse = {
  anchor_scenario_id: 'a',
  anchor_scenario_name: 'Baseline',
  anchor_engine_version: '3.2.0',
  scenarios: [{
    scenario_id: 'b', scenario_name: 'Richer match', verdict: 'not_like_for_like',
    unevaluated: [], plan_design_differences: [], engine_version: '3.1.0',
    reasons: [
      reason({ code: 'census_differs', anchor_value: 'census.parquet', scenario_value: 'census.parquet' }),
      reason({ code: 'engine_version_differs', anchor_value: '3.2.0', scenario_value: '3.1.0' }),
      reason({ code: 'seed_files_differ', files: ['config_job_levels.csv'] }),
    ],
  }],
};

describe('Scenario Diff like-for-like check', () => {
  it('names census, seed-table and engine differences without linking to itself', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter><ComparisonIntegrityLines result={result} diffBase={null} /></MemoryRouter>,
    );
    expect(html).toContain('Richer match is not like-for-like with Baseline');
    expect(html).toContain('Census: same file name, different data');
    expect(html).toContain('Model seed tables differ: config_job_levels.csv');
    expect(html).toContain('Engine version: 3.2.0 vs 3.1.0');
    expect(html).not.toContain('See differences');
    expect(html).not.toContain('href=');
  });
});

describe('ProvenanceWarnings (shown only when the check fails)', () => {
  const configDiff = (overrides: Partial<ConfigDiffResponse>): ConfigDiffResponse => ({
    scenario_a: 'a', scenario_b: 'b', scenario_names: { a: 'Baseline', b: 'Richer match' },
    differences: [], unchanged_count: 0, seeds_match: true, drift_warning: false,
    provenance: {}, ...overrides,
  });
  const render = (diff: ConfigDiffResponse) =>
    renderToStaticMarkup(<ProvenanceWarnings configDiff={diff} scenarioA="a" scenarioB="b" />);

  it('keeps the seed, drift and missing-provenance warnings for that case', () => {
    expect(render(configDiff({ seeds_match: false }))).toContain('Seeds differ.');
    expect(render(configDiff({ drift_warning: true }))).toContain('Provenance warning.');
    const missing = { available: false, config_fingerprint: null, drift_reasons: [], drift_warning: false, random_seed: null, run_timestamp: null };
    expect(render(configDiff({ provenance: { a: missing } }))).toContain('Provenance unavailable.');
    expect(render(configDiff({}))).toBe('');
  });
});

describe('Scenario Diff configuration rows (#1236)', () => {
  const names = { a: 'Baseline', b: 'Richer match' };
  const render = (row: ReturnType<typeof configDiffRows>[number]) => renderToStaticMarkup(
    <table><tbody><ConfigDeltaRow row={row} names={names} locked={false} onApply={() => undefined} /></tbody></table>,
  );

  it('shows a collapsed mirror once, with both raw paths, percent values and copy buttons', () => {
    const [row] = configDiffRows([
      { path: 'compensation.cola_rate', a: 0.02, b: 0.03, status: 'changed' },
      { path: 'compensation.cola_rate_percent', a: 2, b: 3, status: 'changed' },
    ]);
    const html = render(row);
    expect(html).toContain('Cost-of-living raise');
    expect(html).toContain('<code class="block text-xs text-ink-muted">compensation.cola_rate</code>');
    expect(html).toContain('<code class="block text-xs text-ink-muted">compensation.cola_rate_percent</code>');
    expect(html).toContain('<div>2%</div>');
    expect(html).toContain('<div>3%</div>');
    expect(html).toContain('Use in Richer match');
  });

  it('still renders an object value', () => {
    const [row] = configDiffRows([
      { path: 'dc_plan.match_tiers', a: [{ match_rate: 0.5 }], b: [{ match_rate: 1 }], status: 'changed' },
    ]);
    expect(render(row)).toContain('[{&quot;match_rate&quot;:1}]');
  });
});
