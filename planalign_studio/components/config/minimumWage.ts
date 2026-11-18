import type { MinimumWagePreview, MinimumWageStepInput } from '../../services/api';
import type { MinimumWageRow } from './types';

// Engine contract: planalign_orchestrator/config/simulation.py MinimumWageStep
// (0 < rate <= 500) and CompensationSettings.minimum_wage (at most 50 steps,
// one per calendar year).
export const MAX_MINIMUM_WAGE_STEPS = 50;
export const MAX_MINIMUM_HOURLY_RATE = 500;
const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

let nextRowKey = 0;
/** A client-only key that keeps each row's editor state with it when rows are removed. */
export function newMinimumWageRowKey(): string {
  nextRowKey += 1;
  return `minimum-wage-row-${nextRowKey}`;
}

export function newMinimumWageRow(): MinimumWageRow {
  return { rowKey: newMinimumWageRowKey(), hourlyRate: 0, effectiveDate: '' };
}

function dateYear(value: string): number | null {
  const match = DATE_PATTERN.exec(value);
  if (!match) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value ? null : Number(match[1]);
}

function validRate(rate: number): boolean {
  return Number.isFinite(rate) && rate > 0 && rate <= MAX_MINIMUM_HOURLY_RATE;
}

export interface MinimumWageIssues {
  /** Break the engine contract, so saving is blocked. */
  errors: string[];
  /** Allowed; the engine warns and skips the step in this run. */
  warnings: string[];
}

function rowIssues(row: MinimumWageRow, rows: MinimumWageRow[], startYear: number, endYear: number): MinimumWageIssues {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!validRate(row.hourlyRate)) errors.push(`Enter a new minimum above $0 and up to $${MAX_MINIMUM_HOURLY_RATE} an hour.`);
  const year = dateYear(row.effectiveDate);
  if (year === null) {
    errors.push('Choose an effective date.');
  } else if (rows.filter(other => dateYear(other.effectiveDate) === year).length > 1) {
    errors.push(`Only one step per calendar year: another step is also in ${year}.`);
  } else if (year < startYear || year > endYear) {
    warnings.push(`The effective date is outside the simulated years ${startYear}–${endYear}, so this step won't apply in this run.`);
  }
  return { errors, warnings };
}

/** Issues per row, in row order. */
export function minimumWageIssues(rows: MinimumWageRow[], startYear: number, endYear: number): MinimumWageIssues[] {
  return rows.map(row => rowIssues(row, rows, startYear, endYear));
}

/** Errors that block saving, prefixed with the step's number. Warnings never block. */
export function minimumWageSaveErrors(rows: MinimumWageRow[], startYear: number, endYear: number): string[] {
  const listErrors = rows.length > MAX_MINIMUM_WAGE_STEPS ? [`Add at most ${MAX_MINIMUM_WAGE_STEPS} minimum wage steps.`] : [];
  return [...listErrors, ...minimumWageIssues(rows, startYear, endYear).flatMap(({ errors }, index) =>
    errors.map(error => `Minimum wage step ${index + 1}: ${error}`))];
}

/** Saved shape, in date order as the engine reads it. */
export function minimumWagePayload(rows: MinimumWageRow[]): MinimumWageStepInput[] {
  return rows
    .map(row => ({ hourly_rate: row.hourlyRate, effective_date: row.effectiveDate }))
    .sort((a, b) => a.effective_date.localeCompare(b.effective_date));
}

/** Steps complete enough to preview: a valid rate and date, one per year. */
export function previewableSteps(rows: MinimumWageRow[]): MinimumWageStepInput[] {
  const issues = minimumWageIssues(rows, Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY);
  return minimumWagePayload(rows.filter((_, index) => issues[index].errors.length === 0));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Rows from config; undefined when the config does not set a minimum wage. */
export function minimumWageFromConfig(value: unknown): MinimumWageRow[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.filter(isRecord).map(item => ({
    rowKey: newMinimumWageRowKey(),
    hourlyRate: Number(item.hourly_rate),
    effectiveDate: String(item.effective_date ?? '').slice(0, 10),
  }));
}

export function formatHourlyRate(rate: number): string {
  return Number.isFinite(rate)
    ? `$${rate.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : '$—';
}

export function formatStepDate(value: string): string {
  if (dateYear(value) === null) return value || 'a date not yet chosen';
  return new Date(`${value}T00:00:00Z`).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
}

type StepLike = Pick<MinimumWageRow, 'hourlyRate' | 'effectiveDate'>;

/** "$21.00 an hour from Jul 1, 2026", "2 steps: $20.00 from …; $22.00 from …" or "none". */
export function describeMinimumWage(rows: StepLike[]): string {
  if (rows.length === 0) return 'none';
  if (rows.length === 1) return `${formatHourlyRate(rows[0].hourlyRate)} an hour from ${formatStepDate(rows[0].effectiveDate)}`;
  return `${rows.length} steps: ${rows.map(row => `${formatHourlyRate(row.hourlyRate)} from ${formatStepDate(row.effectiveDate)}`).join('; ')}`;
}

export type CensusRateStatus =
  | { kind: 'no_census' }
  | { kind: 'checking' }
  | { kind: 'error'; message: string }
  | { kind: 'no_rates'; columnsPresent: string[]; minimumRate: number; maximumRate: number }
  | { kind: 'ready'; headcount: number; withRate: number };

/**
 * Whether the scenario's census can carry a minimum wage. The engine rejects a
 * run with steps when no census row has a usable hourly rate, so neither "no
 * hourly columns" nor "columns but no usable rate" can be modeled.
 */
export function censusRateStatus(
  censusPath: string,
  preview: { data: MinimumWagePreview | null; error: string; pending: boolean },
): CensusRateStatus {
  if (!censusPath) return { kind: 'no_census' };
  const { data } = preview;
  if (!data) return preview.error && !preview.pending ? { kind: 'error', message: preview.error } : { kind: 'checking' };
  const summary = data.hourly_rate_summary;
  if (!summary || summary.with_rate === 0) {
    return {
      kind: 'no_rates',
      columnsPresent: summary?.columns_present ?? [],
      minimumRate: summary?.minimum_rate ?? 0,
      maximumRate: summary?.maximum_rate ?? 0,
    };
  }
  return { kind: 'ready', headcount: data.headcount, withRate: summary.with_rate };
}
