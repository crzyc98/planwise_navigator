import type { DCPlanAnalytics } from '../services/api';

export type CostBreakdown = 'total' | 'split';
export type CostChartRow = Record<string, number | null>;

export function restoreCostBreakdown(value: unknown): CostBreakdown {
  return value === 'split' ? 'split' : 'total';
}

export function splitUnavailableReason(costView: 'gross' | 'net', grandfatherExisting: boolean): string | null {
  if (grandfatherExisting) return 'Match/core breakdown is unavailable for grandfathered costs.';
  if (costView === 'net') return 'Forfeiture offsets are not allocated between match and core.';
  return null;
}

export function componentKey(id: string, component: 'match' | 'core'): string {
  return `component:${component}:${id}`;
}

/** Match the total chart's empty-cohort handling and accumulate each component separately. */
export function buildCostBreakdownRows(
  rows: CostChartRow[],
  analytics: DCPlanAnalytics[],
  scenarioIds: string[],
  cumulative: boolean,
): CostChartRow[] {
  const summaries = new Map(analytics.map(item => [item.scenario_id,
    new Map(item.contribution_by_year.map(year => [year.year, year])),
  ]));
  const running = new Map<string, number>();
  const unavailable = new Set<string>();
  return rows.map(row => {
    const result = { ...row };
    scenarioIds.forEach(id => {
      const summary = row.year === null ? undefined : summaries.get(id)?.get(row.year);
      (['match', 'core'] as const).forEach(component => {
        const key = componentKey(id, component);
        const value = row[id] === null ? null : (summary?.[`total_employer_${component}`] ?? 0);
        if (cumulative && value === null) unavailable.add(key);
        if (value !== null) running.set(key, (running.get(key) ?? 0) + value);
        result[key] = cumulative
          ? (unavailable.has(key) ? null : running.get(key) ?? 0)
          : value;
      });
    });
    return result;
  });
}

export function componentShare(value: number, total: number): string {
  return total === 0 ? '—' : `${(value / total * 100).toFixed(1)}%`;
}
