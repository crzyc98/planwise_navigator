import { buildHeadcountComparison } from './headcountComparison';
import type { ContributionYearSummary, DCPlanAnalytics, Scenario, SimulationResults } from '../services/api';

export interface ComparisonScenario {
  scenario: Pick<Scenario, 'id' | 'name'>;
  results: {
    workforce_progression: Array<Pick<SimulationResults['workforce_progression'][number], 'simulation_year' | 'headcount'>>;
    event_trends: SimulationResults['event_trends'];
  };
}

// Prefix IDs so series can never replace structural fields such as year or bucket.
export const scenarioSeriesKey = (id: string): string => `scenario_${id}`;
export const eventSeriesKey = (id: string, event: string): string =>
  `${scenarioSeriesKey(id)}_${event}`;

export function buildScenarioColors(
  scenarios: Array<{ id: string }>, colorAt: (index: number) => string
): Record<string, string> {
  return Object.fromEntries(scenarios.map((scenario, index) => [scenario.id, colorAt(index)]));
}

export function buildDCTrendData(
  analytics: Array<Pick<DCPlanAnalytics, 'scenario_id' | 'contribution_by_year'>>,
  metricKey: keyof ContributionYearSummary,
  multiplier: number = 1,
): Array<{ year: number; [key: string]: number }> {
  const years = [...new Set(analytics.flatMap(a =>
    (a.contribution_by_year ?? []).map(c => c.year)
  ))].sort((a, b) => a - b);

  return years.map(year => {
    const point: { year: number; [key: string]: number } = { year };
    analytics.forEach(a => {
      const yearData = a.contribution_by_year?.find(c => c.year === year);
      if (yearData) {
        point[scenarioSeriesKey(a.scenario_id)] = yearData[metricKey] * multiplier;
      }
    });
    return point;
  });
}

export function buildEventComparisonData(scenarios: ComparisonScenario[]) {
  const years = [...new Set(scenarios.flatMap(d =>
    d.results.workforce_progression.map(r => r.simulation_year)
  ))].sort((a, b) => a - b);

  const events = years.map(year => {
    const point: Record<string, number> = { year };
    scenarios.forEach(({ scenario, results }) => {
      const index = results.workforce_progression.findIndex(r => r.simulation_year === year);
      if (index >= 0 && results.event_trends) {
        point[eventSeriesKey(scenario.id, 'hire')] = results.event_trends.hire?.[index] || 0;
        point[eventSeriesKey(scenario.id, 'termination')] = results.event_trends.termination?.[index] || 0;
      }
    });
    return point;
  });

  return { events };
}

export function buildComparisonData(scenarios: ComparisonScenario[]) {
  return { ...buildHeadcountComparison(scenarios), ...buildEventComparisonData(scenarios) };
}
