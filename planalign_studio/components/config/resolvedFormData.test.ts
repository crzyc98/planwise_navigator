import { describe, expect, it } from 'vitest';
import { DEFAULT_FORM_DATA } from './constants';
import { applyResolvedFormData } from './resolvedFormData';
import exportedFixture from './fixtures/resolvedEngineInputs.json';

describe('resolved engine inputs in configuration controls', () => {
  it('resolves participant behavior from engine defaults/overrides with percentage units and independent arrays', () => {
    const variables = {
      deferral_escalation_mode: 'participant_elected', deferral_escalation_participant_elected_signup_probability: 0.0125,
      enrollment_match_magnet_downward_enabled: true,
      below_default_share_tiers: [{ max_auto_enroll_default_rate: 0.03, share: 0.1 }, { max_auto_enroll_default_rate: null, share: 0.15 }],
      below_default_steps: [{ pp: 1, weight: 0.5 }, { pp: 2, weight: 0.5 }],
    };
    const resolved = applyResolvedFormData(variables, DEFAULT_FORM_DATA);
    expect(resolved).toMatchObject({ dcEscalationMode: 'participant_elected', dcEscalationSignupProbability: 1.25,
      dcMatchMagnetDownwardEnabled: true,
      dcBelowDefaultShareTiers: [{ max_auto_enroll_default_rate: 3, share: 10 }, { max_auto_enroll_default_rate: null, share: 15 }],
      dcBelowDefaultSteps: [{ pp: 1, weight: 50 }, { pp: 2, weight: 50 }],
    });
    resolved.dcBelowDefaultShareTiers[0].share = 20;
    resolved.dcBelowDefaultSteps[0].weight = 60;
    expect(variables.below_default_share_tiers[0].share).toBe(0.1);
    expect(variables.below_default_steps[0].weight).toBe(0.5);
    expect(applyResolvedFormData({ deferral_escalation_participant_elected_signup_probability: 0,
      enrollment_match_magnet_downward_enabled: false }, resolved)).toMatchObject({
      dcEscalationSignupProbability: 0, dcMatchMagnetDownwardEnabled: false,
    });
  });
  it('shows active legacy requirements instead of dormant detailed values', () => {
    const resolved = applyResolvedFormData({ employer_match: { apply_eligibility: false,
      eligibility: { minimum_tenure_years: 3, minimum_hours_annual: 500,
        require_active_at_year_end: false, allow_terminated_new_hires: true,
        allow_experienced_terminations: true },
    } }, DEFAULT_FORM_DATA);
    expect(resolved).toMatchObject({ dcMatchMinTenureYears: 0, dcMatchMinHoursAnnual: 1000,
      dcMatchRequireYearEndActive: true, dcMatchAllowTerminatedNewHires: false,
      dcMatchAllowExperiencedTerminations: false });
  });
  it('renders the real Python export fixture with exact schedule units and bounds', () => {
    const resolved = applyResolvedFormData(exportedFixture.variables, DEFAULT_FORM_DATA);
    expect(resolved).toMatchObject({ seed: 0, meritBudget: 3.5, dcEligibilityMonths: 0, dcMatchMode: 'tenure_graded' });
    expect(resolved.dcTenureMatchTiers).toEqual([{ minYears: 0, maxYears: null, matchRate: 150, maxDeferralPct: 6 }]);
    expect(resolved.dcPointsMatchTiers).toEqual([{ minPoints: 0, maxPoints: null, matchRate: 50, maxDeferralPct: 8 }]);
    expect(resolved.dcTenureGradedBands).toEqual([{ minYears: 0, maxYears: null, tiers: [{ deferralMin: 0, deferralMax: 6, matchRate: 150 }] }]);
    expect(resolved.dcCoreGradedSchedule).toEqual([{ serviceYearsMin: 3, serviceYearsMax: 5, rate: 4 }]);
    expect(resolved.dcCorePointsSchedule).toEqual([{ minPoints: 40, maxPoints: null, rate: 4.5 }]);
    expect(resolved.dcCoreAgeSchedule).toEqual([{ minAge: 40, maxAge: null, rate: 5 }]);
    expect(resolved.jobLevelCompensation).toEqual([{ level: 1, name: 'Analyst', minComp: 45000, maxComp: 85000 }]);
    expect(resolved.newHireAgeDistribution).toEqual([{ age: 37, weight: 1, description: '' }]);
  });

  it('replaces misleading Studio defaults with resolved legacy values including zero', () => {
    const resolved = applyResolvedFormData({
      random_seed: 0, eligibility_waiting_period_days: 0,
      auto_enrollment_scope: 'all_eligible_employees',
      employer_core_contribution_rate: 0.03,
      deferral_escalation_cap: 0.06, promotion_base_increase_pct: 0.20,
      auto_enrollment_enabled: false, employer_core_enabled: false, merit_budget: 0.035,
    }, DEFAULT_FORM_DATA);
    expect(resolved).toMatchObject({
      seed: 0, dcEligibilityMonths: 0, dcAutoEnrollScope: 'all_eligible',
      dcCoreContributionRate: 3, dcEscalationCap: 6, promoIncrease: 20,
      dcAutoEnroll: false, dcCoreEnabled: false, meritBudget: 3.5,
    });
    expect(DEFAULT_FORM_DATA.dcEligibilityMonths).toBe(3);
  });

  it('uses the plan eligibility override over the older waiting-period alias', () => {
    const resolved = applyResolvedFormData({
      plan_eligibility_waiting_period_days: 60, eligibility_waiting_period_days: 90,
    }, DEFAULT_FORM_DATA);
    expect(resolved.dcEligibilityMonths).toBe(2);
    expect(applyResolvedFormData({ eligibility_waiting_period_days: 90 }, DEFAULT_FORM_DATA).dcEligibilityMonths).toBe(0);
  });

  it('uses reachable SQL defaults when the export omits core settings', () => {
    const resolved = applyResolvedFormData({ employer_core_contribution: { eligibility: { allow_new_hires: false } },
      core_minimum_tenure_years: 9, core_minimum_hours: 99,
    }, DEFAULT_FORM_DATA);
    expect(resolved).toMatchObject({ dcCoreMinTenureYears: 1, dcCoreMinHoursAnnual: 1000,
      dcCoreRequireYearEndActive: true, dcCoreAllowTerminatedNewHires: false,
      dcCoreAllowExperiencedTerminations: false, dcCoreContributionRate: 2 });
  });

  it('preserves explicit source modes and distinguishes missing rates from zero', () => {
    const form = { ...DEFAULT_FORM_DATA, dcVoluntaryEnrollmentMode: 'inherit' as const, dcNewHireOptOutMode: 'demographic' as const };
    const resolved = applyResolvedFormData({ voluntary_enrollment_rate: 0, deferral_spread_max_lift: 0 }, form);
    expect(resolved).toMatchObject({
      dcVoluntaryEnrollmentMode: 'inherit', dcNewHireOptOutMode: 'demographic',
      dcVoluntaryEnrollmentRate: '0', dcNewHireOptOutRate: '', dcDeferralSpreadMaxLift: '0',
      dcEscalationHireDateCutoff: '',
    });
  });

  it('converts decimal behavior rates and percentage-point increments exactly once', () => {
    const resolved = applyResolvedFormData({
      voluntary_enrollment_rate: 0.73, new_hire_opt_out_rate: 0.08,
      deferral_spread_max_lift: 4, deferral_escalation_increment: 0.015,
      voluntary_max_deferral_rate: 0.15, enrollment_match_magnet_probability: 0.45,
      voluntary_enrollment_deferral_rates_demographic_base_rates_young_low: 0.07,
    }, DEFAULT_FORM_DATA);
    expect(resolved).toMatchObject({ dcVoluntaryEnrollmentRate: '73', dcNewHireOptOutRate: '8',
      dcDeferralSpreadMaxLift: '4', dcEscalationRate: 1.5, dcMaxVoluntaryDeferral: 15,
      dcMatchMagnetProbability: 45 });
    expect(resolved.dcVoluntaryDeferralBaseRates.young_low).toBeCloseTo(7);
  });

  it('projects consumed tiers and preserves different schedule unit conventions', () => {
    const resolved = applyResolvedFormData({
      match_template: 'simple', match_tiers: [{ employee_min: 0, employee_max: 0.08, match_rate: 0.25 }],
      tenure_match_tiers: [{ min_years: 0, max_years: null, rate: 150, max_deferral_pct: 6 }],
      tenure_graded_bands: [{ min_years: 0, max_years: null, tiers: [{ employee_min: 0, employee_max: 0.06, match_rate: 1.5 }] }],
      employer_core_graded_schedule: [{ min_years: 3, max_years: 5, rate: 4 }],
      employer_core_age_schedule: [{ min_age: 40, max_age: null, rate: 5 }],
    }, DEFAULT_FORM_DATA);
    expect(resolved.dcMatchTemplate).toBe('simple');
    expect(resolved.dcMatchTiers).toEqual([{ deferralMin: 0, deferralMax: 8, matchRate: 25 }]);
    expect(resolved.dcTenureMatchTiers[0]).toEqual({ minYears: 0, maxYears: null, matchRate: 150, maxDeferralPct: 6 });
    expect(resolved.dcTenureGradedBands[0].tiers[0].matchRate).toBe(150);
    expect(resolved.dcCoreGradedSchedule).toEqual([{ serviceYearsMin: 3, serviceYearsMax: 5, rate: 4 }]);
    expect(resolved.dcCoreAgeSchedule).toEqual([{ minAge: 40, maxAge: null, rate: 5 }]);
  });

  it('does not pretend legacy formula metadata supplies the contribution tiers', () => {
    const resolved = applyResolvedFormData({ active_match_formula: 'simple_match',
      match_formulas: { simple_match: { type: 'simple', max_match_percentage: 0.08, match_rate: 0.25 } },
    }, DEFAULT_FORM_DATA);
    expect(resolved.dcMatchTiers).toEqual(DEFAULT_FORM_DATA.dcMatchTiers);
    expect(resolved.dcMatchTemplate).toBe(DEFAULT_FORM_DATA.dcMatchTemplate);
  });

  it('prefers explicit Studio match tiers over a legacy formula and maps independent eligibility', () => {
    const resolved = applyResolvedFormData({
      active_match_formula: 'simple_match', match_formulas: { simple_match: { type: 'simple', max_match_percentage: 0.06, match_rate: 0.5 } },
      match_tiers: [{ employee_min: 0, employee_max: 0.04, match_rate: 1 }],
      employer_match: { eligibility: { minimum_tenure_years: 2, require_active_at_year_end: false, minimum_hours_annual: 500 } },
      employer_core_contribution: { eligibility: { minimum_tenure_years: 1, require_active_at_year_end: true, minimum_hours_annual: 800 } },
      core_minimum_hours: 800, employer_core_integration_level_value: null,
      employer_core_integration_disparity_rate: 0.03,
    }, DEFAULT_FORM_DATA);
    expect(resolved.dcMatchTiers[0].deferralMax).toBe(4);
    expect(resolved).toMatchObject({ dcMatchMinTenureYears: 2, dcMatchRequireYearEndActive: false,
      dcMatchMinHoursAnnual: 500, dcCoreMinTenureYears: 1, dcCoreRequireYearEndActive: true,
      dcCoreMinHoursAnnual: 800, dcCoreIntegrationLevelValue: null, dcCoreIntegrationDisparityRate: 3 });
  });

  it('keeps helper and unsupported fields unchanged and never mutates source arrays', () => {
    const form = { ...DEFAULT_FORM_DATA, targetPercentile: 90, promoBudget: 8 };
    const variables = { new_hire_age_distribution: [{ age: 37, weight: 1 }],
      job_level_compensation: [{ level: 1, min_compensation: 12345, max_compensation: 67890 }] };
    const resolved = applyResolvedFormData(variables, form);
    expect(resolved.targetPercentile).toBe(90);
    expect(resolved.promoBudget).toBe(8);
    expect(resolved.newHireAgeDistribution).toEqual([{ age: 37, weight: 1, description: '' }]);
    resolved.newHireAgeDistribution[0].weight = 0.5;
    expect(variables.new_hire_age_distribution[0].weight).toBe(1);
    expect(resolved.jobLevelCompensation[0]).toEqual({ level: 1, name: 'Level 1', minComp: 12345, maxComp: 67890 });
  });
});

describe('resolved Easy Enroll inputs', () => {
  it('projects all decimal engine values, preserves zero and false, and copies package rows', () => {
    const variables = { easy_enroll_enabled: true, easy_enroll_channel_share_with_auto_enrollment: 0.57,
      easy_enroll_channel_share_without_auto_enrollment: 0.45, easy_enroll_escalation_cap: 0.125,
      easy_enroll_packages: [{ rate: 0.075, share: 1 }],
    };
    const form = applyResolvedFormData(variables, DEFAULT_FORM_DATA);
    expect(form).toMatchObject({ dcEasyEnrollEnabled: true, dcEasyEnrollShareWithAutoEnrollment: 57,
      dcEasyEnrollShareWithoutAutoEnrollment: 45, dcEasyEnrollEscalationCap: 12.5,
      dcEasyEnrollPackages: [{ rate: 7.5, share: 100 }],
    });
    form.dcEasyEnrollPackages[0].rate = 8;
    expect(variables.easy_enroll_packages[0].rate).toBe(0.075);
    expect(applyResolvedFormData({ easy_enroll_enabled: false, easy_enroll_channel_share_with_auto_enrollment: 0,
      easy_enroll_channel_share_without_auto_enrollment: 0, easy_enroll_escalation_cap: 0 }, form))
      .toMatchObject({ dcEasyEnrollEnabled: false, dcEasyEnrollShareWithAutoEnrollment: 0,
        dcEasyEnrollShareWithoutAutoEnrollment: 0, dcEasyEnrollEscalationCap: 0 });
  });
});

describe('resolved starting-pay growth', () => {
  it('converts the exported decimal rate to percent', () => {
    expect(applyResolvedFormData({ new_hire_salary_growth_rate: 0.03 }, DEFAULT_FORM_DATA)
      .newHireSalaryGrowthPercent).toBe(3);
  });

  it('resets missing and zero rates to zero rather than COLA', () => {
    const previous = { ...DEFAULT_FORM_DATA, newHireSalaryGrowthPercent: 7, colaRate: 4 };
    expect(applyResolvedFormData({}, previous).newHireSalaryGrowthPercent).toBe(0);
    expect(applyResolvedFormData({ new_hire_salary_growth_rate: 0 }, previous)
      .newHireSalaryGrowthPercent).toBe(0);
  });
});
