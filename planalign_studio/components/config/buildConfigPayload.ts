// Pure function to build the API config payload from form data
// Extracted from handleSaveConfig (lines 1340-1466 of ConfigStudio.tsx)

import type { FormData } from './types';
import type { PromotionHazardConfig, BandConfig } from '../../services/api';
import { calculateMatchCap } from './constants';

function rateOverride(key: string, mode: FormData['dcVoluntaryEnrollmentMode'], value: string) {
  if (mode === 'inherit') return {};
  if (mode === 'demographic') return { [key]: null };
  return value !== '' ? { [key]: Number(value) / 100 } : {};
}

export function buildConfigPayload(
  formData: FormData,
  promotionHazardConfig: PromotionHazardConfig | null,
  bandConfig: BandConfig | null,
  censusTarget?: { isScenario: boolean; workspacePath?: string },
) {
  const saveCensusPath = formData.censusDataPath && !(
    censusTarget?.isScenario && (
      formData.censusDataSource === 'workspace' || formData.censusDataPath === censusTarget.workspacePath
    )
  );
  const configPayload = {
    simulation: {
      name: formData.name,
      start_year: Number(formData.startYear),
      end_year: Number(formData.endYear),
      random_seed: Number(formData.seed),
      target_growth_rate: Number(formData.targetGrowthRate) / 100,
    },
    workforce: {
      total_termination_rate: Number(formData.totalTerminationRate) / 100,
      new_hire_termination_rate: Number(formData.newHireTerminationRate) / 100,
      part_time_new_hire_pct: Number(formData.partTimeNewHirePct) / 100,
    },
    // Keep workspace inheritance when saving a scenario. Only a distinct census
    // belongs in scenario overrides; retain the legacy key for existing readers.
    ...(saveCensusPath
      ? {
          setup: { census_parquet_path: formData.censusDataPath },
          data_sources: { census_parquet_path: formData.censusDataPath },
        }
      : {}),
    compensation: {
      target_compensation_growth_percent: Number(formData.targetCompensationGrowth),
      merit_budget_percent: Number(formData.meritBudget),
      cola_rate_percent: Number(formData.colaRate),
      promotion_compensation: {
        base_increase_pct: Number(formData.promoIncrease) / 100,
        distribution_range: Number(formData.promoDistributionRange) / 100,
      },
      promotion_budget_percent: Number(formData.promoBudget),
      promotion_rate_multiplier: Number(formData.promoRateMultiplier),
    },
    new_hire: {
      strategy: formData.newHireStrategy,
      target_percentile: Number(formData.targetPercentile),
      compensation_variance_percent: Number(formData.newHireCompVariance),
      age_distribution: formData.newHireAgeDistribution.map(row => ({
        age: row.age,
        weight: row.weight,
      })),
      level_distribution_mode: formData.levelDistributionMode,
      level_distribution: formData.newHireLevelDistribution.map(row => ({
        level: row.level,
        percentage: row.percentage / 100,
      })),
      job_level_compensation: formData.jobLevelCompensation.map(row => ({
        level: row.level,
        name: row.name,
        min_compensation: row.minComp,
        max_compensation: row.maxComp,
      })),
      market_scenario: formData.marketScenario,
      level_market_adjustments: formData.levelMarketAdjustments.map(row => ({
        level: row.level,
        adjustment_percent: row.adjustment,
      })),
    },
    dc_plan: {
      eligibility_months: Number(formData.dcEligibilityMonths),
      auto_enroll: Boolean(formData.dcAutoEnroll),
      ...(formData.dcReenrollmentSweepOptionsEdited || formData.dcReenrollmentSweepOptionsPresent.includes('reenrollment_sweep_method') ? {
        reenrollment_sweep_method: formData.dcReenrollmentSweepMethod,
      } : {}),
      ...(formData.dcReenrollmentSweepOptionsEdited || formData.dcReenrollmentSweepOptionsPresent.includes('reenrollment_sweep_include_non_contributors') ? {
        reenrollment_sweep_include_non_contributors: formData.dcReenrollmentSweepIncludeNonContributors,
      } : {}),
      ...(formData.dcReenrollmentSweepOptionsEdited || formData.dcReenrollmentSweepOptionsPresent.includes('reenrollment_sweep_include_below_default') ? {
        reenrollment_sweep_include_below_default: formData.dcReenrollmentSweepIncludeBelowDefault,
      } : {}),
      ...(formData.dcReenrollmentSweepOptionsEdited || formData.dcReenrollmentSweepOptionsPresent.includes('reenrollment_sweep_include_below_aip_cap') ? {
        reenrollment_sweep_include_below_aip_cap: formData.dcReenrollmentSweepIncludeBelowAipCap,
      } : {}),
      ...(formData.dcReenrollmentSweepOptionsEdited || formData.dcReenrollmentSweepOptionsPresent.includes('reenrollment_sweep_decline_probability') ? {
        reenrollment_sweep_decline_probability: formData.dcReenrollmentSweepDeclineProbability / 100,
      } : {}),
      ...(formData.dcReenrollmentSweepEdited ? {
        reenrollment_sweep_enabled: formData.dcReenrollmentSweepEnabled,
        reenrollment_sweep_interval_years: Number(formData.dcReenrollmentSweepIntervalYears),
        reenrollment_sweep_first_year: formData.dcReenrollmentSweepFirstYear === '' ? null : Number(formData.dcReenrollmentSweepFirstYear),
      } : {}),
      default_deferral_percent: Number(formData.dcDefaultDeferral),
      auto_enroll_window_days: Number(formData.dcAutoEnrollWindowDays),
      auto_enroll_opt_out_grace_period: Number(formData.dcAutoEnrollOptOutGracePeriod),
      auto_enroll_scope: formData.dcAutoEnrollScope,
      auto_enroll_hire_date_cutoff: formData.dcAutoEnrollHireDateCutoff,
      opt_out_rate_target: Number(formData.dcOptOutRateTarget) / 100,
      opt_out_multipliers_age: formData.dcOptOutMultipliersAge,
      opt_out_multipliers_income: formData.dcOptOutMultipliersIncome,
      ...rateOverride('voluntary_enrollment_rate', formData.dcVoluntaryEnrollmentMode, formData.dcVoluntaryEnrollmentRate),
      ...rateOverride('new_hire_opt_out_rate', formData.dcNewHireOptOutMode, formData.dcNewHireOptOutRate),
      ...(formData.dcDeferralSpreadMaxLift !== '' ? { deferral_spread_max_lift: Number(formData.dcDeferralSpreadMaxLift) } : {}),
      // Per-segment starting deferral rates (UI percent → decimal)
      voluntary_deferral_base_rates: Object.fromEntries(
        Object.entries(formData.dcVoluntaryDeferralBaseRates).map(
          ([segment, percent]) => [segment, Number(percent) / 100]
        )
      ),
      // Feature 102: match-magnet dial (UI percent → decimal)
      match_magnet_enabled: Boolean(formData.dcMatchMagnetEnabled),
      match_magnet_probability: Number(formData.dcMatchMagnetProbability) / 100,
      match_magnet_downward_enabled: Boolean(formData.dcMatchMagnetDownwardEnabled),
      deferral_rate_changes_enabled: formData.dcDeferralRateChangesEnabled,
      deferral_rate_changes_with_escalation_increase_probability: Number(formData.dcDeferralRateChangesWithEscalationIncreaseProbability) / 100,
      deferral_rate_changes_with_escalation_decrease_probability: Number(formData.dcDeferralRateChangesWithEscalationDecreaseProbability) / 100,
      deferral_rate_changes_without_escalation_increase_probability: Number(formData.dcDeferralRateChangesWithoutEscalationIncreaseProbability) / 100,
      deferral_rate_changes_without_escalation_decrease_probability: Number(formData.dcDeferralRateChangesWithoutEscalationDecreaseProbability) / 100,
      deferral_rate_changes_increase_steps: formData.dcDeferralRateChangesIncreaseSteps.map(step => ({ pp: step.pp, weight: step.weight / 100 })),
      deferral_rate_changes_decrease_shares: formData.dcDeferralRateChangesDecreaseShares.map(step => ({ share: step.share / 100, weight: step.weight / 100 })),
      deferral_rate_changes_post_escalation_decrease_window_days: formData.dcDeferralRateChangesPostEscalationDecreaseWindowDays,
      deferral_rate_changes_post_escalation_decrease_leaves_escalation: formData.dcDeferralRateChangesPostEscalationDecreaseLeavesEscalation,
      deferral_rate_changes_stop_probability: Number(formData.dcDeferralRateChangesStopProbability) / 100,
      deferral_rate_changes_restart_probability: Number(formData.dcDeferralRateChangesRestartProbability) / 100,
      easy_enroll_enabled: Boolean(formData.dcEasyEnrollEnabled),
      easy_enroll_channel_share_without_auto_enrollment: Number(formData.dcEasyEnrollShareWithoutAutoEnrollment) / 100,
      easy_enroll_channel_share_with_auto_enrollment: Number(formData.dcEasyEnrollShareWithAutoEnrollment) / 100,
      easy_enroll_packages: formData.dcEasyEnrollPackages.map(pkg => ({ rate: pkg.rate / 100, share: pkg.share / 100 })),
      easy_enroll_escalation_cap: Number(formData.dcEasyEnrollEscalationCap) / 100,
      below_default_share_tiers: formData.dcBelowDefaultShareTiers.map(tier => ({
        max_auto_enroll_default_rate: tier.max_auto_enroll_default_rate === null ? null : Number(tier.max_auto_enroll_default_rate) / 100,
        share: Number(tier.share) / 100,
      })),
      below_default_steps: formData.dcBelowDefaultSteps.map(step => ({ pp: step.pp, weight: Number(step.weight) / 100 })),
      max_voluntary_deferral_percent: Number(formData.dcMaxVoluntaryDeferral) / 100,
      deferral_match_response: {
        enabled: Boolean(formData.dcMatchResponseEnabled),
        upward_participation_rate: Number(formData.dcMatchResponseUpwardParticipation) / 100,
        downward_enabled: Boolean(formData.dcMatchResponseDownwardEnabled),
        downward_participation_rate: Number(formData.dcMatchResponseDownwardParticipation) / 100,
      },
      match_enabled: Boolean(formData.dcMatchEnabled),
      match_template: formData.dcMatchTemplate,
      match_tiers: formData.dcMatchTiers.map(t => ({
        employee_min: t.deferralMin / 100,
        employee_max: t.deferralMax / 100,
        match_rate: t.matchRate / 100,
      })),
      match_cap_percent: calculateMatchCap(formData.dcMatchTiers),
      match_status: formData.dcMatchMode,
      tenure_match_tiers: formData.dcTenureMatchTiers.map(t => ({
        min_years: t.minYears,
        max_years: t.maxYears,
        match_rate: t.matchRate / 100,
        max_deferral_pct: t.maxDeferralPct / 100,
      })),
      points_match_tiers: formData.dcPointsMatchTiers.map(t => ({
        min_points: t.minPoints,
        max_points: t.maxPoints,
        match_rate: t.matchRate / 100,
        max_deferral_pct: t.maxDeferralPct / 100,
      })),
      // Feature 099: tenure-graded multi-tier bands
      tenure_graded_bands: formData.dcTenureGradedBands.map(b => ({
        min_years: b.minYears,
        max_years: b.maxYears,
        tiers: b.tiers.map(t => ({
          employee_min: t.deferralMin / 100,
          employee_max: t.deferralMax / 100,
          match_rate: t.matchRate / 100,
        })),
      })),
      match_min_tenure_years: Number(formData.dcMatchMinTenureYears),
      match_require_year_end_active: Boolean(formData.dcMatchRequireYearEndActive),
      match_min_hours_annual: Number(formData.dcMatchMinHoursAnnual),
      match_allow_terminated_new_hires: Boolean(formData.dcMatchAllowTerminatedNewHires),
      match_allow_experienced_terminations: Boolean(formData.dcMatchAllowExperiencedTerminations),
      core_enabled: Boolean(formData.dcCoreEnabled),
      core_status: formData.dcCoreStatus,
      core_contribution_rate_percent: Number(formData.dcCoreContributionRate),
      core_graded_schedule: formData.dcCoreGradedSchedule.map(tier => ({
        service_years_min: tier.serviceYearsMin,
        service_years_max: tier.serviceYearsMax,
        contribution_rate: tier.rate / 100,
      })),
      core_points_schedule: formData.dcCorePointsSchedule.map(tier => ({
        min_points: tier.minPoints,
        max_points: tier.maxPoints,
        contribution_rate: tier.rate / 100,
      })),
      core_age_schedule: formData.dcCoreAgeSchedule.map(tier => ({
        min_age: tier.minAge,
        max_age: tier.maxAge,
        contribution_rate: tier.rate / 100,
      })),
      // §401(l) integration. The engine only ever sees decimal fractions, so the
      // percentage the form carries is converted here, once.
      core_integration_enabled: Boolean(formData.dcCoreIntegrationEnabled),
      core_integration_level_mode: formData.dcCoreIntegrationLevelMode,
      core_integration_level_value:
        formData.dcCoreIntegrationLevelMode === 'ss_wage_base'
          ? null
          : Number(formData.dcCoreIntegrationLevelValue),
      core_integration_disparity_rate:
        Number(formData.dcCoreIntegrationDisparityRate) / 100,
      core_min_tenure_years: Number(formData.dcCoreMinTenureYears),
      core_require_year_end_active: Boolean(formData.dcCoreRequireYearEndActive),
      core_min_hours_annual: Number(formData.dcCoreMinHoursAnnual),
      core_allow_terminated_new_hires: Boolean(formData.dcCoreAllowTerminatedNewHires),
      core_allow_experienced_terminations: Boolean(formData.dcCoreAllowExperiencedTerminations),
      auto_escalation: Boolean(formData.dcAutoEscalation),
      escalation_mode: formData.dcEscalationMode,
      escalation_participant_elected_signup_probability: Number(formData.dcEscalationSignupProbability) / 100,
      escalation_rate_percent: Number(formData.dcEscalationRate),
      escalation_cap_percent: Number(formData.dcEscalationCap),
      escalation_effective_day: formData.dcEscalationEffectiveDay,
      escalation_delay_years: Number(formData.dcEscalationDelayYears),
      escalation_hire_date_cutoff: formData.dcEscalationHireDateCutoff,
    },
    advanced: {
      engine: formData.engine,
      enable_multithreading: Boolean(formData.enableMultithreading),
      checkpoint_frequency: formData.checkpointFrequency,
      memory_limit_gb: Number(formData.memoryLimitGB),
      log_level: formData.logLevel,
      strict_validation: Boolean(formData.strictValidation),
    },
  };

  return {
    ...configPayload,
    // Include seed configs in the unified payload.
    ...(promotionHazardConfig ? {
      promotion_hazard: {
        base_rate: promotionHazardConfig.base.base_rate,
        level_dampener_factor: promotionHazardConfig.base.level_dampener_factor,
        age_multipliers: promotionHazardConfig.age_multipliers.map(m => ({
          age_band: m.age_band,
          multiplier: m.multiplier,
        })),
        tenure_multipliers: promotionHazardConfig.tenure_multipliers.map(m => ({
          tenure_band: m.tenure_band,
          multiplier: m.multiplier,
        })),
      },
    } : {}),
    ...(bandConfig ? {
      age_bands: bandConfig.age_bands.map(b => ({
        band_id: b.band_id,
        band_label: b.band_label,
        min_value: b.min_value,
        max_value: b.max_value,
        display_order: b.display_order,
      })),
      tenure_bands: bandConfig.tenure_bands.map(b => ({
        band_id: b.band_id,
        band_label: b.band_label,
        min_value: b.min_value,
        max_value: b.max_value,
        display_order: b.display_order,
      })),
    } : {}),
  };
}
