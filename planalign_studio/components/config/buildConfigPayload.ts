// Pure function to build the API config payload from form data
// Extracted from handleSaveConfig (lines 1340-1466 of ConfigStudio.tsx)

import type { FormData } from './types';
import type { PromotionHazardConfig, BandConfig } from '../../services/api';
import { calculateMatchCap } from './constants';

export function buildConfigPayload(
  formData: FormData,
  promotionHazardConfig: PromotionHazardConfig | null,
  bandConfig: BandConfig | null
) {
  const configPayload: any = {
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
    },
    data_sources: {
      census_parquet_path: formData.censusDataPath,
    },
    compensation: {
      merit_budget_percent: Number(formData.meritBudget),
      cola_rate_percent: Number(formData.colaRate),
      promotion_increase_percent: Number(formData.promoIncrease),
      promotion_distribution_range_percent: Number(formData.promoDistributionRange),
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
      default_deferral_percent: Number(formData.dcDefaultDeferral),
      auto_enroll_window_days: Number(formData.dcAutoEnrollWindowDays),
      auto_enroll_opt_out_grace_period: Number(formData.dcAutoEnrollOptOutGracePeriod),
      auto_enroll_scope: formData.dcAutoEnrollScope,
      auto_enroll_hire_date_cutoff: formData.dcAutoEnrollHireDateCutoff,
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
      match_min_tenure_years: Number(formData.dcMatchMinTenureYears),
      match_require_year_end_active: Boolean(formData.dcMatchRequireYearEndActive),
      match_min_hours_annual: Number(formData.dcMatchMinHoursAnnual),
      match_allow_terminated_new_hires: Boolean(formData.dcMatchAllowTerminatedNewHires),
      match_allow_experienced_terminations: Boolean(formData.dcMatchAllowExperiencedTerminations),
      core_enabled: Boolean(formData.dcCoreEnabled),
      core_status: formData.dcCoreStatus,
      core_contribution_rate_percent: Number(formData.dcCoreContributionRate),
      core_graded_schedule: formData.dcCoreGradedSchedule.map((tier: any) => ({
        service_years_min: tier.serviceYearsMin,
        service_years_max: tier.serviceYearsMax,
        contribution_rate: tier.rate / 100,
      })),
      core_points_schedule: formData.dcCorePointsSchedule.map((tier: any) => ({
        min_points: tier.minPoints,
        max_points: tier.maxPoints,
        contribution_rate: tier.rate / 100,
      })),
      core_min_tenure_years: Number(formData.dcCoreMinTenureYears),
      core_require_year_end_active: Boolean(formData.dcCoreRequireYearEndActive),
      core_min_hours_annual: Number(formData.dcCoreMinHoursAnnual),
      core_allow_terminated_new_hires: Boolean(formData.dcCoreAllowTerminatedNewHires),
      core_allow_experienced_terminations: Boolean(formData.dcCoreAllowExperiencedTerminations),
      auto_escalation: Boolean(formData.dcAutoEscalation),
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

  // Include seed configs in the unified payload
  if (promotionHazardConfig) {
    configPayload.promotion_hazard = {
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
    };
  }

  if (bandConfig) {
    configPayload.age_bands = bandConfig.age_bands.map(b => ({
      band_id: b.band_id,
      band_label: b.band_label,
      min_value: b.min_value,
      max_value: b.max_value,
      display_order: b.display_order,
    }));
    configPayload.tenure_bands = bandConfig.tenure_bands.map(b => ({
      band_id: b.band_id,
      band_label: b.band_label,
      min_value: b.min_value,
      max_value: b.max_value,
      display_order: b.display_order,
    }));
  }

  return configPayload;
}
