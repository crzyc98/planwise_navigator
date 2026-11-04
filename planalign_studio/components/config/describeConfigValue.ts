/**
 * Plain-language rendering for structured configuration values (schedules,
 * multiplier tables, eligibility blocks) so review and comparison screens
 * never fall back to raw JSON.
 */

type Row = Record<string, unknown>;

const isRow = (value: unknown): value is Row =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

const num = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

const trim = (value: number) => Number(value.toFixed(3)).toLocaleString('en-US');
const pct = (fraction: number) => `${trim(fraction * 100)}%`;
const money = (value: number) => `$${Math.round(value).toLocaleString('en-US')}`;

const ACRONYMS: Record<string, string> = { aip: 'AIP', ss: 'SS', id: 'ID', irs: 'IRS', pp: 'pp' };

/** `minimum_tenure_years` -> `Minimum tenure years`. */
export function humanizeKey(key: string): string {
  const words = key.split(/[._]/).filter(Boolean).map(word => ACRONYMS[word] ?? word);
  const text = words.join(' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const FRACTION_KEY = /(^|_)(rate|share|weight|probability|pct|employee_min|employee_max)$/;
const PERCENT_POINT_KEY = /_percent$/;
const MONEY_KEY = /(compensation|salary|wage|_amount|_dollars)$/;

/** Format one scalar, using its key to decide on %, $ or a plain number. */
export function describeScalar(key: string, value: unknown, parent = ''): string {
  if (value === null || value === undefined) return 'None';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  const n = num(value);
  if (n === undefined) return String(value);
  // Engine core schedules store `rate` in percentage points (3.0 = 3%).
  if (key === 'rate' && /(^|\.)employer_core_/.test(parent)) return `${trim(n)}%`;
  if (key === 'multiplier' || key.endsWith('_multiplier')) return `×${trim(n)}`;
  if (PERCENT_POINT_KEY.test(key)) return `${trim(n)}%`;
  if (FRACTION_KEY.test(key) && n >= 0 && n <= 1) return pct(n);
  if (MONEY_KEY.test(key)) return money(n);
  return trim(n);
}

function range(min: unknown, max: unknown, unit: (value: number) => string): string {
  const lo = num(min) ?? 0;
  const hi = num(max);
  return hi === undefined ? `${unit(lo)}+` : `${unit(lo)}–${unit(hi)}`;
}

const rateOf = (row: Row, parent: string): string => {
  const key = 'contribution_rate' in row ? 'contribution_rate' : 'rate';
  return describeScalar(key, row[key], parent);
};

/** Threshold label for `{min, multiplier}` rows, based on the table's name. */
function thresholdLabel(parent: string, min: number): string {
  if (/income|compensation/.test(parent)) return `${money(min)}+ pay`;
  if (/tenure/.test(parent)) return `${trim(min)}+ yrs service`;
  if (/_rate$/.test(parent)) return `${pct(min)}+ contribution`;
  if (/age/.test(parent)) return `Age ${trim(min)}+`;
  return `${trim(min)}+`;
}

/** Known row shapes; returns undefined when the row is not recognised. */
function describeKnownRow(row: Row, parent: string): string | undefined {
  if ('min_age' in row && ('rate' in row || 'contribution_rate' in row)) {
    return `Age ${range(row.min_age, row.max_age, trim)}: ${rateOf(row, parent)}`;
  }
  if ('min_points' in row) return `${range(row.min_points, row.max_points, trim)} points: ${rateOf(row, parent)}`;
  if ('service_years_min' in row || 'min_years' in row) {
    const lo = row.service_years_min ?? row.min_years;
    const hi = 'service_years_max' in row ? row.service_years_max : row.max_years;
    return `${range(lo, hi, trim)} yrs service: ${rateOf(row, parent)}`;
  }
  if ('min' in row && 'multiplier' in row && num(row.min) !== undefined) {
    return `${thresholdLabel(parent, num(row.min) ?? 0)}: ${describeScalar('multiplier', row.multiplier)}`;
  }
  if ('age' in row && 'weight' in row) return `Age ${describeScalar('age', row.age)}: ${describeScalar('weight', row.weight)}`;
  if ('band_label' in row) return String(row.band_label);
  if ('level' in row && 'min_compensation' in row) {
    const name = typeof row.name === 'string' ? `${row.name} (level ${row.level})` : `Level ${row.level}`;
    return `${name}: ${range(row.min_compensation, row.max_compensation, money)}`;
  }
  if ('age_band' in row && 'multiplier' in row) return `Age ${row.age_band}: ${describeScalar('multiplier', row.multiplier)}`;
  if ('tenure_band' in row && 'multiplier' in row) return `Tenure ${row.tenure_band}: ${describeScalar('multiplier', row.multiplier)}`;
  return undefined;
}

/** One-line description of any config value, never JSON. */
export function describeConfigValue(key: string, value: unknown, parent = ''): string {
  if (Array.isArray(value)) {
    if (!value.length) return 'None';
    return value.map(item => describeConfigValue(key, item, key)).join('; ');
  }
  if (isRow(value)) {
    const known = describeKnownRow(value, parent || key);
    if (known !== undefined) return known;
    const entries = Object.entries(value);
    if (!entries.length) return 'None';
    return entries.map(([name, child]) => {
      const text = describeConfigValue(name, child, key);
      return isRow(child) ? `${humanizeKey(name)} (${text})` : `${humanizeKey(name)}: ${text}`;
    }).join(', ');
  }
  return describeScalar(key, value, parent);
}

export const isStructuredValue = (value: unknown): boolean => Array.isArray(value) || isRow(value);
