import { ApiError } from '../services/api';

/** Prefer the exact Baseline name; accept capitalization/spacing differences. */
export function baselineScenarioId(scenarios: { id: string; name: string }[]): string | null {
  return (scenarios.find(scenario => scenario.name === 'Baseline')
    ?? scenarios.find(scenario => scenario.name.trim().toLowerCase() === 'baseline'))?.id ?? null;
}

/** The 409 the API returns when the target scenario has no matching completed run. */
export function isMissingRunError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409
    && typeof e.detail === 'string' && e.detail.startsWith('No completed simulation matches');
}

export type GrowthMetric = 'active_average' | 'payroll_per_head';

/**
 * Optimizer settings for a metric. Total pay per head runs with the compound
 * band and starting-pay cap it was validated with (#1073). Setting the raise
 * budget from the target needs the two-dial search, under either metric.
 */
export function growthMetricSettings(
  metric: GrowthMetric,
  solveSalaryGrowth: boolean,
  solveRaiseBudget = false,
) {
  if (metric === 'active_average') {
    return solveSalaryGrowth && solveRaiseBudget ? { solve_raise_budget: true } : {};
  }
  return {
    growth_metric: metric,
    ...(solveSalaryGrowth
      ? {
          compound_band_pct: 0.04,
          salary_growth_max: 0.05,
          stop_on_plateau: true,
          solve_raise_budget: solveRaiseBudget,
        }
      : {}),
  };
}

export interface CostEstimateRow {
  simulation_year: number;
  current_total_pay: number;
  solved_total_pay: number;
  current_employer_cost: number;
  estimated_employer_cost: number;
}

/** Final-year and whole-horizon totals for the panel's before-and-after table. */
export function costSummary(rows: CostEstimateRow[]) {
  if (rows.length === 0) return null;
  const last = rows.reduce((a, b) => (b.simulation_year > a.simulation_year ? b : a));
  const sum = (pick: (row: CostEstimateRow) => number) => rows.reduce((total, row) => total + pick(row), 0);
  return {
    firstYear: Math.min(...rows.map(row => row.simulation_year)),
    lastYear: last.simulation_year,
    pay: [last.current_total_pay, last.solved_total_pay] as const,
    cost: [last.current_employer_cost, last.estimated_employer_cost] as const,
    horizonCost: [sum(row => row.current_employer_cost), sum(row => row.estimated_employer_cost)] as const,
  };
}
