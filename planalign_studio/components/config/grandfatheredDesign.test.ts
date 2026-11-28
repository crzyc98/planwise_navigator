import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { applyConfigToFormData, draftFromBaseline } from './ConfigContext';
import { buildConfigPayload } from './buildConfigPayload';
import { DEFAULT_FORM_DATA } from './constants';
import { designParameters } from './designParameters';
import { grandfatheredDesignFromConfig, grandfatheredDesignPayload, inheritedDesignIds, mergedDesignConfig, newGrandfatheredDesign } from './grandfatheredDesign';
import { grandfatheredDesignErrors } from './grandfatheredDesignValidation';
import { newHireScope } from './newHireScope';
import type { FormData, GrandfatheredDesignForm } from './types';

type Json = Record<string, unknown>;
const payload = (form: FormData) => buildConfigPayload(form, null, null) as Json;
const target = { isScenario: true };
const json = (value: unknown): Json => JSON.parse(JSON.stringify(value));

/** Match-only change: new hires get 50% on the first 6%; core stays 1% flat. */
function withDesign(changes: Partial<GrandfatheredDesignForm> = {}, form: FormData = DEFAULT_FORM_DATA): FormData {
  const design = newGrandfatheredDesign(form);
  return { ...form, dcGrandfather: {
    ...design, cutoff: '2015-01-01',
    newHireFormula: { ...design.newHireFormula, dcMatchTiers: [{ deferralMin: 0, deferralMax: 6, matchRate: 50 }],
      dcCoreContributionRate: 3 },
    ...changes,
  } };
}

/** Load a saved config the way Studio does (without engine resolution). */
function load(config: Json): FormData {
  const form = applyConfigToFormData(config, DEFAULT_FORM_DATA);
  return { ...form, dcGrandfather: grandfatheredDesignFromConfig(mergedDesignConfig(config, undefined), form) };
}

const save = (config: Json, before: FormData, after: FormData) => draftFromBaseline(
  { config, form: before, promotionHazardConfig: null, bandConfig: null },
  { form: after, promotionHazardConfig: null, bandConfig: null }, target, {});

describe('grandfathered design payload', () => {
  it('adds nothing to the single-design payload when the feature is unused', () => {
    const { dcGrandfather, ...legacyForm } = DEFAULT_FORM_DATA;
    expect(dcGrandfather).toBeNull();
    const emitted = payload(DEFAULT_FORM_DATA);
    expect(emitted).not.toHaveProperty('plan_design_assignment');
    expect(emitted).not.toHaveProperty('plan_design_parameters');
    expect(JSON.stringify(emitted)).toBe(JSON.stringify(payload(legacyForm as FormData)));
    expect(JSON.stringify(payload({ ...DEFAULT_FORM_DATA, dcGrandfather: { ...newGrandfatheredDesign(DEFAULT_FORM_DATA), enabled: false } })))
      .toBe(JSON.stringify(emitted));
  });

  it('emits one cutoff rule and two complete designs in the engine contract', () => {
    const emitted = payload(withDesign());
    expect(emitted.plan_design_assignment).toEqual({
      default_plan_design_id: 'existing_employees',
      rules: [{ type: 'hire_date_cutoff', cutoff: '2015-01-01', plan_design_id: 'new_hires' }],
    });
    const designs = emitted.plan_design_parameters as Record<string, Json>;
    expect(Object.keys(designs)).toEqual(['existing_employees', 'new_hires']);
    expect(designs.existing_employees).toEqual(designParameters(DEFAULT_FORM_DATA));
    expect(designs.new_hires.match).toEqual({ family: 'deferral_based', match_template: 'tiered', cap_percent: 0.03,
      tiers: [{ employee_min: 0, employee_max: 0.06, match_rate: 0.5 }] });
    // Match-only: core is not changed for new hires.
    expect(designs.new_hires.employer_core).toEqual(designs.existing_employees.employer_core);
    for (const key of ['auto_enrollment', 'deferral_escalation', 'eligibility']) {
      expect(designs.new_hires[key]).toEqual(designs.existing_employees[key]);
    }
    expect(designs.existing_employees.eligibility).toEqual({ waiting_period_days: 90 });
  });

  it.each([
    ['core only', { changeMatch: false, changeCore: true }, false, true],
    ['match and core', { changeMatch: true, changeCore: true }, true, true],
  ])('supports %s', (_label, changes, matchDiffers, coreDiffers) => {
    const designs = payload(withDesign(changes)).plan_design_parameters as Record<string, Json>;
    expect(designs.new_hires.match).toEqual(matchDiffers ? expect.objectContaining({ cap_percent: 0.03 }) : designs.existing_employees.match);
    expect(designs.new_hires.employer_core).toEqual(coreDiffers
      ? expect.objectContaining({ family: 'flat', contribution_rate: 0.03 }) : designs.existing_employees.employer_core);
  });

  it('keeps schedule units: service rates as fractions, age and points rates as percents', () => {
    const form = withDesign({ changeMatch: false, changeCore: true });
    form.dcGrandfather!.newHireFormula = { ...form.dcGrandfather!.newHireFormula, dcCoreStatus: 'age_banded',
      dcCoreAgeSchedule: [{ minAge: 0, maxAge: 40, rate: 2 }, { minAge: 40, maxAge: null, rate: 4 }] };
    const core = (payload(form).plan_design_parameters as Record<string, Json>).new_hires.employer_core;
    expect(core).toMatchObject({ family: 'age_banded', age_schedule: [{ min_age: 0, max_age: 40, rate: 2 }, { min_age: 40, max_age: null, rate: 4 }] });
    form.dcGrandfather!.newHireFormula.dcCoreStatus = 'graded_by_service';
    form.dcGrandfather!.newHireFormula.dcCoreGradedSchedule = [{ serviceYearsMin: 0, serviceYearsMax: null, rate: 2.5 }];
    expect((payload(form).plan_design_parameters as Record<string, Json>).new_hires.employer_core)
      .toMatchObject({ graded_schedule: [{ min_years: 0, max_years: null, rate: 0.025 }] });
  });

  it('matches the checked-in payload the engine simulation test runs', () => {
    const fixture = JSON.parse(readFileSync(new URL('../../../tests/fixtures/studio_grandfathered_design/payload.json', import.meta.url), 'utf8'));
    const { plan_design_assignment, plan_design_parameters } = payload(withDesign({ changeCore: true }));
    expect(json({ plan_design_assignment, plan_design_parameters })).toEqual(fixture);
  });
});

describe('grandfathered design load, edit, save and copy', () => {
  // Settings Studio does not model must survive every save.
  const withExtras = (config: Json): Json => ({ ...config, custom: { retain: true },
    dc_plan: { ...(config.dc_plan as Json), studio_unmodelled_note: 'keep' } });

  it('loads a saved two-design configuration back into the editor', () => {
    const form = withDesign({ changeCore: true });
    const loaded = load(json(payload(form)));
    expect(loaded.dcGrandfather).toEqual({ ...form.dcGrandfather, savedActive: true,
      newHireFormula: expect.objectContaining({ dcMatchTiers: [{ deferralMin: 0, deferralMax: 6, matchRate: 50 }], dcCoreContributionRate: 3 }) });
  });

  it('saves one edited field and keeps every unedited field, then copies unchanged', () => {
    const saved = withExtras(json(payload(withDesign({ changeCore: true }))));
    const loaded = load(saved);
    const edited = structuredClone(loaded);
    edited.dcGrandfather!.newHireFormula.dcMatchTiers[0].matchRate = 75;
    const result = save(saved, loaded, edited);
    const expected = structuredClone(saved) as Json & { plan_design_parameters: Record<string, Json & { match: { tiers: Json[]; cap_percent: number } }> };
    expected.plan_design_parameters.new_hires.match.tiers[0].match_rate = 0.75;
    expected.plan_design_parameters.new_hires.match.cap_percent = 0.045;
    expect(result).toEqual(expected);
    // Copy to another scenario: load the saved overrides as the baseline and save without edits.
    const copied = load(result);
    expect(save(result, copied, copied)).toEqual(result);
  });

  it('applies a plan-wide edit to both designs', () => {
    const saved = json(payload(withDesign()));
    const loaded = load(saved);
    const result = save(saved, loaded, { ...loaded, dcDefaultDeferral: 6 }) as { plan_design_parameters: Record<string, Json & { auto_enrollment: Json }> };
    expect(result.plan_design_parameters.existing_employees.auto_enrollment.default_deferral_rate).toBe(0.06);
    expect(result.plan_design_parameters.new_hires.auto_enrollment.default_deferral_rate).toBe(0.06);
  });

  it('turning off a saved setup clears it on save and keeps everything else', () => {
    const saved = withExtras(json(payload(withDesign())));
    const loaded = load(saved);
    const off = { ...loaded, dcGrandfather: { ...loaded.dcGrandfather!, enabled: false } };
    expect(save(saved, loaded, off)).toEqual({ ...saved, plan_design_assignment: null, plan_design_parameters: null });
    // Re-enabling before saving restores the same designs.
    expect(save(saved, loaded, { ...off, dcGrandfather: { ...off.dcGrandfather, enabled: true } })).toEqual(saved);
  });

  it('keeps a setup it cannot edit exactly as saved', () => {
    const saved = json(payload(withDesign()));
    const assignment = saved.plan_design_assignment as { rules: Json[] };
    assignment.rules.push({ type: 'hire_date_cutoff', cutoff: '2020-01-01', plan_design_id: 'existing_employees' });
    const loaded = load(saved);
    expect(loaded.dcGrandfather).toBeNull();
    expect(save(saved, loaded, { ...loaded, dcMatchMinHoursAnnual: 500 }))
      .toEqual({ ...saved, dc_plan: { ...(saved.dc_plan as Json), match_min_hours_annual: 500 } });
  });

  it('does not offer to edit designs whose shared terms differ', () => {
    const saved = json(payload(withDesign()));
    ((saved.plan_design_parameters as Record<string, Json>).new_hires.eligibility as Json).waiting_period_days = 0;
    expect(load(saved).dcGrandfather).toBeNull();
  });

  it('reads scenario overrides over the workspace and treats null as cleared', () => {
    const workspace = json(payload(withDesign()));
    expect(mergedDesignConfig(workspace, { plan_design_assignment: null, plan_design_parameters: null }))
      .toEqual({ plan_design_assignment: null, plan_design_parameters: null });
    expect(mergedDesignConfig(workspace, undefined)).toEqual({
      plan_design_assignment: workspace.plan_design_assignment, plan_design_parameters: workspace.plan_design_parameters });
  });
});

describe('grandfathered design validation', () => {
  const errors = (changes: Partial<GrandfatheredDesignForm> = {}, form?: FormData) => grandfatheredDesignErrors(withDesign(changes, form));
  const newHire = (formula: Partial<GrandfatheredDesignForm['newHireFormula']>, changes: Partial<GrandfatheredDesignForm> = {}) => {
    const form = withDesign({ changeCore: true, ...changes });
    form.dcGrandfather!.newHireFormula = { ...form.dcGrandfather!.newHireFormula, ...formula };
    return grandfatheredDesignErrors(form);
  };

  it('accepts a complete setup and ignores the feature when off', () => {
    expect(errors()).toEqual([]);
    expect(errors({ enabled: false, cutoff: '' })).toEqual([]);
    expect(grandfatheredDesignErrors(DEFAULT_FORM_DATA)).toEqual([]);
  });

  it.each(['', '2026-02-30', '2026-13-01', '01/01/2026'])('rejects the cutoff %j', cutoff => {
    expect(errors({ cutoff })).toEqual(['Enter the hire-date cutoff as a full date, for example 2026-01-01.']);
  });

  it('rejects missing, invalid and duplicate design names', () => {
    expect(errors({ existingDesignId: '' })).toEqual(['Enter a name for the existing-employee design.']);
    expect(errors({ newHireDesignId: '  ' })).toEqual(['Enter a name for the new-hire design.']);
    expect(errors({ newHireDesignId: "new'hires" })[0]).toMatch(/new-hire design name "new'hires" can use only letters/);
    expect(errors({ newHireDesignId: 'existing_employees' })).toEqual(['Give the existing-employee and new-hire designs different names.']);
  });

  it('requires a scenario to reuse the design names its workspace defines', () => {
    const workspace = json(payload(withDesign()));
    const inherited = inheritedDesignIds(workspace, true);
    expect(inherited).toEqual(['existing_employees', 'new_hires']);
    expect(inheritedDesignIds(workspace, false)).toEqual([]);
    expect(grandfatheredDesignErrors(withDesign(), inherited)).toEqual([]);
    expect(grandfatheredDesignErrors(withDesign({ newHireDesignId: 'hired_2026' }), inherited)).toEqual([
      'The workspace already defines plan designs named “existing_employees” and “new_hires”. Use the same names in this scenario: a scenario adds to the workspace’s designs rather than replacing them.',
    ]);
  });

  it('requires something to differ for new hires', () => {
    expect(errors({ changeMatch: false })).toEqual(['Choose what is different for new hires: the employer match, the core contribution, or both.']);
  });

  it.each([
    [{ dcMatchTiers: [] }, 'New hires’ match: add at least one tier.'],
    [{ dcMatchTiers: [{ deferralMin: 0, deferralMax: 6, matchRate: 150 }] }, 'New hires’ match: rates must be between 0% and 100%.'],
    [{ dcMatchTiers: [{ deferralMin: 3, deferralMax: 3, matchRate: 50 }] }, 'New hires’ match: each tier must end above where it starts.'],
    [{ dcMatchTiers: [{ deferralMin: 0, deferralMax: 4, matchRate: 50 }, { deferralMin: 3, deferralMax: 6, matchRate: 50 }] }, 'New hires’ match: tiers overlap.'],
    [{ dcMatchMode: 'tenure_graded', dcTenureGradedBands: [] }, 'New hires’ match: add at least one service band.'],
    [{ dcMatchMode: 'points_based', dcPointsMatchTiers: [] }, 'New hires’ match: add at least one tier.'],
    [{ dcMatchMode: 'legacy_formula' }, 'New hires’ match: the saved calculation mode "legacy_formula" can\'t be used in a two-design plan. Choose one of the listed modes.'],
    [{ dcCoreStatus: 'graded_by_service', dcCoreGradedSchedule: [] }, 'New hires’ core contribution: add at least one tier.'],
    [{ dcCoreStatus: 'custom' }, 'New hires’ core contribution: the saved contribution type "custom" can\'t be used in a two-design plan. Choose one of the listed types.'],
    [{ dcCoreContributionRate: 120 }, 'New hires’ core contribution: the rate must be between 0% and 100%.'],
    [{ dcCoreIntegrationEnabled: true, dcCoreIntegrationLevelMode: 'fixed_dollar' as const, dcCoreIntegrationLevelValue: null }, 'New hires’ core contribution: enter the Social Security integration level.'],
  ])('reports an incomplete new-hire formula %#', (formula, message) => {
    expect(newHire(formula)).toEqual([message]);
  });

  it('checks the existing-employee formula against the engine limits too', () => {
    const form = { ...DEFAULT_FORM_DATA, dcMatchTiers: [{ deferralMin: 0, deferralMax: 3, matchRate: 200 }] };
    expect(errors({}, form)).toContain('Existing employees’ match: rates must be between 0% and 100%.');
  });

  it('ignores the parts new hires do not change', () => {
    expect(newHire({ dcCoreStatus: 'custom' }, { changeCore: false })).toEqual([]);
  });

  it('rejects an automatic increase larger than its cap', () => {
    expect(errors({}, { ...DEFAULT_FORM_DATA, dcEscalationRate: 12, dcEscalationCap: 10 }))
      .toEqual(['Automatic contribution increases: the yearly increase can’t be larger than the cap.']);
  });
});

describe('new-hire formula scope', () => {
  it('edits only the new-hire formula', () => {
    let form = withDesign();
    const scope = () => newHireScope({ formData: form, setFormData: update => { form = update(form); },
      handleChange: () => undefined, inputProps: name => ({ name, value: undefined, onChange: () => undefined }) });
    expect(scope().formData.dcMatchTiers).toEqual([{ deferralMin: 0, deferralMax: 6, matchRate: 50 }]);
    scope().setFormData(previous => ({ ...previous, dcMatchTiers: [{ deferralMin: 0, deferralMax: 4, matchRate: 100 }], dcAutoEnroll: false }));
    scope().handleChange({ target: { name: 'dcCoreStatus', value: 'age_banded', type: 'select-one' } } as React.ChangeEvent<HTMLSelectElement>);
    scope().handleChange({ target: { name: 'dcAutoEscalation', checked: false, type: 'checkbox' } } as React.ChangeEvent<HTMLInputElement>);
    expect(form.dcGrandfather!.newHireFormula).toMatchObject({ dcMatchTiers: [{ deferralMin: 0, deferralMax: 4, matchRate: 100 }], dcCoreStatus: 'age_banded' });
    expect(form).toMatchObject({ dcMatchTiers: DEFAULT_FORM_DATA.dcMatchTiers, dcCoreStatus: 'flat', dcAutoEnroll: true, dcAutoEscalation: DEFAULT_FORM_DATA.dcAutoEscalation });
  });

  it('turning on starts new hires from a copy of the current formula', () => {
    const design = newGrandfatheredDesign({ ...DEFAULT_FORM_DATA, startYear: 2027 });
    expect(design).toMatchObject({ enabled: true, cutoff: '2027-01-01', changeMatch: true, changeCore: false, savedActive: false });
    expect(design.newHireFormula.dcMatchTiers).toEqual(DEFAULT_FORM_DATA.dcMatchTiers);
    expect(grandfatheredDesignPayload({ ...DEFAULT_FORM_DATA, dcGrandfather: { ...design, enabled: false, savedActive: true } }))
      .toEqual({ plan_design_assignment: null, plan_design_parameters: null });
  });
});
