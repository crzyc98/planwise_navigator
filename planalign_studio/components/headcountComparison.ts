import type { SimulationResults } from '../services/api';

interface HeadcountScenario {
  scenario: { id: string; name: string };
  results: {
    workforce_progression: Array<Pick<SimulationResults['workforce_progression'][number], 'simulation_year' | 'headcount'>>;
  };
}

export function buildHeadcountComparison(scenarios: HeadcountScenario[]) {
  const observations = scenarios.map(({ results }) => new Map(
    results.workforce_progression.map(row => [row.simulation_year, row.headcount]),
  ));
  const observedYears = observations.flatMap(rows => Array.from(rows.keys()));
  if (observedYears.length === 0) {
    return { workforce: [], hasMissingYears: false, commonYearCount: 0 };
  }

  // Include interior years even when every scenario lacks an observation.
  const firstYear = Math.min(...observedYears);
  const lastYear = Math.max(...observedYears);
  const years = Array.from({ length: lastYear - firstYear + 1 }, (_, index) => firstYear + index);
  const workforce = years.map(year => {
    const point: Record<string, number | null> = { year };
    scenarios.forEach(({ scenario }, index) => {
      point[`scenario_${scenario.id}`] = observations[index].get(year) ?? null;
    });
    return point;
  });
  const commonYearCount = years.filter(year => observations.every(rows => rows.has(year))).length;
  return { workforce, hasMissingYears: commonYearCount < years.length, commonYearCount };
}
