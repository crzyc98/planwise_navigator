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
export interface SearchLimits {
  scaleMax: number;
  salaryGrowthMaxPct: number;
}

/** Say which dials finished at a limit. Reaching one doesn't prove it caused a miss. */
export function searchLimitNotes(
  bestScale: number | null | undefined,
  bestSalaryGrowthRate: number | null | undefined,
  limits: SearchLimits,
): string[] {
  const notes: string[] = [];
  if (bestScale != null && bestScale >= limits.scaleMax - 1e-6) {
    notes.push(`New-hire scale ended at its ${limits.scaleMax.toFixed(2)}× limit.`);
  }
  if (bestSalaryGrowthRate != null && bestSalaryGrowthRate * 100 >= limits.salaryGrowthMaxPct - 1e-6) {
    notes.push(`Starting-pay growth ended at its ${limits.salaryGrowthMaxPct.toFixed(1)}%/yr limit.`);
  }
  return notes;
}

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
          stop_on_plateau: true,
          solve_raise_budget: solveRaiseBudget,
        }
      : {}),
  };
}

export interface SearchInputs {
  tolerance_pct?: number;
  max_iterations?: number;
  search_mode?: string;
  initial_scale?: number;
  scale_min?: number;
  scale_max?: number;
  solve_salary_growth?: boolean;
  salary_growth_min?: number;
  salary_growth_max?: number;
  compound_band_pct?: number | null;
  solve_raise_budget?: boolean;
  raise_budget_limit_pct?: number;
}

/** Every start and bound a search uses, in words. Reads what is sent, or what was saved. */
export function searchInputLines(inputs: SearchInputs): string[] {
  const lines = [`Tolerance ±${(inputs.tolerance_pct ?? 0.05).toFixed(2)}pp, up to ${inputs.max_iterations ?? 8} runs.`];
  if (inputs.search_mode !== 'new_hire_scale') return lines;
  lines.push(
    `New-hire scale starts at ${(inputs.initial_scale ?? 1).toFixed(2)}×, `
    + `searched from ${(inputs.scale_min ?? 0.5).toFixed(2)}× to ${(inputs.scale_max ?? 3).toFixed(2)}×.`,
  );
  if (!inputs.solve_salary_growth) return lines;
  lines.push(
    `Starting-pay growth searched from ${((inputs.salary_growth_min ?? 0) * 100).toFixed(1)}% `
    + `to ${((inputs.salary_growth_max ?? 0.08) * 100).toFixed(1)}%/yr.`,
  );
  if (inputs.compound_band_pct != null) {
    lines.push(`Horizon mean held within ±${inputs.compound_band_pct.toFixed(2)}pp of the target.`);
  }
  if (inputs.solve_raise_budget) {
    lines.push(`Raise budget set from the target, within ${(inputs.raise_budget_limit_pct ?? 1).toFixed(1)}pp of the starting raises.`);
  }
  return lines;
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
