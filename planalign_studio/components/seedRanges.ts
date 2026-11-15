/**
 * Seed ranges beside Cost Comparison's employer-cost figures.
 *
 * The ensemble metric is gross match + core over every employee, so ranges sit
 * only beside that same number: not beside grandfathered or cohort-filtered
 * costs, and not beside net-of-forfeiture rows. Differences come from the API
 * already paired seed by seed with the anchor, and only for ensembles run on
 * the same settings (config fingerprint) as the results shown.
 */
import type { DCPlanCohort, ScenarioCostRange } from '../services/api';

export type CostBandView = { p10: number; p90: number; n_seeds: number };
export type DifferenceView = { min: number; max: number; n_seeds: number };

export interface SeedRangeRow {
  years: Map<number, CostBandView>;
  total: CostBandView | null;
  difference: DifferenceView | null;
}

export interface SeedRangeView {
  rows: Map<string, SeedRangeRow>;
  /** One short line per scenario whose ensemble exists but can't be shown or paired. */
  notes: Array<{ scenarioId: string; reason: string }>;
}

export const SEED_RANGE_FOOTNOTE =
  'Ranges show how much each figure moves across simulation seeds: P10–P90 for cost, '
  + 'and the lowest to highest seed-by-seed difference from the anchor. They cover hiring, '
  + 'termination and promotion draws, not enrollment.';

/** Why ranges are hidden in the current view, or null when they apply. */
export function seedRangeHiddenReason(
  cohort: DCPlanCohort,
  grandfatherExisting: boolean,
): string | null {
  if (grandfatherExisting) return 'Seed ranges are for cost without grandfathering, so they are hidden while grandfathering is on.';
  if (cohort !== 'all') return 'Seed ranges cover all employees, so they are hidden for a cohort.';
  return null;
}

/**
 * Shape the API response for the cost matrix. The API decides whether an
 * ensemble may be used (same settings, so the same years, as the results
 * shown) and whether it pairs with the anchor; this only lays it out.
 */
export function buildSeedRangeView(ranges: ScenarioCostRange[]): SeedRangeView {
  const rows = new Map<string, SeedRangeRow>();
  const notes: SeedRangeView['notes'] = [];
  for (const range of ranges) {
    if (range.job_id === null) continue; // no ensemble: point figures stay as they are
    if (range.reason) notes.push({ scenarioId: range.scenario_id, reason: range.reason });
    if (!range.current) continue;
    rows.set(range.scenario_id, {
      years: new Map(range.years.map(band => [band.year, band])),
      total: range.total,
      difference: range.paired ? range.difference_total : null,
    });
  }
  return { rows, notes };
}

/** Compact currency matching the page's formatCurrency, with a real minus sign. */
export function formatCompactCurrency(value: number): string {
  const sign = value < 0 ? '−' : '';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

export function formatCostBand(band: CostBandView): string {
  return `${formatCompactCurrency(band.p10)}–${formatCompactCurrency(band.p90)}`;
}

/** Short cell text: "saves $40.0K–$80.0K", "adds …", a signed span across zero, or "same as anchor". */
export function formatDifference(range: DifferenceView): string {
  if (range.min === 0 && range.max === 0) return 'same as anchor';
  if (range.max <= 0) {
    return `saves ${formatCompactCurrency(-range.max)}–${formatCompactCurrency(-range.min)}`;
  }
  if (range.min >= 0) {
    return `adds ${formatCompactCurrency(range.min)}–${formatCompactCurrency(range.max)}`;
  }
  return `${formatCompactCurrency(range.min)} to +${formatCompactCurrency(range.max)}`;
}

function describePoint(delta: number): string {
  if (delta === 0) return 'Costs the same as the anchor';
  return `Costs ${formatCompactCurrency(Math.abs(delta))} ${delta < 0 ? 'less' : 'more'} than the anchor`;
}

/** Full sentence for the tooltip: "Costs $X less than the anchor; across 10 seeds the saving ranges from A to B." */
export function describeDifference(delta: number, range: DifferenceView): string {
  const seeds = `across ${range.n_seeds} seeds`;
  let spread: string;
  if (range.min === 0 && range.max === 0) {
    spread = `${seeds} it is the same on every seed`;
  } else if (range.max <= 0) {
    spread = `${seeds} the saving ranges from ${formatCompactCurrency(-range.max)} to ${formatCompactCurrency(-range.min)}`;
  } else if (range.min >= 0) {
    spread = `${seeds} the extra cost ranges from ${formatCompactCurrency(range.min)} to ${formatCompactCurrency(range.max)}`;
  } else {
    spread = `${seeds} the difference ranges from ${formatCompactCurrency(range.min)} to +${formatCompactCurrency(range.max)}, so its direction depends on the seed`;
  }
  return `${describePoint(delta)}; ${spread}.`;
}
