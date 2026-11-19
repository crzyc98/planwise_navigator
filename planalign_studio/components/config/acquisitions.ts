import type { CompensationAnalysis } from '../../services/api';
import type { AcquisitionPay, AcquisitionRow } from './types';

// Engine contract: planalign_orchestrator/config/workforce.py AcquisitionSettings.
export const MAX_ACQUISITIONS = 99;
export const MAX_ACQUISITION_HEADCOUNT = 99_999;
const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9-]{0,31}$/;
const ID_LENGTH = 32;
const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
// Override ranges, matching the engine's validation.
export const PERCENT_OF_STAFF_RANGE = { min: 10, max: 1000 } as const;
export const MAX_AVERAGE_PAY = 10_000_000;
export const AVERAGE_AGE_RANGE = { min: 18, max: 80 } as const;
export const MAX_AVERAGE_SERVICE = 62;
/** Keys this editor reads and writes; any other saved key is kept as is. */
const EDITED_KEYS = new Set([
  'id', 'name', 'headcount', 'effective_date', 'service_credit', 'plan_entry',
  'starting_participation_rate', 'starting_deferral_rate',
  'average_pay', 'relative_pay', 'average_age', 'average_service',
]);

let nextRowKey = 0;
/** A client-only key that keeps each row's editor state with it when rows are removed. */
export function newAcquisitionRowKey(): string {
  nextRowKey += 1;
  return `acquisition-row-${nextRowKey}`;
}

/** An empty row with the engine defaults: mirrors staff, prior service, entry on the date, auto-enrollment. */
export function newAcquisitionRow(): AcquisitionRow {
  return {
    rowKey: newAcquisitionRowKey(), id: '', name: '', headcount: 0, effectiveDate: '',
    serviceCredit: 'prior_service', planEntry: 'acquisition_date',
    startingParticipationPct: null, startingDeferralPct: null,
    pay: { kind: 'mirror' }, averageAge: null, averageService: null, extra: {},
  };
}

/** A valid, unused engine id from a display name: lowercase letters, digits and hyphens. */
export function acquisitionId(name: string, taken: ReadonlySet<string>): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, ID_LENGTH).replace(/-+$/, '') || 'acquisition';
  if (!taken.has(base)) return base;
  for (let n = 2; ; n += 1) {
    const suffix = `-${n}`;
    const candidate = `${base.slice(0, ID_LENGTH - suffix.length).replace(/-+$/, '')}${suffix}`;
    if (!taken.has(candidate)) return candidate;
  }
}

/** Rename a row. Its id follows the name until it has been saved, then stays fixed. */
export function renameAcquisition(rows: AcquisitionRow[], index: number, name: string, savedIds: ReadonlySet<string>): AcquisitionRow[] {
  return rows.map((row, i) => {
    if (i !== index) return row;
    if (savedIds.has(row.id)) return { ...row, name };
    const taken = new Set(rows.filter((_, j) => j !== index).map(other => other.id));
    return { ...row, name, id: acquisitionId(name, taken) };
  });
}

function dateYear(value: string): number | null {
  const match = DATE_PATTERN.exec(value);
  if (!match) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value ? null : Number(match[1]);
}

export interface AcquisitionIssues {
  /** Break the engine contract, so saving is blocked. */
  errors: string[];
  /** Allowed; the engine warns and skips the group in this run. */
  warnings: string[];
}

function rowIssues(row: AcquisitionRow, rows: AcquisitionRow[], startYear: number, endYear: number): AcquisitionIssues {
  const errors: string[] = [];
  const warnings: string[] = [];
  const name = row.name.trim().toLowerCase();
  if (!name) errors.push('Enter a name.');
  else if (rows.filter(other => other.name.trim().toLowerCase() === name).length > 1) errors.push('Use a different name for each acquisition.');
  if (!ID_PATTERN.test(row.id)) errors.push('Its id must be letters, digits and hyphens, up to 32 characters.');
  else if (rows.filter(other => other.id === row.id).length > 1) errors.push(`Another acquisition already uses the id "${row.id}".`);
  if (!Number.isInteger(row.headcount) || row.headcount < 1 || row.headcount > MAX_ACQUISITION_HEADCOUNT) {
    errors.push(`Enter a headcount from 1 to ${MAX_ACQUISITION_HEADCOUNT.toLocaleString()}.`);
  }
  const year = dateYear(row.effectiveDate);
  if (year === null) errors.push('Choose an effective date.');
  else if (year < startYear || year > endYear) warnings.push(`The effective date is outside the simulated years ${startYear}–${endYear}, so this group won't join in this run.`);
  return { errors: [...errors, ...planIssues(row), ...overrideIssues(row)], warnings };
}

const inRange = (value: number, min: number, max: number) => Number.isFinite(value) && value >= min && value <= max;

function planIssues(row: AcquisitionRow): string[] {
  if (row.startingParticipationPct === null && row.startingDeferralPct === null) return [];
  const errors: string[] = [];
  if (row.startingParticipationPct === null || !inRange(row.startingParticipationPct, 0, 100)) {
    errors.push('Enter the share already participating, from 0% to 100%.');
  }
  if (row.startingDeferralPct === null || !inRange(row.startingDeferralPct, 0, 100) || row.startingDeferralPct === 0) {
    errors.push('Enter their average deferral rate, above 0% and up to 100%.');
  }
  return errors;
}

function overrideIssues(row: AcquisitionRow): string[] {
  const errors: string[] = [];
  const { pay, averageAge, averageService } = row;
  if (pay.kind === 'relative' && !inRange(pay.percentOfStaff, PERCENT_OF_STAFF_RANGE.min, PERCENT_OF_STAFF_RANGE.max)) {
    errors.push(`Enter pay from ${PERCENT_OF_STAFF_RANGE.min}% to ${PERCENT_OF_STAFF_RANGE.max.toLocaleString()}% of existing staff.`);
  }
  if (pay.kind === 'amount' && (!inRange(pay.averagePay, 0, MAX_AVERAGE_PAY) || pay.averagePay === 0)) {
    errors.push(`Enter an average pay above $0 and up to $${MAX_AVERAGE_PAY.toLocaleString()}.`);
  }
  if (averageAge !== null && !inRange(averageAge, AVERAGE_AGE_RANGE.min, AVERAGE_AGE_RANGE.max)) {
    errors.push(`Enter an average age from ${AVERAGE_AGE_RANGE.min} to ${AVERAGE_AGE_RANGE.max}.`);
  }
  if (averageService !== null && !inRange(averageService, 0, MAX_AVERAGE_SERVICE)) {
    errors.push(`Enter average service from 0 to ${MAX_AVERAGE_SERVICE} years.`);
  } else if (averageService !== null && averageAge !== null && averageService > averageAge - 18) {
    errors.push('Average service can be at most average age minus 18.');
  }
  return errors;
}

/** Issues per row, in row order. */
export function acquisitionIssues(rows: AcquisitionRow[], startYear: number, endYear: number): AcquisitionIssues[] {
  return rows.map(row => rowIssues(row, rows, startYear, endYear));
}

/** Errors that block saving, as one list prefixed with each group's name. Warnings never block. */
export function acquisitionSaveErrors(rows: AcquisitionRow[], startYear: number, endYear: number): string[] {
  const listErrors = rows.length > MAX_ACQUISITIONS ? [`Add at most ${MAX_ACQUISITIONS} acquisitions.`] : [];
  return [...listErrors, ...acquisitionIssues(rows, startYear, endYear).flatMap(({ errors }, index) =>
    errors.map(error => `Acquisition ${rows[index].name.trim() || index + 1}: ${error}`))];
}

// Config holds rates as fractions; the editor shows percents. Rounding keeps 0.07 -> 7 -> 0.07.
const toPercent = (fraction: number) => Number((fraction * 100).toFixed(4));
const toFraction = (percent: number) => Number((percent / 100).toFixed(6));

function payPayload(pay: AcquisitionPay): Record<string, number> {
  if (pay.kind === 'relative') return { relative_pay: toFraction(pay.percentOfStaff) };
  if (pay.kind === 'amount') return { average_pay: pay.averagePay };
  return {};
}

/**
 * Saved entries. Keys Studio does not edit are written back as loaded; plan
 * settings at their defaults and unset overrides are left out, as the engine
 * reads a missing key as the default.
 */
export function acquisitionsPayload(rows: AcquisitionRow[]) {
  return rows.map(row => ({
    ...row.extra,
    id: row.id,
    name: row.name.trim(),
    headcount: row.headcount,
    effective_date: row.effectiveDate,
    ...(row.serviceCredit !== 'prior_service' ? { service_credit: row.serviceCredit } : {}),
    ...(row.planEntry !== 'acquisition_date' ? { plan_entry: row.planEntry } : {}),
    ...(row.startingParticipationPct !== null || row.startingDeferralPct !== null ? {
      starting_participation_rate: row.startingParticipationPct === null ? null : toFraction(row.startingParticipationPct),
      starting_deferral_rate: row.startingDeferralPct === null ? null : toFraction(row.startingDeferralPct),
    } : {}),
    ...payPayload(row.pay),
    ...(row.averageAge !== null ? { average_age: row.averageAge } : {}),
    ...(row.averageService !== null ? { average_service: row.averageService } : {}),
  }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

const numberOrNull = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);
const percentOrNull = (value: unknown): number | null => {
  const fraction = numberOrNull(value);
  return fraction === null ? null : toPercent(fraction);
};

function payFromConfig(item: Record<string, unknown>): AcquisitionPay {
  const relative = numberOrNull(item.relative_pay);
  if (relative !== null) return { kind: 'relative', percentOfStaff: toPercent(relative) };
  const amount = numberOrNull(item.average_pay);
  return amount === null ? { kind: 'mirror' } : { kind: 'amount', averagePay: amount };
}

/** Rows from config; undefined when the config does not set acquisitions. */
export function acquisitionsFromConfig(value: unknown): AcquisitionRow[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.filter(isRecord).map(item => {
    const id = String(item.id ?? '');
    const name = typeof item.name === 'string' && item.name.trim() ? item.name : id;
    return {
      rowKey: newAcquisitionRowKey(), id, name, headcount: Number(item.headcount), effectiveDate: String(item.effective_date ?? ''),
      serviceCredit: item.service_credit === 'acquisition_date' ? 'acquisition_date' : 'prior_service',
      planEntry: item.plan_entry === 'waiting_period' ? 'waiting_period' : 'acquisition_date',
      startingParticipationPct: percentOrNull(item.starting_participation_rate),
      startingDeferralPct: percentOrNull(item.starting_deferral_rate),
      pay: payFromConfig(item),
      averageAge: numberOrNull(item.average_age),
      averageService: numberOrNull(item.average_service),
      extra: Object.fromEntries(Object.entries(item).filter(([key]) => !EDITED_KEYS.has(key))),
    };
  });
}

/** Whether the row overrides who the group is, rather than mirroring existing staff. */
export function hasOverrides(row: Pick<AcquisitionRow, 'pay' | 'averageAge' | 'averageService'>): boolean {
  return row.pay.kind !== 'mirror' || row.averageAge !== null || row.averageService !== null;
}

/** e.g. "Mirrors existing staff" or "Pay 90% of staff, average age 44". */
export function describeOverrides(row: Pick<AcquisitionRow, 'pay' | 'averageAge' | 'averageService'>): string {
  if (!hasOverrides(row)) return 'Mirrors existing staff';
  const parts: string[] = [];
  if (row.pay.kind === 'relative') {
    parts.push(Number.isFinite(row.pay.percentOfStaff) ? `pay ${row.pay.percentOfStaff}% of staff` : 'pay relative to staff, not yet set');
  }
  if (row.pay.kind === 'amount') parts.push(`average pay $${row.pay.averagePay.toLocaleString()}`);
  if (row.averageAge !== null) parts.push(`average age ${row.averageAge}`);
  if (row.averageService !== null) parts.push(`average service ${row.averageService} years`);
  const text = parts.join(', ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Estimated annual pay for a group: headcount times staff average pay, or the
 * set amount, scaled by a relative pay override. Null when there is no staff
 * average to start from and no amount.
 */
export function estimatedAnnualPay(row: Pick<AcquisitionRow, 'headcount' | 'pay'>, staffAveragePay: number | null): number | null {
  const headcount = Number.isFinite(row.headcount) ? row.headcount : 0;
  if (row.pay.kind === 'amount') return headcount * row.pay.averagePay;
  if (staffAveragePay === null) return null;
  // A cleared percent field is NaN until it is filled in.
  if (row.pay.kind === 'relative' && !Number.isFinite(row.pay.percentOfStaff)) return null;
  const factor = row.pay.kind === 'relative' ? row.pay.percentOfStaff / 100 : 1;
  return headcount * staffAveragePay * factor;
}

export function totalAcquiredHeadcount(rows: Array<Pick<AcquisitionRow, 'headcount'>>): number {
  return rows.reduce((sum, row) => sum + (Number.isFinite(row.headcount) ? row.headcount : 0), 0);
}

/** Settings that differ from the defaults, in plain words, e.g. ["service from the acquisition date", "pay 90% of staff"]. */
export function acquisitionDetails(row: AcquisitionRow): string[] {
  const details: string[] = [];
  if (row.serviceCredit === 'acquisition_date') details.push('service from the acquisition date');
  if (row.planEntry === 'waiting_period') details.push('waiting period before entry');
  if (row.startingParticipationPct !== null || row.startingDeferralPct !== null) {
    details.push(`${row.startingParticipationPct ?? '?'}% participating at ${row.startingDeferralPct ?? '?'}%`);
  }
  if (hasOverrides(row)) details.push(describeOverrides(row).toLowerCase());
  const extra = Object.keys(row.extra);
  if (extra.length) details.push(`other settings: ${extra.sort().join(', ')}`);
  return details;
}

/**
 * Each group's name, headcount, date and any non-default settings, e.g.
 * "Acme: 250 on 2026-07-01 (pay 90% of staff); Beta: 50 on 2027-01-01", or "none".
 */
export function listAcquisitions(rows: AcquisitionRow[]): string {
  if (rows.length === 0) return 'none';
  return rows.map(row => {
    const details = acquisitionDetails(row);
    const suffix = details.length ? ` (${details.join('; ')})` : '';
    return `${row.name}: ${row.headcount.toLocaleString()} on ${row.effectiveDate}${suffix}`;
  }).join('; ');
}

/** "2 groups, 300 people" or "none". */
export function describeAcquisitions(rows: Array<Pick<AcquisitionRow, 'headcount'>>): string {
  if (rows.length === 0) return 'none';
  const people = totalAcquiredHeadcount(rows);
  return `${rows.length} ${rows.length === 1 ? 'group' : 'groups'}, ${people.toLocaleString()} ${people === 1 ? 'person' : 'people'}`;
}

/**
 * Average pay of active staff from the census compensation analysis (all
 * employees, not only recent hires): the level averages weighted by headcount,
 * or the overall average when the census has no levels.
 */
export function staffAveragePay(analysis: Pick<CompensationAnalysis, 'levels' | 'overall_stats'>): number | null {
  const levels = (analysis.levels ?? []).filter(level => level.employee_count > 0);
  const people = levels.reduce((sum, level) => sum + level.employee_count, 0);
  if (people > 0) return levels.reduce((sum, level) => sum + level.avg_compensation * level.employee_count, 0) / people;
  return analysis.overall_stats?.avg_compensation ?? null;
}
