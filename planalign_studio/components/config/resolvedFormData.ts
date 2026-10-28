import type { FormData, MatchTier } from './types';
import { ELIGIBILITY_DEFAULTS } from './constants';
import { packagesToPercent, stepsToPercent, tiersToPercent } from './participantBehaviorConfig';

type Variables = Record<string, unknown>;
const asVariables = (value: unknown): Variables => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Variables : {};
const rows = <T,>(value: unknown): T[] | null => Array.isArray(value) ? value as T[] : null;
const percent = (value: unknown): number => scaled(value as number);
type Mapping = readonly [keyof FormData, string, number?];

// Avoid binary floating-point artifacts in controls and dirty comparisons.
const scaled = (value: number, factor = 100): number => Number((value * factor).toFixed(10));

// Defaults not always emitted by to_dbt_vars. These come from the reachable
// contribution/escalation models and dbt_project.yml, not DEFAULT_FORM_DATA.
const ENGINE_FALLBACKS: Variables = {
  plan_eligibility_waiting_period_days: 0,
  employer_match_enabled: true, employer_match_status: 'deferral_based', match_template: 'tiered',
  match_tiers: [
    { employee_min: 0, employee_max: 0.03, match_rate: 1 },
    { employee_min: 0.03, employee_max: 0.05, match_rate: 0.5 },
  ],
  employer_core_enabled: true, employer_core_status: 'flat', employer_core_contribution_rate: 0.02,
  employer_core_integration_enabled: false, employer_core_integration_level_mode: 'ss_wage_base',
  employer_core_integration_level_value: null, employer_core_integration_disparity_rate: 0,
  deferral_escalation_enabled: true, deferral_escalation_effective_mmdd: '01-01',
  deferral_escalation_increment: 0.01, deferral_escalation_cap: 0.10, deferral_escalation_first_delay_years: 1,
};

// Exported variables already resolve legacy YAML, Studio aliases and typed
// defaults. This projection is for display; it must never rebuild saved config.
const SCALARS: Mapping[] = [
  ['startYear', 'start_year'], ['endYear', 'end_year'], ['seed', 'random_seed'],
  ['targetGrowthRate', 'target_growth_rate', 100],
  ['totalTerminationRate', 'total_termination_rate', 100],
  ['newHireTerminationRate', 'new_hire_termination_rate', 100],
  ['partTimeNewHirePct', 'part_time_new_hire_pct', 100],
  ['meritBudget', 'merit_budget', 100], ['colaRate', 'cola_rate', 100],
  ['promoIncrease', 'promotion_base_increase_pct', 100],
  ['promoDistributionRange', 'promotion_distribution_range', 100],
  ['promoRateMultiplier', 'promotion_rate_multiplier'],
  ['dcAutoEnroll', 'auto_enrollment_enabled'],
  ['dcDeferralRateChangesEnabled', 'deferral_rate_changes_enabled'],
  ['dcDeferralRateChangesWithEscalationIncreaseProbability', 'deferral_rate_changes_with_escalation_increase_probability', 100],
  ['dcDeferralRateChangesWithEscalationDecreaseProbability', 'deferral_rate_changes_with_escalation_decrease_probability', 100],
  ['dcDeferralRateChangesWithoutEscalationIncreaseProbability', 'deferral_rate_changes_without_escalation_increase_probability', 100],
  ['dcDeferralRateChangesWithoutEscalationDecreaseProbability', 'deferral_rate_changes_without_escalation_decrease_probability', 100],
  ['dcDeferralRateChangesPostEscalationDecreaseWindowDays', 'deferral_rate_changes_post_escalation_decrease_window_days'],
  ['dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation', 'deferral_rate_changes_post_escalation_decrease_leaves_escalation'],
  ['dcDeferralRateChangesStopProbability', 'deferral_rate_changes_stop_probability', 100],
  ['dcDeferralRateChangesRestartProbability', 'deferral_rate_changes_restart_probability', 100],
  ['dcEasyEnrollEnabled', 'easy_enroll_enabled'],
  ['dcEasyEnrollShareWithoutAutoEnrollment', 'easy_enroll_channel_share_without_auto_enrollment', 100],
  ['dcEasyEnrollShareWithAutoEnrollment', 'easy_enroll_channel_share_with_auto_enrollment', 100],
  ['dcEasyEnrollEscalationCap', 'easy_enroll_escalation_cap', 100],
  ['dcReenrollmentSweepEnabled', 'reenrollment_sweep_enabled'],
  ['dcReenrollmentSweepIntervalYears', 'reenrollment_sweep_interval_years'],
  ['dcReenrollmentSweepMethod', 'reenrollment_sweep_method'],
  ['dcReenrollmentSweepIncludeNonContributors', 'reenrollment_sweep_include_non_contributors'],
  ['dcReenrollmentSweepIncludeBelowDefault', 'reenrollment_sweep_include_below_default'],
  ['dcReenrollmentSweepIncludeBelowAipCap', 'reenrollment_sweep_include_below_aip_cap'],
  ['dcReenrollmentSweepDeclineProbability', 'reenrollment_sweep_decline_probability', 100],
  ['dcDefaultDeferral', 'auto_enrollment_default_deferral_rate', 100],
  ['dcAutoEnrollWindowDays', 'auto_enrollment_window_days'],
  ['dcAutoEnrollOptOutGracePeriod', 'auto_enrollment_opt_out_grace_period'],
  ['dcAutoEnrollHireDateCutoff', 'auto_enrollment_hire_date_cutoff'],
  ['dcOptOutRateTarget', 'opt_out_rate_target', 100],
  ['dcMatchMagnetEnabled', 'enrollment_match_magnet_enabled'],
  ['dcMatchMagnetProbability', 'enrollment_match_magnet_probability', 100],
  ['dcMatchMagnetDownwardEnabled', 'enrollment_match_magnet_downward_enabled'],
  ['dcMaxVoluntaryDeferral', 'voluntary_max_deferral_rate', 100],
  ['dcMatchResponseEnabled', 'deferral_match_response_enabled'],
  ['dcMatchResponseUpwardParticipation', 'deferral_match_response_upward_participation_rate', 100],
  ['dcMatchResponseDownwardEnabled', 'deferral_match_response_downward_enabled'],
  ['dcMatchResponseDownwardParticipation', 'deferral_match_response_downward_participation_rate', 100],
  ['dcMatchEnabled', 'employer_match_enabled'], ['dcMatchMode', 'employer_match_status'],
  ['dcCoreEnabled', 'employer_core_enabled'], ['dcCoreStatus', 'employer_core_status'],
  ['dcCoreContributionRate', 'employer_core_contribution_rate', 100],
  ['dcCoreIntegrationEnabled', 'employer_core_integration_enabled'],
  ['dcCoreIntegrationLevelMode', 'employer_core_integration_level_mode'],
  ['dcCoreIntegrationDisparityRate', 'employer_core_integration_disparity_rate', 100],
  ['dcAutoEscalation', 'deferral_escalation_enabled'],
  ['dcEscalationMode', 'deferral_escalation_mode'],
  ['dcEscalationSignupProbability', 'deferral_escalation_participant_elected_signup_probability', 100],
  ['dcEscalationRate', 'deferral_escalation_increment', 100],
  ['dcEscalationCap', 'deferral_escalation_cap', 100],
  ['dcEscalationEffectiveDay', 'deferral_escalation_effective_mmdd'],
  ['dcEscalationDelayYears', 'deferral_escalation_first_delay_years'],
];

function applyScalars(variables: Variables, form: FormData): FormData {
  const changes: Record<string, unknown> = {};
  for (const [field, key, scale] of SCALARS) {
    const value = variables[key];
    if (value == null || typeof value !== typeof form[field]) continue;
    if (typeof value === 'number' && !Number.isFinite(value)) continue;
    changes[field] = scale === undefined ? value : scaled(value as number, scale);
  }
  return { ...form, ...changes };
}

function applyEnrollment(variables: Variables, form: FormData): FormData {
  const waitingDays = variables.plan_eligibility_waiting_period_days;
  const scope = variables.auto_enrollment_scope;
  const rates = { ...form.dcVoluntaryDeferralBaseRates };
  for (const key of Object.keys(rates) as Array<keyof typeof rates>) {
    const value = variables[`voluntary_enrollment_deferral_rates_demographic_base_rates_${key}`];
    if (typeof value === 'number') rates[key] = scaled(value);
  }
  return {
    ...form,
    ...(typeof waitingDays === 'number' ? { dcEligibilityMonths: scaled(waitingDays, 1 / 30) } : {}),
    ...(typeof scope === 'string' ? { dcAutoEnrollScope: scope === 'all_eligible_employees' ? 'all_eligible' : scope } : {}),
    dcVoluntaryEnrollmentRate: variables.voluntary_enrollment_rate == null ? '' : String(percent(variables.voluntary_enrollment_rate)),
    dcNewHireOptOutRate: variables.new_hire_opt_out_rate == null ? '' : String(percent(variables.new_hire_opt_out_rate)),
    dcDeferralSpreadMaxLift: variables.deferral_spread_max_lift == null ? form.dcDeferralSpreadMaxLift : String(variables.deferral_spread_max_lift),
    dcEscalationHireDateCutoff: (variables.deferral_escalation_hire_date_cutoff ?? '') as string,
    dcVoluntaryDeferralBaseRates: rates,
    dcOptOutMultipliersAge: rows<FormData['dcOptOutMultipliersAge'][number]>(variables.opt_out_multipliers_age) ?? form.dcOptOutMultipliersAge,
    dcOptOutMultipliersIncome: rows<FormData['dcOptOutMultipliersIncome'][number]>(variables.opt_out_multipliers_income) ?? form.dcOptOutMultipliersIncome,
    ...(rows<FormData['dcDeferralRateChangesIncreaseSteps'][number]>(variables.deferral_rate_changes_increase_steps)
      ? { dcDeferralRateChangesIncreaseSteps: stepsToPercent(variables.deferral_rate_changes_increase_steps as FormData['dcDeferralRateChangesIncreaseSteps']) } : {}),
    ...(rows<FormData['dcDeferralRateChangesDecreaseSteps'][number]>(variables.deferral_rate_changes_decrease_steps)
      ? { dcDeferralRateChangesDecreaseSteps: stepsToPercent(variables.deferral_rate_changes_decrease_steps as FormData['dcDeferralRateChangesDecreaseSteps']) } : {}),
    ...(rows<FormData['dcEasyEnrollPackages'][number]>(variables.easy_enroll_packages)
      ? { dcEasyEnrollPackages: packagesToPercent(variables.easy_enroll_packages as FormData['dcEasyEnrollPackages']) } : {}),
    dcReenrollmentSweepFirstYear: String(variables.reenrollment_sweep_first_year ?? ''),
    ...(rows<FormData['dcBelowDefaultShareTiers'][number]>(variables.below_default_share_tiers)
      ? { dcBelowDefaultShareTiers: tiersToPercent(variables.below_default_share_tiers as FormData['dcBelowDefaultShareTiers']) } : {}),
    ...(rows<FormData['dcBelowDefaultSteps'][number]>(variables.below_default_steps)
      ? { dcBelowDefaultSteps: stepsToPercent(variables.below_default_steps as FormData['dcBelowDefaultSteps']) } : {}),
  };
}

function applyEligibility(variables: Variables, form: FormData): FormData {
  const changes: Record<string, unknown> = {};
  const fields = {
    MinTenureYears: 'minimum_tenure_years', RequireYearEndActive: 'require_active_at_year_end',
    MinHoursAnnual: 'minimum_hours_annual', AllowTerminatedNewHires: 'allow_terminated_new_hires',
    AllowExperiencedTerminations: 'allow_experienced_terminations',
  };
  for (const family of ['Match', 'Core'] as const) {
    const settings = variables[family === 'Match' ? 'employer_match' : 'employer_core_contribution'];
    // Legacy matching ignores stored detailed rules. Show the rules actually
    // consumed by int_employer_eligibility, not dormant saved values.
    const nested = asVariables(settings);
    const eligibility = family === 'Match' && nested.apply_eligibility === false
      ? {} : asVariables(nested.eligibility);
    // int_employer_eligibility consumes nested values only; flat core aliases
    // do not override this model's defaults.
    const defaults: Record<string, number | boolean> = ELIGIBILITY_DEFAULTS[family];
    for (const [suffix, key] of Object.entries(fields)) {
      changes[`dc${family}${suffix}`] = eligibility[key] ?? defaults[key];
    }
  }
  return { ...form, ...changes };
}

function matchTiers(tiers: Variables[]): MatchTier[] {
  return tiers.map(tier => ({
    deferralMin: percent(tier.employee_min), deferralMax: percent(tier.employee_max),
    matchRate: percent(tier.match_rate),
  }));
}

function applyMatch(variables: Variables, form: FormData): FormData {
  // Legacy match_formulas affects the exported match-magnet ceiling, but the
  // contribution model consumes match_tiers directly. Do not invent a mapping.
  const tiers = variables.match_tiers;
  return {
    ...form,
    ...(typeof variables.match_template === 'string' ? { dcMatchTemplate: variables.match_template } : {}),
    ...(rows<Variables>(tiers) ? { dcMatchTiers: matchTiers(rows<Variables>(tiers)!) } : {}),
    ...(rows<Variables>(variables.tenure_match_tiers) ? { dcTenureMatchTiers: rows<Variables>(variables.tenure_match_tiers)!.map(tier => ({
      minYears: tier.min_years, maxYears: tier.max_years, matchRate: tier.rate, maxDeferralPct: tier.max_deferral_pct,
    })) as FormData['dcTenureMatchTiers'] } : {}),
    ...(rows<Variables>(variables.points_match_tiers) ? { dcPointsMatchTiers: rows<Variables>(variables.points_match_tiers)!.map(tier => ({
      minPoints: tier.min_points, maxPoints: tier.max_points, matchRate: tier.rate, maxDeferralPct: tier.max_deferral_pct,
    })) as FormData['dcPointsMatchTiers'] } : {}),
    ...(rows<Variables>(variables.tenure_graded_bands) ? { dcTenureGradedBands: rows<Variables>(variables.tenure_graded_bands)!.map(band => ({
      minYears: band.min_years, maxYears: band.max_years, tiers: matchTiers(rows<Variables>(band.tiers) ?? []),
    })) as FormData['dcTenureGradedBands'] } : {}),
  };
}

function applyCoreSchedules(variables: Variables, form: FormData): FormData {
  return {
    ...form,
    ...('employer_core_integration_level_value' in variables ? { dcCoreIntegrationLevelValue: variables.employer_core_integration_level_value as number | null } : {}),
    ...(rows<Variables>(variables.employer_core_graded_schedule) ? { dcCoreGradedSchedule: rows<Variables>(variables.employer_core_graded_schedule)!.map(tier => ({
      serviceYearsMin: tier.min_years, serviceYearsMax: tier.max_years, rate: tier.rate,
    })) as FormData['dcCoreGradedSchedule'] } : {}),
    ...(rows<Variables>(variables.employer_core_points_schedule) ? { dcCorePointsSchedule: rows<Variables>(variables.employer_core_points_schedule)!.map(tier => ({
      minPoints: tier.min_points, maxPoints: tier.max_points, rate: tier.rate,
    })) as FormData['dcCorePointsSchedule'] } : {}),
    ...(rows<Variables>(variables.employer_core_age_schedule) ? { dcCoreAgeSchedule: rows<Variables>(variables.employer_core_age_schedule)!.map(tier => ({
      minAge: tier.min_age, maxAge: tier.max_age, rate: tier.rate,
    })) as FormData['dcCoreAgeSchedule'] } : {}),
  };
}

function applyNewHire(variables: Variables, form: FormData): FormData {
  return {
    ...form,
    ...(rows<Variables>(variables.new_hire_age_distribution) ? { newHireAgeDistribution: rows<Variables>(variables.new_hire_age_distribution)!.map(row => ({
      age: row.age, weight: row.weight, description: form.newHireAgeDistribution.find(age => age.age === row.age)?.description ?? '',
    })) as FormData['newHireAgeDistribution'] } : {}),
    ...(rows<Variables>(variables.job_level_compensation) ? { jobLevelCompensation: rows<Variables>(variables.job_level_compensation)!.map(row => ({
      level: row.level, name: row.name ?? `Level ${row.level}`, minComp: row.min_compensation, maxComp: row.max_compensation,
    })) as FormData['jobLevelCompensation'] } : {}),
  };
}

/** Display the resolved global engine inputs without changing saved raw config.
 * Per-design overrides and unsupported Studio controls remain in their raw form.
 */
export function applyResolvedFormData(variables: Variables, form: FormData): FormData {
  variables = { ...ENGINE_FALLBACKS, ...variables };
  let resolved = applyScalars(variables, form);
  resolved = applyEnrollment(variables, resolved);
  resolved = applyEligibility(variables, resolved);
  resolved = applyMatch(variables, resolved);
  resolved = applyCoreSchedules(variables, resolved);
  return applyNewHire(variables, resolved);
}
