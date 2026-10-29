import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Section401a4Summary, Section401a4ComparisonResults } from './NDTTesting';
import type { Section401a4ScenarioResult } from '../services/api';

const base: Section401a4ScenarioResult = {
  plan_design_id: null, employees: null, service_risk_detail: null, scenario_id: 's', scenario_name: 'Synthetic', simulation_year: 2025,
  test_result: 'unavailable', heuristic_result: 'pass', test_message: 'Rate-group coverage not evaluated.',
  hce_count: 1, nhce_count: 4, hce_average_rate: .1, nhce_average_rate: .07,
  hce_median_rate: .1, nhce_median_rate: .09, ratio: .6999999999999998,
  applied_test: 'general', margin: .2, ratio_test_threshold: .7,
  include_match: false, service_risk_flag: false, excluded_count: 0, hce_threshold_used: 155000,
};

describe('401a4 evidence presentation', () => {
  for (const heuristic of ['pass', 'fail', null]) {
    for (const comparison of [false, true]) {
      it(`renders neutral unavailable: heuristic=${heuristic}, comparison=${comparison}`, () => {
        const result = { ...base, heuristic_result: heuristic };
        const html = renderToStaticMarkup(comparison
          ? <Section401a4ComparisonResults results={[result]} scenarioOrder={['s']} />
          : <Section401a4Summary result={result} />);
        expect(html).toContain('Determination unavailable');
        expect(html).toContain('Rate-group coverage not evaluated.');
        expect(html).not.toMatch(/PASS|FAIL|success|danger|check-circle/);
        if (heuristic === null) {
          expect(html).toContain('Rate comparison unavailable');
          expect(html).not.toContain('Average-rate ratio (rounded)');
        } else {
          expect(html).toContain('Average-rate ratio (rounded)');
          expect(html).toContain('70.00%');
        }
      });
    }
  }
  it('keeps execution errors distinct', () => {
    const html = renderToStaticMarkup(<Section401a4Summary result={{...base, test_result: 'error', test_message: 'Missing database'}} />);
    expect(html).toContain('Execution error');
    expect(html).toContain('Missing database');
    expect(html).not.toContain('Average-rate ratio');
  });
});
