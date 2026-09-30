import { describe, expect, it } from 'vitest';
import type { ContributionYearSummary } from '../services/api';
import {
  buildComparisonData, buildDCTrendData, buildEventComparisonData, buildScenarioColors, ComparisonScenario,
} from './scenarioComparisonData';

function scenario(id: string, name: string, headcount: number, hires: number): ComparisonScenario {
  return {
    scenario: { id, name },
    results: {
      workforce_progression: [{ simulation_year: 2025, headcount }],
      event_trends: { hire: [hires], termination: [hires + 1] },
    },
  };
}

describe('scenario comparison series identity', () => {
  it.each(['Baseline', 'year', 'bucket', 'name'])('keeps independent values for duplicate names: %s', name => {
    const scenarios = [scenario('a', name, 100, 10), scenario('b', name, 200, 20)];
    expect(buildComparisonData(scenarios).workforce).toEqual([
      { year: 2025, scenario_a: 100, scenario_b: 200 },
    ]);
    expect(buildEventComparisonData(scenarios).events).toEqual([
      { year: 2025, scenario_a_hire: 10, scenario_a_termination: 11, scenario_b_hire: 20, scenario_b_termination: 21 },
    ]);
    expect(buildScenarioColors(scenarios.map(d => d.scenario), index => ['green', 'blue'][index]))
      .toEqual({ a: 'green', b: 'blue' });
  });

  it('preserves series and color identity when names change', () => {
    const original = [scenario('a', 'Baseline', 100, 10), scenario('b', 'Baseline', 200, 20)];
    const renamed = original.map(d => ({ ...d, scenario: { ...d.scenario, name: 'year' } }));
    expect(buildComparisonData(renamed)).toEqual(buildComparisonData(original));
    expect(buildEventComparisonData(renamed)).toEqual(buildEventComparisonData(original));
    const colorAt = (index: number) => ['green', 'blue'][index];
    expect(buildScenarioColors(renamed.map(d => d.scenario), colorAt))
      .toEqual(buildScenarioColors(original.map(d => d.scenario), colorAt));
  });

  it('protects structural fields even when a scenario ID is year', () => {
    expect(buildComparisonData([scenario('year', 'year', 100, 10)]).workforce)
      .toEqual([{ year: 2025, scenario_year: 100 }]);
  });

  it('uses each scenario year index for events across different horizons', () => {
    const first = scenario('a', 'Baseline', 100, 10);
    const second = scenario('b', 'Baseline', 200, 20);
    second.results.workforce_progression[0].simulation_year = 2026;
    expect(buildEventComparisonData([second, first]).events).toEqual([
      { year: 2025, scenario_a_hire: 10, scenario_a_termination: 11 },
      { year: 2026, scenario_b_hire: 20, scenario_b_termination: 21 },
    ]);
  });
});

function yearSummary(deferral: number): ContributionYearSummary {
  return {
    year: 2025, average_deferral_rate: deferral, participation_rate: 80,
    employer_cost_rate: 4, employer_cost_pct_of_capped_compensation: 4,
    employee_contribution_rate: 6, match_contribution_rate: 3, core_contribution_rate: 1,
    total_contribution_rate: 10, participant_count: 80, total_eligible_count: 100,
    total_all_contributions: 1000, total_compensation: 10000, total_capped_compensation: 10000,
    total_employee_contributions: 600, total_employer_match: 300, total_employer_core: 100,
    total_employer_cost: 400,
  };
}

describe('DC plan trend series identity', () => {
  it('retains independent ID-based values and the year axis', () => {
    expect(buildDCTrendData([
      { scenario_id: 'a', contribution_by_year: [yearSummary(0.06)] },
      { scenario_id: 'year', contribution_by_year: [yearSummary(0.1)] },
    ], 'average_deferral_rate', 100)).toEqual([
      { year: 2025, scenario_a: 6, scenario_year: 10 },
    ]);
  });

  it('handles missing years and empty comparisons', () => {
    expect(buildDCTrendData([], 'participation_rate')).toEqual([]);
    expect(buildDCTrendData([
      { scenario_id: 'a', contribution_by_year: [] },
      { scenario_id: 'b', contribution_by_year: [yearSummary(0.06)] },
    ], 'participation_rate')).toEqual([{ year: 2025, scenario_b: 80 }]);
  });
});
