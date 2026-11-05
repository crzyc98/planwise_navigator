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
 * band and starting-pay cap it was validated with (#1073); the active metric
 * adds nothing, so its request is unchanged.
 */
export function growthMetricSettings(metric: GrowthMetric, solveSalaryGrowth: boolean) {
  if (metric === 'active_average') return {};
  return {
    growth_metric: metric,
    ...(solveSalaryGrowth
      ? { compound_band_pct: 0.04, salary_growth_max: 0.05, stop_on_plateau: true }
      : {}),
  };
}
