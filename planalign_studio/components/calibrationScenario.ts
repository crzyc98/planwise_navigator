import { ApiError, type AutoCalibrationOutcome } from '../services/api';

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

export type SolveMode = 'new_hire_scale' | 'levers' | 'horizon';

/** Horizon search when the scenario is on the shared pay scale it needs (#1075). */
export function defaultSearchMode(newHire: { shared_pay_scale?: unknown } | null | undefined): SolveMode {
  return newHire?.shared_pay_scale === true ? 'horizon' : 'new_hire_scale';
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
  raise_min?: number;
  raise_max?: number;
  hire_pay_ratio_min?: number;
  hire_pay_ratio_max?: number;
  cagr_tolerance_pct?: number;
  annual_guardrail_pct?: number;
  seed_count?: number;
}

type HorizonReport = NonNullable<AutoCalibrationOutcome['horizon']>;

function horizonInputLines(inputs: SearchInputs): string[] {
  const percent = (value: number | undefined, fallback: number) => ((value ?? fallback) * 100).toFixed(1);
  return [
    `Horizon growth within ±${(inputs.cagr_tolerance_pct ?? 0.25).toFixed(2)}pp, each year within ±${(inputs.annual_guardrail_pct ?? 0.5).toFixed(2)}pp, on the mean of ${inputs.seed_count ?? 3} seeds.`,
    `Raises searched from ${percent(inputs.raise_min, 0.01)}% to ${percent(inputs.raise_max, 0.1)}%.`,
    `Hire pay growth searched from ${percent(inputs.salary_growth_min, 0)}% to ${percent(inputs.salary_growth_max, 0.08)}%/yr.`,
    `Hire pay searched from ${percent(inputs.hire_pay_ratio_min, 0.9)}% to ${percent(inputs.hire_pay_ratio_max, 1.1)}% of existing staff.`,
  ];
}

export function horizonSummaryLines(report: HorizonReport): string[] {
  const lines = [
    `Horizon growth ${report.cagr_pct.toFixed(2)}% (${report.cagr_error_pct >= 0 ? '+' : ''}${report.cagr_error_pct.toFixed(2)}pp from target).`,
    `Years outside the guardrail on the seed average: ${report.guardrail_misses}.`,
    `By seed: ${report.seeds.map(seed => `${seed.seed}: ${seed.cagr_pct.toFixed(2)}%`).join(', ')}.`,
  ];
  if (report.active_bounds.length > 0) {
    lines.push(`At a search limit: ${report.active_bounds.join(', ').replaceAll('_', ' ').replaceAll(':', ' ')}.`);
  }
  return lines;
}

/** Why the server would refuse these limits, in words, so the run never starts. */
export function searchLimitsError(inputs: SearchInputs): string | null {
  const { salary_growth_min: growthMin = 0, salary_growth_max: growthMax = 0.08 } = inputs;
  if (growthMax > 0.25) return 'Keep the hire pay growth limit at 25% or lower.';
  if (growthMin >= growthMax) return 'The hire pay growth limit must be above its minimum.';
  if (inputs.search_mode !== 'horizon') return null;
  const { raise_min: raiseMin = 0.01, raise_max: raiseMax = 0.1 } = inputs;
  const { hire_pay_ratio_min: ratioMin = 0.9, hire_pay_ratio_max: ratioMax = 1.1 } = inputs;
  if (raiseMin < 0 || raiseMax > 0.25) return 'Keep raises between 0% and 25%.';
  if (raiseMin >= raiseMax) return 'Highest raises must be above lowest raises.';
  if (ratioMin < 0.5 || ratioMax > 1.5) return 'Keep hire pay between 50% and 150% of existing staff.';
  if (ratioMin >= ratioMax) return 'Highest hire pay must be above lowest hire pay.';
  return null;
}

/** Every start and bound a search uses, in words. Reads what is sent, or what was saved. */
export function searchInputLines(inputs: SearchInputs): string[] {
  const lines = [`Tolerance ±${(inputs.tolerance_pct ?? 0.05).toFixed(2)}pp, up to ${inputs.max_iterations ?? 8} runs.`];
  if (inputs.search_mode === 'horizon') return horizonInputLines(inputs);
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
