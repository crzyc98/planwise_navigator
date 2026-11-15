/**
 * Seed ranges beside Cost Comparison's employer-cost figures.
 *
 * The ensemble metric is gross match + core over every employee, so ranges sit
 * only beside that same number: not beside grandfathered or cohort-filtered
 * costs, and not beside net-of-forfeiture rows. Differences come from the API
 * already paired seed by seed with the anchor.
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

function sameYears(range: ScenarioCostRange, years: number[]): boolean {
  if (range.start_year === null || range.end_year === null || years.length === 0) return false;
  const sorted = [...years].sort((a, b) => a - b);
  return sorted[0] === range.start_year
    && sorted[sorted.length - 1] === range.end_year
    && sorted.length === range.end_year - range.start_year + 1;
}

/**
 * Shape the API response for the cost matrix. A scenario's ranges are used
 * only when its ensemble covers exactly the years its results show; its
 * difference also needs the anchor's ensemble to cover the anchor's years.
 */
export function buildSeedRangeView(
  ranges: ScenarioCostRange[],
  resultYears: Map<string, number[]>,
  anchorId: string,
): SeedRangeView {
  const rows = new Map<string, SeedRangeRow>();
  const notes: SeedRangeView['notes'] = [];
  const matches = (range: ScenarioCostRange) => sameYears(range, resultYears.get(range.scenario_id) ?? []);
  const anchor = ranges.find(range => range.scenario_id === anchorId);
  const anchorMatches = anchor !== undefined && matches(anchor);

  for (const range of ranges) {
    if (range.job_id === null) continue; // no ensemble: point figures stay as they are
    if (!matches(range)) {
      notes.push({
        scenarioId: range.scenario_id,
        reason: `Its ensemble covers ${range.start_year}–${range.end_year}, not the years shown, so no range is shown.`,
      });
      continue;
    }
    const pairedNote = range.scenario_id === anchorId ? null : pairingNote(range, anchorMatches);
    if (pairedNote) notes.push({ scenarioId: range.scenario_id, reason: pairedNote });
    rows.set(range.scenario_id, {
      years: new Map(range.years.map(band => [band.year, band])),
      total: range.total,
      difference: pairedNote === null ? range.difference_total : null,
    });
  }
  return { rows, notes };
}

function pairingNote(range: ScenarioCostRange, anchorMatches: boolean): string | null {
  if (!range.paired) return range.reason ?? 'Not paired with the anchor.';
  if (!anchorMatches) return "The anchor's ensemble doesn't cover the years shown, so they aren't paired.";
  return null;
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

/** Short cell text: "saves $40.0K–$80.0K", "adds …", or a signed span when it straddles zero. */
export function formatDifference(range: DifferenceView): string {
  if (range.max < 0) {
    return `saves ${formatCompactCurrency(-range.max)}–${formatCompactCurrency(-range.min)}`;
  }
  if (range.min > 0) {
    return `adds ${formatCompactCurrency(range.min)}–${formatCompactCurrency(range.max)}`;
  }
  return `${formatCompactCurrency(range.min)} to +${formatCompactCurrency(range.max)}`;
}

/** Full sentence for the tooltip: "Costs $X less than the anchor; across 10 seeds the saving ranges from A to B." */
export function describeDifference(delta: number, range: DifferenceView): string {
  const point = `Costs ${formatCompactCurrency(Math.abs(delta))} ${delta < 0 ? 'less' : 'more'} than the anchor`;
  const seeds = `across ${range.n_seeds} seeds`;
  if (range.max < 0) {
    return `${point}; ${seeds} the saving ranges from ${formatCompactCurrency(-range.max)} to ${formatCompactCurrency(-range.min)}.`;
  }
  if (range.min > 0) {
    return `${point}; ${seeds} the extra cost ranges from ${formatCompactCurrency(range.min)} to ${formatCompactCurrency(range.max)}.`;
  }
  return `${point}; ${seeds} the difference ranges from ${formatCompactCurrency(range.min)} to +${formatCompactCurrency(range.max)}, so its direction depends on the seed.`;
}
