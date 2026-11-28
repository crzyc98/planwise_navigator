/**
 * Effective year on Cost Comparison (#791).
 *
 * Before the effective year every scenario other than the anchor shows the
 * anchor's figures; from that year on it shows its own run. The API combines
 * the runs (so the exports match the page); this module holds the page rules.
 * `null` means the first simulation year: the page is exactly as it was.
 */
import type { DCPlanAnalytics } from '../services/api';

export const GRANDFATHER_BLOCKED =
  "Grandfathering can't be combined with a later effective year yet. Set the effective year back to the first year to use it.";
export const NET_BLOCKED =
  "Net of forfeitures can't be combined with a later effective year yet. Set the effective year back to the first year to use it.";
export const UNAVAILABLE_YEAR_NOTE = 'The run that supplies this year has no result for it.';

/** Why the effective year can't be changed in the current view, or null. */
export function effectiveYearBlockedReason(
  grandfatherExisting: boolean,
  costView: 'gross' | 'net',
): string | null {
  if (grandfatherExisting) {
    return "A later effective year can't be combined with grandfathering yet. Turn off grandfathering to set one.";
  }
  if (costView === 'net') {
    return "A later effective year can't be combined with net of forfeitures yet. Switch to Gross to set one.";
  }
  return null;
}

/** Every year from the first simulation year to the last one shown. */
export function effectiveYearOptions(firstYear: number | undefined, years: number[]): number[] {
  if (firstYear === undefined || years.length === 0) return [];
  const last = Math.max(firstYear, ...years);
  return Array.from({ length: last - firstYear + 1 }, (_, index) => firstYear + index);
}

/** A stored year, or null (the first year) for anything else. */
export function restoreEffectiveYear(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) ? value : null;
}

/** Years a combined series can't show because the supplying run has no result. */
export function unavailableYears(analytics: DCPlanAnalytics): Set<number> {
  return new Set((analytics.year_sources ?? [])
    .filter(source => !source.available)
    .map(source => source.year));
}
