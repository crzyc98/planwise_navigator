import { describe, expect, it } from 'vitest';
import { applyConfigToFormData } from './ConfigContext';
import { buildConfigPayload } from './buildConfigPayload';
import { applyConfigEdits } from './configEdits';
import { DEFAULT_FORM_DATA } from './constants';
import { applyResolvedFormData } from './resolvedFormData';

const payload = (form: typeof DEFAULT_FORM_DATA) => buildConfigPayload(form, null, null);
const behavior = {
  escalation_mode: 'participant_elected' as const,
  escalation_participant_elected_signup_probability: 0.0125,
  match_magnet_downward_enabled: true,
  below_default_share_tiers: [{ max_auto_enroll_default_rate: 0.03, share: 0.1 }, { max_auto_enroll_default_rate: null, share: 0.15 }],
  below_default_steps: [{ pp: 1, weight: 0.75 }, { pp: 3, weight: 0.25 }],
};

describe('participant behavior payload and inheritance', () => {
  it('loads stored decimal settings as percentages and exports them exactly once', () => {
    const form = applyConfigToFormData({ dc_plan: behavior }, DEFAULT_FORM_DATA);
    expect(form).toMatchObject({ dcEscalationMode: 'participant_elected', dcEscalationSignupProbability: 1.25,
      dcMatchMagnetDownwardEnabled: true,
      dcBelowDefaultShareTiers: [{ max_auto_enroll_default_rate: 3, share: 10 }, { max_auto_enroll_default_rate: null, share: 15 }],
      dcBelowDefaultSteps: [{ pp: 1, weight: 75 }, { pp: 3, weight: 25 }],
    });
    expect(payload(form).dc_plan).toMatchObject(behavior);
    expect(behavior.below_default_steps[0].weight).toBe(0.75);
  });

  it('enables shipped defaults and preserves explicit false and zero overrides', () => {
    expect(payload(DEFAULT_FORM_DATA).dc_plan).toMatchObject({
      escalation_mode: 'automatic', escalation_participant_elected_signup_probability: 0.01,
      match_magnet_downward_enabled: true,
      below_default_share_tiers: [{ max_auto_enroll_default_rate: 0.03, share: 0.10 }, { max_auto_enroll_default_rate: null, share: 0.15 }],
      below_default_steps: [{ pp: 1, weight: 0.5 }, { pp: 2, weight: 0.3 }, { pp: 3, weight: 0.2 }],
    });
    const inherited = applyConfigToFormData({ dc_plan: behavior }, DEFAULT_FORM_DATA);
    const neutral = applyConfigToFormData({ dc_plan: { escalation_mode: 'automatic',
      escalation_participant_elected_signup_probability: 0, match_magnet_downward_enabled: false,
    } }, inherited);
    expect(neutral).toMatchObject({ dcEscalationMode: 'automatic', dcEscalationSignupProbability: 0, dcMatchMagnetDownwardEnabled: false });
    expect(neutral.dcBelowDefaultShareTiers).toEqual(inherited.dcBelowDefaultShareTiers);
  });

  it.each([{}, { simulation: { random_seed: 13 } }, { dc_plan: behavior }])(
    'does not add new keys when an untouched scenario is saved: %j', original => {
      const loaded = applyResolvedFormData({ deferral_escalation_mode: 'participant_elected',
        deferral_escalation_participant_elected_signup_probability: 0.02,
        enrollment_match_magnet_downward_enabled: true,
        below_default_share_tiers: behavior.below_default_share_tiers, below_default_steps: behavior.below_default_steps,
      }, applyConfigToFormData(original, DEFAULT_FORM_DATA));
      const before = payload(loaded);
      expect(applyConfigEdits(original, before, payload(structuredClone(loaded)))).toEqual(original);
      // Saving an unrelated edit must not materialize the displayed inherited values either.
      expect(applyConfigEdits(original, before, payload({ ...loaded, seed: loaded.seed + 1 }))).toEqual({
        ...original, simulation: { ...('simulation' in original ? original.simulation : {}), random_seed: loaded.seed + 1 },
      });
    },
  );

  it('persists just the edited behavior keys in a sparse scenario', () => {
    const loaded = applyResolvedFormData({}, DEFAULT_FORM_DATA);
    const after = { ...loaded, dcEscalationSignupProbability: 1.25, dcMatchMagnetDownwardEnabled: false };
    expect(applyConfigEdits({}, payload(loaded), payload(after))).toEqual({ dc_plan: {
      escalation_participant_elected_signup_probability: 0.0125, match_magnet_downward_enabled: false,
    } });
  });
});

const easyEnroll = {
  easy_enroll_enabled: true,
  easy_enroll_channel_share_without_auto_enrollment: 0.4125,
  easy_enroll_channel_share_with_auto_enrollment: 0.625,
  easy_enroll_packages: [{ rate: 0.065, share: 0.25 }, { rate: 0.09, share: 0.75 }],
  easy_enroll_escalation_cap: 0.125,
};

describe('Easy Enroll payload and inheritance', () => {
  it('loads decimal overrides as percentages and exports all five keys exactly once', () => {
    const form = applyConfigToFormData({ dc_plan: easyEnroll }, DEFAULT_FORM_DATA);
    expect(form).toMatchObject({ dcEasyEnrollEnabled: true, dcEasyEnrollShareWithoutAutoEnrollment: 41.25,
      dcEasyEnrollShareWithAutoEnrollment: 62.5, dcEasyEnrollEscalationCap: 12.5,
      dcEasyEnrollPackages: [{ rate: 6.5, share: 25 }, { rate: 9, share: 75 }],
    });
    expect(payload(form).dc_plan).toMatchObject(easyEnroll);
    expect(easyEnroll.easy_enroll_packages[0]).toEqual({ rate: 0.065, share: 0.25 });
    const inherited = applyConfigToFormData({}, form);
    expect(inherited).toEqual(form);
    expect(applyConfigToFormData({ dc_plan: { easy_enroll_enabled: false,
      easy_enroll_channel_share_with_auto_enrollment: 0, easy_enroll_escalation_cap: 0 } }, form))
      .toMatchObject({ dcEasyEnrollEnabled: false, dcEasyEnrollShareWithAutoEnrollment: 0, dcEasyEnrollEscalationCap: 0 });
  });

  it('matches the shipped defaults', () => {
    expect(payload(DEFAULT_FORM_DATA).dc_plan).toMatchObject({ easy_enroll_enabled: true,
      easy_enroll_channel_share_without_auto_enrollment: 0.45, easy_enroll_channel_share_with_auto_enrollment: 0.57,
      easy_enroll_packages: [{ rate: 0.06, share: 0.3 }, { rate: 0.08, share: 0.5 }, { rate: 0.1, share: 0.2 }],
      easy_enroll_escalation_cap: 0.1,
    });
  });

  it.each([{}, { dc_plan: easyEnroll }, { easy_enroll: { enabled: true, packages: easyEnroll.easy_enroll_packages } }])(
    'preserves an untouched scenario and does not materialize inherited keys during unrelated edits: %j', original => {
      const form = applyResolvedFormData(easyEnroll, applyConfigToFormData(original, DEFAULT_FORM_DATA));
      expect(applyConfigEdits(original, payload(form), payload(structuredClone(form)))).toEqual(original);
      expect(applyConfigEdits(original, payload(form), payload({ ...form, seed: form.seed + 1 })))
        .toEqual({ ...original, simulation: { random_seed: form.seed + 1 } });
    });

  it('writes just edited Easy Enroll keys in a sparse scenario', () => {
    const form = applyResolvedFormData(easyEnroll, DEFAULT_FORM_DATA);
    expect(applyConfigEdits({}, payload(form), payload({ ...form, dcEasyEnrollEnabled: false, dcEasyEnrollEscalationCap: 15 })))
      .toEqual({ dc_plan: { easy_enroll_enabled: false, easy_enroll_escalation_cap: 0.15 } });
  });
});

describe('re-enrollment sweep payload', () => {
  it('omits new keys for an untouched scenario even when inherited values are displayed', () => {
    const form = applyResolvedFormData({ reenrollment_sweep_enabled: true, reenrollment_sweep_interval_years: 2, reenrollment_sweep_first_year: 2027 }, DEFAULT_FORM_DATA);
    expect(form.dcReenrollmentSweepEnabled).toBe(true);
    expect(form.dcReenrollmentSweepFirstYear).toBe('2027');
    expect(Object.keys(payload(form).dc_plan).filter(key => key.startsWith('reenrollment_sweep_'))).toEqual([]);
  });
  it('loads, saves and clears an explicit schedule without coercing null to zero', () => {
    const settings = { reenrollment_sweep_enabled: true, reenrollment_sweep_interval_years: 2, reenrollment_sweep_first_year: 2027 };
    const loaded = applyConfigToFormData({ dc_plan: settings }, DEFAULT_FORM_DATA);
    expect(payload(loaded).dc_plan).toMatchObject(settings);
    const cleared = { ...loaded, dcReenrollmentSweepFirstYear: '', dcReenrollmentSweepEnabled: false };
    expect(payload(cleared).dc_plan).toMatchObject({ ...settings, reenrollment_sweep_enabled: false, reenrollment_sweep_first_year: null });
    expect(applyConfigEdits({ dc_plan: settings }, payload(loaded), payload(cleared))).toEqual({ dc_plan: { ...settings, reenrollment_sweep_enabled: false, reenrollment_sweep_first_year: null } });
  });
  it('exports an edited toggle with its default interval and optional first year', () => {
    expect(payload({ ...DEFAULT_FORM_DATA, dcReenrollmentSweepEdited: true, dcReenrollmentSweepEnabled: true }).dc_plan).toMatchObject({ reenrollment_sweep_enabled: true, reenrollment_sweep_interval_years: 3, reenrollment_sweep_first_year: null });
  });
});


describe('sweep options inheritance', () => {
  it('omits new options in an untouched scenario with an existing sweep', () => {
    const loaded = applyConfigToFormData({ dc_plan: { reenrollment_sweep_enabled: true } }, DEFAULT_FORM_DATA);
    expect(payload(loaded).dc_plan).not.toHaveProperty('reenrollment_sweep_method');
  });
  it('exports edited options and converts the decline percent to a rate', () => {
    expect(payload({ ...DEFAULT_FORM_DATA, dcReenrollmentSweepOptionsEdited: true,
      dcReenrollmentSweepMethod: 'into_aip', dcReenrollmentSweepIncludeBelowDefault: true,
      dcReenrollmentSweepIncludeBelowAipCap: true, dcReenrollmentSweepDeclineProbability: 15 }).dc_plan)
      .toMatchObject({ reenrollment_sweep_method: 'into_aip', reenrollment_sweep_include_non_contributors: true,
        reenrollment_sweep_include_below_default: true, reenrollment_sweep_include_below_aip_cap: true,
        reenrollment_sweep_decline_probability: 0.15 });
  });
});


it('retains an existing method without adding omitted sweep options', () => {
  const form = applyConfigToFormData({ dc_plan: { reenrollment_sweep_method: 'into_aip' } }, DEFAULT_FORM_DATA);
  expect(payload(form).dc_plan.reenrollment_sweep_method).toBe('into_aip');
  expect(payload(form).dc_plan).not.toHaveProperty('reenrollment_sweep_decline_probability');
  expect(payload(form).dc_plan).not.toHaveProperty('reenrollment_sweep_include_below_default');
});

const rateChanges = {
  deferral_rate_changes_enabled: true,
  deferral_rate_changes_with_escalation_increase_probability: 0.0325,
  deferral_rate_changes_with_escalation_decrease_probability: 0.15,
  deferral_rate_changes_without_escalation_increase_probability: 0.25,
  deferral_rate_changes_without_escalation_decrease_probability: 0.075,
  deferral_rate_changes_increase_steps: [{ pp: 2, weight: 0.625 }, { pp: 5, weight: 0.375 }],
  deferral_rate_changes_decrease_shares: [{ share: 0.25, weight: 0.25 }, { share: 0.75, weight: 0.75 }],
  deferral_rate_changes_post_escalation_decrease_window_days: 123,
  deferral_rate_changes_post_escalation_decrease_leaves_escalation: true,
  deferral_rate_changes_stop_probability: 0.015,
  deferral_rate_changes_restart_probability: 0.0125,
};

describe('contribution rate change payload and inheritance', () => {
  it('loads all decimal overrides and round trips without scaling points or days', () => {
    const form = applyConfigToFormData({ dc_plan: rateChanges }, DEFAULT_FORM_DATA);
    expect(form).toMatchObject({
      dcDeferralRateChangesEnabled: true,
      dcDeferralRateChangesWithEscalationIncreaseProbability: 3.25,
      dcDeferralRateChangesWithEscalationDecreaseProbability: 15,
      dcDeferralRateChangesWithoutEscalationIncreaseProbability: 25,
      dcDeferralRateChangesWithoutEscalationDecreaseProbability: 7.5,
      dcDeferralRateChangesIncreaseSteps: [{ pp: 2, weight: 62.5 }, { pp: 5, weight: 37.5 }],
      dcDeferralRateChangesDecreaseShares: [{ share: 25, weight: 25 }, { share: 75, weight: 75 }],
      dcDeferralRateChangesPostEscalationDecreaseWindowDays: 123,
      dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation: true,
      dcDeferralRateChangesStopProbability: 1.5,
      dcDeferralRateChangesRestartProbability: 1.25,
    });
    expect(payload(form).dc_plan).toMatchObject(rateChanges);
    expect(payload(applyResolvedFormData(rateChanges, DEFAULT_FORM_DATA)).dc_plan).toMatchObject(rateChanges);
    expect(applyConfigToFormData({}, form)).toEqual(form);
    expect(rateChanges.deferral_rate_changes_increase_steps[0]).toEqual({ pp: 2, weight: 0.625 });
    const off = applyConfigToFormData({ dc_plan: { deferral_rate_changes_enabled: false,
      deferral_rate_changes_post_escalation_decrease_leaves_escalation: false,
      deferral_rate_changes_with_escalation_increase_probability: 0, deferral_rate_changes_restart_probability: 0,
    } }, form);
    expect(off).toMatchObject({ dcDeferralRateChangesEnabled: false,
      dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation: false,
      dcDeferralRateChangesWithEscalationIncreaseProbability: 0, dcDeferralRateChangesRestartProbability: 0,
      dcDeferralRateChangesIncreaseSteps: form.dcDeferralRateChangesIncreaseSteps });
  });

  it('matches every shipped default', () => {
    expect(payload(DEFAULT_FORM_DATA).dc_plan).toMatchObject({
      deferral_rate_changes_enabled: true,
      deferral_rate_changes_with_escalation_increase_probability: 0.085,
      deferral_rate_changes_with_escalation_decrease_probability: expect.closeTo(0.067),
      deferral_rate_changes_without_escalation_increase_probability: 0.085,
      deferral_rate_changes_without_escalation_decrease_probability: expect.closeTo(0.067),
      deferral_rate_changes_increase_steps: [{ pp: 1, weight: 0.1 }, { pp: 2, weight: 0.1 }, { pp: 3, weight: 0.15 }, { pp: 5, weight: 0.2 }, { pp: 7, weight: 0.2 }, { pp: 10, weight: 0.25 }],
      deferral_rate_changes_decrease_shares: [{ share: 0.25, weight: 0.2 }, { share: 0.5, weight: 0.25 }, { share: 0.75, weight: 0.35 }, { share: 0.9, weight: 0.2 }],
      deferral_rate_changes_post_escalation_decrease_window_days: 90,
      deferral_rate_changes_post_escalation_decrease_leaves_escalation: false,
      deferral_rate_changes_stop_probability: 0.015, deferral_rate_changes_restart_probability: 0.4,
    });
  });

  it.each([{}, { dc_plan: rateChanges }, { deferral_rate_changes: {
    enabled: true, increase_steps: rateChanges.deferral_rate_changes_increase_steps,
  } }])('sends no new keys on untouched or unrelated scenario edits: %j', original => {
    const form = applyResolvedFormData(rateChanges, applyConfigToFormData(original, DEFAULT_FORM_DATA));
    expect(applyConfigEdits(original, payload(form), payload(structuredClone(form)))).toEqual(original);
    expect(applyConfigEdits(original, payload(form), payload({ ...form, seed: form.seed + 1 })))
      .toEqual({ ...original, simulation: { random_seed: form.seed + 1 } });
  });

  it('persists only edited keys, retaining saved inactive values', () => {
    const form = applyResolvedFormData(rateChanges, DEFAULT_FORM_DATA);
    expect(applyConfigEdits({}, payload(form), payload({ ...form, dcDeferralRateChangesEnabled: false,
      dcDeferralRateChangesStopProbability: 2.25, dcDeferralRateChangesIncreaseSteps: [{ pp: 3, weight: 100 }],
    }))).toEqual({ dc_plan: { deferral_rate_changes_enabled: false,
      deferral_rate_changes_stop_probability: 0.0225, deferral_rate_changes_increase_steps: [{ pp: 3, weight: 1 }] } });
  });
});

describe('annual starting-pay growth', () => {
  it('loads percentages and saves decimal rates', () => {
    const form = applyConfigToFormData({ new_hire: { salary_growth_rate: 0.03 } }, DEFAULT_FORM_DATA);
    expect(form.newHireSalaryGrowthPercent).toBe(3);
    expect(payload(form).new_hire).toMatchObject({ salary_growth_rate: 0.03 });
  });

  it('defaults missing and explicit zero rates to zero even after another scenario', () => {
    const previous = { ...DEFAULT_FORM_DATA, newHireSalaryGrowthPercent: 5, colaRate: 4 };
    for (const config of [{}, { new_hire: {} }, { new_hire: { salary_growth_rate: 0 } }]) {
      const form = applyConfigToFormData(config, previous);
      expect(form.newHireSalaryGrowthPercent).toBe(0);
      expect(payload(form).new_hire).toMatchObject({ salary_growth_rate: 0 });
    }
    expect(payload(DEFAULT_FORM_DATA).new_hire).toMatchObject({ salary_growth_rate: 0 });
  });
});
