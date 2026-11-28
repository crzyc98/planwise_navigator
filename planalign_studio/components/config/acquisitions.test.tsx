import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_FORM_DATA } from './constants';
import { buildConfigPayload } from './buildConfigPayload';
import { applyConfigToFormData, draftFromBaseline } from './ConfigContext';
import { AcquisitionsSection } from './AcquisitionsSection';
import {
  acquisitionId, acquisitionIssues, acquisitionSaveErrors, acquisitionsFromConfig, acquisitionsPayload, describeOverrides,
  estimatedAnnualPay, newAcquisitionRow, renameAcquisition, staffAveragePay,
} from './acquisitions';
import { formatSetting, summarizeIntegrity } from '../comparisonIntegrity';
import type { AcquisitionRow, FormData } from './types';

const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('./ConfigContext', async importOriginal => ({
  ...(await importOriginal<typeof import('./ConfigContext')>()),
  useConfigContext: () => state.value,
}));

const acme: AcquisitionRow = { ...newAcquisitionRow(), rowKey: 'row-acme', id: 'acme', name: 'Acme Corp', headcount: 250, effectiveDate: '2026-07-01' };
const form = (acquisitions: AcquisitionRow[]): FormData => ({ ...structuredClone(DEFAULT_FORM_DATA), startYear: 2025, endYear: 2027, acquisitions });
const target = { isScenario: true };

describe('acquisition ids', () => {
  it('derives a valid, unique id from the name', () => {
    expect(acquisitionId('Acme Corp. (West)', new Set())).toBe('acme-corp-west');
    expect(acquisitionId('Acme Corp', new Set(['acme-corp']))).toBe('acme-corp-2');
    expect(acquisitionId('!!!', new Set())).toBe('acquisition');
    expect(acquisitionId('x'.repeat(40), new Set(['x'.repeat(32)]))).toMatch(/^x{30}-2$/);
  });

  it('follows the name until saved, then stays fixed', () => {
    const draft = renameAcquisition([{ ...acme, id: '' }], 0, 'Beta Inc', new Set());
    expect(draft[0].id).toBe('beta-inc');
    const renamed = renameAcquisition([acme], 0, 'Acme Holdings', new Set(['acme']));
    expect(renamed[0]).toEqual({ ...acme, name: 'Acme Holdings' });
  });
});

describe('acquisition validation', () => {
  const errors = (rows: AcquisitionRow[]) => acquisitionIssues(rows, 2025, 2027).map(item => item.errors);
  const outsideYears = "The effective date is outside the simulated years 2025–2027, so this group won't join in this run.";

  it('accepts a valid group', () => {
    expect(acquisitionIssues([acme], 2025, 2027)).toEqual([{ errors: [], warnings: [] }]);
  });

  it('rejects bad headcounts, missing dates, names and duplicates', () => {
    const rows = [acme, { ...acme, id: 'acme-2', name: 'acme corp ', headcount: 0 }];
    expect(errors(rows)[1]).toEqual(['Use a different name for each acquisition.', 'Enter a headcount from 1 to 99,999.']);
    expect(errors([{ ...acme, headcount: 100_000, effectiveDate: '' }])[0])
      .toEqual(['Enter a headcount from 1 to 99,999.', 'Choose an effective date.']);
    expect(errors([{ ...acme, effectiveDate: '2026-02-30' }])[0]).toEqual(['Choose an effective date.']);
    expect(errors([{ ...acme, name: '' }])[0]).toEqual(['Enter a name.']);
    expect(errors([acme, { ...acme, name: 'Other' }])[1]).toEqual(['Another acquisition already uses the id "acme".']);
  });

  it('warns about a date outside the simulated years without blocking the save', () => {
    const late = { ...acme, effectiveDate: '2029-01-01' };
    expect(acquisitionIssues([late], 2025, 2027)).toEqual([{ errors: [], warnings: [outsideYears] }]);
    expect(acquisitionSaveErrors([late], 2025, 2027)).toEqual([]);
  });

  it('names the group in save errors', () => {
    expect(acquisitionSaveErrors([{ ...acme, headcount: 0 }], 2025, 2027))
      .toEqual(['Acquisition Acme Corp: Enter a headcount from 1 to 99,999.']);
  });
});

describe('acquisition config round trip', () => {
  const saved = { workforce: { acquisitions: [{ id: 'acme', name: 'Acme Corp', headcount: 250, effective_date: '2026-07-01' }] } };

  it('reloads saved values and writes the same config', () => {
    const loaded = applyConfigToFormData(saved, DEFAULT_FORM_DATA);
    expect(loaded.acquisitions).toEqual([{ ...acme, rowKey: expect.any(String) }]);
    expect(buildConfigPayload(loaded, null, null).workforce.acquisitions).toEqual(saved.workforce.acquisitions);
  });

  it('gives each loaded row its own client-only key, never saved', () => {
    const twice = { workforce: { acquisitions: [...saved.workforce.acquisitions, { ...saved.workforce.acquisitions[0], id: 'acme-2', name: 'Acme 2' }] } };
    const loaded = applyConfigToFormData(twice, DEFAULT_FORM_DATA);
    expect(new Set(loaded.acquisitions.map(row => row.rowKey)).size).toBe(2);
    expect(buildConfigPayload(loaded, null, null).workforce.acquisitions[0]).not.toHaveProperty('rowKey');
  });

  it('falls back to the id for a group saved without a name', () => {
    const loaded = applyConfigToFormData({ workforce: { acquisitions: [{ id: 'beta', headcount: 5, effective_date: '2026-01-01' }] } }, DEFAULT_FORM_DATA);
    expect(loaded.acquisitions[0].name).toBe('beta');
  });

  it('leaves a config without acquisitions untouched', () => {
    const baseline = { config: { workforce: { total_termination_rate: 0.1 } }, form: form([]), promotionHazardConfig: null, bandConfig: null };
    const edited = { ...form([]), seed: 7 };
    const draft = draftFromBaseline(baseline, { form: edited, promotionHazardConfig: null, bandConfig: null }, target, {});
    expect(draft.workforce).toEqual({ total_termination_rate: 0.1 });
  });

  it('adds and removes acquisitions as explicit edits', () => {
    const added = draftFromBaseline({ config: {}, form: form([]), promotionHazardConfig: null, bandConfig: null },
      { form: form([acme]), promotionHazardConfig: null, bandConfig: null }, target, {});
    expect(added.workforce).toEqual({ acquisitions: saved.workforce.acquisitions });
    const removed = draftFromBaseline({ config: saved, form: form([acme]), promotionHazardConfig: null, bandConfig: null },
      { form: form([]), promotionHazardConfig: null, bandConfig: null }, target, {});
    expect(removed.workforce).toEqual({ acquisitions: [] });
  });
});

describe('acquisitions editor', () => {
  beforeEach(() => {
    state.value = { formData: form([]), setFormData: vi.fn(), savedFormData: null };
  });

  it('is collapsed and says none when the scenario has no acquisitions', () => {
    const html = renderToStaticMarkup(<AcquisitionsSection />);
    expect(html).toContain('Acquisitions');
    expect(html).toContain(': none.');
    expect(html).not.toContain('role="alert"');
  });

  it('previews each group and the total, with inline errors', () => {
    state.value.formData = form([acme, { ...acme, rowKey: 'row-beta', id: 'beta', name: 'Beta', headcount: 50, effectiveDate: '2030-01-01' }, { ...acme, rowKey: 'row-bad', id: 'bad', name: 'Bad', headcount: 0 }]);
    const html = renderToStaticMarkup(<AcquisitionsSection />);
    expect(html).toContain('3 groups, 300 people');
    expect(html).toContain('Acme Corp: 250 people join on');
    expect(html).toContain('Total: 300 people');
    expect(html).toContain('so this group won&#x27;t join in this run.');
    expect(html).toContain('Some acquisitions fall outside the simulated years');
    expect(html).toContain('Enter a headcount from 1 to 99,999.');
    expect(html).toContain('Some acquisitions need attention before saving.');
  });
});

describe('acquisitions in comparisons', () => {
  it('says when only one side has acquisitions', () => {
    expect(formatSetting('workforce.acquisitions', null)).toBe('none');
    expect(formatSetting('workforce.acquisitions', [
      { id: 'acme', name: 'Acme', headcount: 250, effective_date: '2026-07-01' },
      { id: 'beta', name: 'Beta', headcount: 50, effective_date: '2027-01-01' },
    ])).toBe('Acme: 250 on 2026-07-01; Beta: 50 on 2027-01-01');
    const [line] = summarizeIntegrity({
      anchor_scenario_id: 'a', anchor_scenario_name: 'Baseline', anchor_engine_version: null,
      scenarios: [{
        scenario_id: 'b', scenario_name: 'With Acme', verdict: 'not_like_for_like', unevaluated: [], plan_design_differences: [], engine_version: null,
        reasons: [{ code: 'config_differs', effect: 'breaks', path: 'workforce.acquisitions', group: 'workforce_and_pay',
          anchor_value: null, scenario_value: [{ id: 'acme', headcount: 250, effective_date: '2026-07-01' }], files: [], scenario_id: null }],
      }],
    }).lines;
    expect(line.details).toEqual(['Acquisitions: none vs acme: 250 on 2026-07-01']);
  });
});

// --- Slice 2: plan settings, overrides, unknown keys, pay estimate ---------

const FULL = {
  id: 'acme', name: 'Acme Corp', headcount: 250, effective_date: '2026-07-01',
  service_credit: 'acquisition_date', plan_entry: 'waiting_period', join_year_hours_credit: 'full_year',
  starting_participation_rate: 0.07, starting_deferral_rate: 0.055,
  relative_pay: 0.9, average_age: 44, average_service: 7.5,
};

describe('acquisition plan settings and overrides', () => {
  it('reloads every setting and override and writes the same config', () => {
    const loaded = applyConfigToFormData({ workforce: { acquisitions: [FULL] } }, DEFAULT_FORM_DATA);
    expect(loaded.acquisitions[0]).toMatchObject({
      serviceCredit: 'acquisition_date', planEntry: 'waiting_period', joinYearHoursCredit: 'full_year', startingParticipationPct: 7, startingDeferralPct: 5.5,
      pay: { kind: 'relative', percentOfStaff: 90 }, averageAge: 44, averageService: 7.5,
    });
    expect(buildConfigPayload(loaded, null, null).workforce.acquisitions).toEqual([FULL]);
    const amount = { ...FULL, relative_pay: undefined, average_pay: 82_500 };
    delete amount.relative_pay;
    expect(acquisitionsPayload(acquisitionsFromConfig([amount]) ?? [])).toEqual([amount]);
  });

  it('writes nothing new for a group at the defaults', () => {
    const plain = { id: 'acme', name: 'Acme Corp', headcount: 250, effective_date: '2026-07-01' };
    expect(acquisitionsPayload(acquisitionsFromConfig([plain]) ?? [])).toEqual([plain]);
    expect(acquisitionsPayload([acme])).toEqual([plain]);
  });

  it('keeps keys Studio does not edit when saving', () => {
    const fromYaml = { ...FULL, hourly_rate_source: 'census', notes: { owner: 'finance' } };
    const [row] = acquisitionsFromConfig([fromYaml]) ?? [];
    expect(acquisitionsPayload([{ ...row, headcount: 300 }])).toEqual([{ ...fromYaml, headcount: 300 }]);
  });

  it('validates override and participation ranges', () => {
    const errors = (row: AcquisitionRow) => acquisitionIssues([row], 2025, 2027)[0].errors;
    expect(errors({ ...acme, pay: { kind: 'relative', percentOfStaff: 5 } })).toEqual(['Enter pay from 10% to 1,000% of existing staff.']);
    expect(errors({ ...acme, pay: { kind: 'amount', averagePay: 0 } })).toEqual(['Enter an average pay above $0 and up to $10,000,000.']);
    expect(errors({ ...acme, averageAge: 17 })).toEqual(['Enter an average age from 18 to 80.']);
    expect(errors({ ...acme, averageAge: 30, averageService: 13 })).toEqual(['Average service can be at most average age minus 18.']);
    expect(errors({ ...acme, startingParticipationPct: 50, startingDeferralPct: null }))
      .toEqual(['Enter their average deferral rate, above 0% and up to 100%.']);
    expect(errors({ ...acme, startingParticipationPct: 50, startingDeferralPct: 6, averageAge: 40, averageService: 10 })).toEqual([]);
  });

  it('describes the group as mirroring staff unless overridden', () => {
    expect(describeOverrides(acme)).toBe('Mirrors existing staff');
    expect(describeOverrides({ ...acme, pay: { kind: 'relative', percentOfStaff: 90 }, averageAge: 44 }))
      .toBe('Pay 90% of staff, average age 44');
    expect(describeOverrides({ ...acme, pay: { kind: 'relative', percentOfStaff: Number.NaN } }))
      .toBe('Pay relative to staff, not yet set');
  });
});

describe('acquisition pay estimate', () => {
  it('uses headcount × staff average pay, adjusted by a pay override', () => {
    expect(estimatedAnnualPay(acme, 80_000)).toBe(20_000_000);
    expect(estimatedAnnualPay({ ...acme, pay: { kind: 'relative', percentOfStaff: 90 } }, 80_000)).toBe(18_000_000);
    expect(estimatedAnnualPay({ ...acme, pay: { kind: 'amount', averagePay: 50_000 } }, null)).toBe(12_500_000);
    expect(estimatedAnnualPay(acme, null)).toBeNull();
    expect(estimatedAnnualPay({ ...acme, pay: { kind: 'relative', percentOfStaff: Number.NaN } }, 80_000)).toBeNull();
  });

  it('reads staff average pay from the census analysis', () => {
    expect(staffAveragePay({
      levels: [
        { level: 1, name: 'L1', employee_count: 3, avg_compensation: 50_000, median_compensation: 0, min_compensation: 0, max_compensation: 0, p25_compensation: 0, p75_compensation: 0, raw_min_compensation: 0, raw_max_compensation: 0 },
        { level: 2, name: 'L2', employee_count: 1, avg_compensation: 90_000, median_compensation: 0, min_compensation: 0, max_compensation: 0, p25_compensation: 0, p75_compensation: 0, raw_min_compensation: 0, raw_max_compensation: 0 },
      ],
      overall_stats: null,
    })).toBe(60_000);
    expect(staffAveragePay({ levels: null, overall_stats: { avg_compensation: 70_000, median_compensation: 0, min_compensation: 0, max_compensation: 0, p10_compensation: 0, p25_compensation: 0, p75_compensation: 0, p90_compensation: 0 } })).toBe(70_000);
  });
});

describe('acquisitions editor, slice 2', () => {
  beforeEach(() => {
    state.value = { formData: form([]), setFormData: vi.fn(), savedFormData: null, activeWorkspace: { id: 'ws' } };
  });

  it('shows plan settings with defaults and a collapsed override section', () => {
    state.value.formData = form([acme]);
    const html = renderToStaticMarkup(<AcquisitionsSection />);
    expect(html).toContain('Keep service from the acquired company');
    expect(html).toContain('Enter the plan on the acquisition date');
    expect(html).toContain('Count hours from the acquisition date');
    expect(html).toContain('Auto-enroll like new hires');
    expect(html).toContain('Who they are: </span>Mirrors existing staff');
    expect(html).not.toContain('<details class="rounded-md border border-border p-3" open');
    expect(html).toContain('Load a census file to estimate pay');
  });

  it('estimates pay for a set amount without a census', () => {
    state.value.formData = form([{ ...acme, pay: { kind: 'amount', averagePay: 60_000 } }]);
    const html = renderToStaticMarkup(<AcquisitionsSection />);
    expect(html).toMatch(/about \$15M a year in pay/);
  });
});

describe('acquisition settings in comparisons', () => {
  it('names the settings that differ from the defaults', () => {
    expect(formatSetting('workforce.acquisitions', [FULL]))
      .toBe('Acme Corp: 250 on 2026-07-01 (service from the acquisition date; waiting period before entry; full year of hours in the join year; 7% participating at 5.5%; pay 90% of staff, average age 44, average service 7.5 years)');
  });
});
