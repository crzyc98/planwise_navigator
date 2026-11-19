import { describe, expect, it, vi } from 'vitest';
import { applyConfigToFormData, draftFromBaseline } from './ConfigContext';
import { DEFAULT_FORM_DATA } from './constants';
import {
  censusRateStatus, describeMinimumWage, minimumWageFromConfig, minimumWageIssues, minimumWagePayload, minimumWageSaveErrors,
  newMinimumWageRow, previewableSteps,
} from './minimumWage';
import { formatSetting } from '../comparisonIntegrity';
import type { MinimumWagePreview } from '../../services/api';
import type { MinimumWageRow } from './types';

vi.mock('../../services/api', () => ({}));

const row = (hourlyRate: number, effectiveDate: string): MinimumWageRow => ({ ...newMinimumWageRow(), hourlyRate, effectiveDate });
const STEPS = [
  { hourly_rate: 20, effective_date: '2026-07-01' },
  { hourly_rate: 22, effective_date: '2027-01-01' },
];

describe('minimum wage steps', () => {
  it('checks the engine contract: rate bounds, a date and one step per year', () => {
    const rows = [row(0, '2026-07-01'), row(501, '2026-01-01'), row(21, ''), row(21, '2026-02-30')];
    const issues = minimumWageIssues(rows, 2025, 2027);
    expect(issues[0].errors).toEqual([
      'Enter a new minimum above $0 and up to $500 an hour.',
      'Only one step per calendar year: another step is also in 2026.',
    ]);
    expect(issues[1].errors).toContain('Enter a new minimum above $0 and up to $500 an hour.');
    expect(issues[2].errors).toEqual(['Choose an effective date.']);
    expect(issues[3].errors).toEqual(['Choose an effective date.']);
    expect(minimumWageSaveErrors(rows, 2025, 2027)[0]).toBe('Minimum wage step 1: Enter a new minimum above $0 and up to $500 an hour.');
  });

  it('warns, without blocking, when a step falls outside the simulated years', () => {
    const rows = [row(21, '2030-01-01')];
    expect(minimumWageIssues(rows, 2025, 2027)[0]).toEqual({
      errors: [],
      warnings: ["The effective date is outside the simulated years 2025–2027, so this step won't apply in this run."],
    });
    expect(minimumWageSaveErrors(rows, 2025, 2027)).toEqual([]);
  });

  it('saves steps in date order and previews only complete ones', () => {
    const rows = [row(22, '2027-01-01'), row(20, '2026-07-01'), row(0, '')];
    expect(minimumWagePayload(rows.slice(0, 2))).toEqual(STEPS);
    expect(previewableSteps(rows, 2025, 2029)).toEqual(STEPS);
  });

  it('leaves steps outside the simulated years out of the preview', () => {
    const rows = [row(30, '2024-07-01'), row(20, '2026-07-01')];
    expect(previewableSteps(rows, 2025, 2027)).toEqual([{ hourly_rate: 20, effective_date: '2026-07-01' }]);
  });

  it('reads saved steps back as rows', () => {
    const rows = minimumWageFromConfig(STEPS)!;
    expect(minimumWagePayload(rows)).toEqual(STEPS);
    expect(minimumWageFromConfig(undefined)).toBeUndefined();
  });

  it('describes one step, several and none', () => {
    expect(describeMinimumWage([])).toBe('none');
    expect(describeMinimumWage([row(21, '2026-07-01')])).toBe('$21.00 an hour from Jul 1, 2026');
    expect(describeMinimumWage(minimumWageFromConfig(STEPS)!)).toBe('2 steps: $20.00 from Jul 1, 2026; $22.00 from Jan 1, 2027');
  });

  it('reads as "none" against a scenario without one in the comparison', () => {
    expect(formatSetting('compensation.minimum_wage', undefined)).toBe('none');
    expect(formatSetting('compensation.minimum_wage', [STEPS[0]])).toBe('$20.00 an hour from Jul 1, 2026');
  });
});

describe('saving a scenario', () => {
  const scope = { isScenario: true };
  const baselineFor = (config: Record<string, unknown>) => {
    const form = applyConfigToFormData(config, DEFAULT_FORM_DATA);
    return { config, form, promotionHazardConfig: null, bandConfig: null };
  };

  it('writes no minimum_wage key when the block is untouched', () => {
    const baseline = baselineFor({ compensation: { merit_budget: 0.03 } });
    expect(draftFromBaseline(baseline, baseline, scope, {})).toEqual({ compensation: { merit_budget: 0.03 } });
    const edited = { ...baseline, form: { ...baseline.form, meritBudget: 4 } };
    expect(draftFromBaseline(baseline, edited, scope, {}).compensation).not.toHaveProperty('minimum_wage');
  });

  it('writes the steps when added, and keeps them as saved on reload', () => {
    const baseline = baselineFor({});
    const added = { ...baseline, form: { ...baseline.form, minimumWage: [row(22, '2027-01-01'), row(20, '2026-07-01')] } };
    const draft = draftFromBaseline(baseline, added, scope, {});
    expect(draft.compensation.minimum_wage).toEqual(STEPS);
    const reloaded = baselineFor(draft);
    expect(minimumWagePayload(reloaded.form.minimumWage)).toEqual(STEPS);
    expect(draftFromBaseline(reloaded, reloaded, scope, {})).toEqual(draft);
  });
});

describe('census hourly rates', () => {
  const preview = (summary: MinimumWagePreview['hourly_rate_summary']): MinimumWagePreview => ({
    headcount: 100, hourly_rate_summary: summary, columns_needed: ['hourly_rate', 'hours_worked', 'scheduled_hours_per_week'], steps: [],
  });
  const summary = {
    columns_present: ['hours_worked'], with_rate: 60, blank: 40, out_of_bounds: 0, multiple_columns: 0,
    minimum_rate: 7.25, maximum_rate: 500, by_source: { hours_worked: 60 },
  };
  const status = (data: MinimumWagePreview | null, error = '', pending = false, path = 'data/census.parquet') =>
    censusRateStatus(path, { data, error, pending });

  it('is ready when some census rows have a rate', () => {
    expect(status(preview(summary))).toEqual({ kind: 'ready', headcount: 100, withRate: 60 });
  });

  it('is off without hourly columns, or when none of their rates is usable', () => {
    expect(status(preview(null))).toMatchObject({ kind: 'no_rates', columnsPresent: [] });
    expect(status(preview({ ...summary, with_rate: 0, blank: 100, by_source: {} }))).toMatchObject({
      kind: 'no_rates', columnsPresent: ['hours_worked'], minimumRate: 7.25, maximumRate: 500,
    });
  });

  it('waits for a census and for the check', () => {
    expect(status(null, '', false, '')).toEqual({ kind: 'no_census' });
    expect(status(null, '', true)).toEqual({ kind: 'checking' });
    expect(status(null, 'File not found')).toEqual({ kind: 'error', message: 'File not found' });
  });
});
