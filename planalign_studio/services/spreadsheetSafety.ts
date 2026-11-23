/**
 * Neutralize strings that spreadsheet apps (Excel, Sheets, Calc) would
 * otherwise evaluate as formulas when exported to CSV or pasted as TSV.
 */

const FORMULA_PREFIX_RE = /^[=+\-@\t\r]/;

/** Prefix formula-triggering strings with an apostrophe so they stay text. */
export function neutralizeFormula(value: string): string {
  return FORMULA_PREFIX_RE.test(value) ? `'${value}` : value;
}

/**
 * Format a single CSV cell: neutralize formula-leading strings and quote
 * whenever RFC 4180 requires it. Numeric values stay numeric (e.g. -5 is
 * never prefixed).
 */
export function csvCell(value: string | number): string {
  if (typeof value === 'number') {
    return String(value);
  }
  const safe = neutralizeFormula(value);
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

/**
 * Format a single tab-separated cell for clipboard paste into spreadsheets.
 * Neutralizes formula-leading strings while leaving numbers untouched.
 */
export function tsvCell(value: string | number): string {
  if (typeof value === 'number') {
    return String(value);
  }
  const safe = neutralizeFormula(value);
  return /[\t"\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}
