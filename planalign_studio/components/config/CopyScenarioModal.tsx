import { useConfigContext } from './ConfigContext';
import { getScenario, validateFilePath, Scenario } from '../../services/api';

interface CopyScenarioModalProps {
  availableScenarios: Scenario[];
  onClose: () => void;
}

export function CopyScenarioModal({ availableScenarios, onClose }: CopyScenarioModalProps) {
  const { setFormData, setPromotionHazardConfig, setBandConfig, activeWorkspace } = useConfigContext();

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-xl font-bold text-gray-900">Copy Configuration from Scenario</h2>
          <p className="text-sm text-gray-500 mt-1">Select a scenario to copy its settings into this one</p>
        </div>
        <div className="p-6 overflow-y-auto flex-1 space-y-3">
          {availableScenarios.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No other scenarios available to copy from</p>
          ) : (
            availableScenarios.map(scenario => (
              <button
                key={scenario.id}
                onClick={async () => {
                  try {
                    const fullScenario = await getScenario(activeWorkspace.id, scenario.id);
                    const cfg = fullScenario.config_overrides || {};

                    setFormData(prev => ({
                      ...prev,
                      // Simulation
                      name: cfg.simulation?.name || prev.name,
                      startYear: cfg.simulation?.start_year ?? prev.startYear,
                      endYear: cfg.simulation?.end_year ?? prev.endYear,
                      seed: cfg.simulation?.random_seed ?? prev.seed,
                      targetGrowthRate: cfg.simulation?.target_growth_rate != null
                        ? cfg.simulation.target_growth_rate * 100
                        : prev.targetGrowthRate,
                      // Workforce
                      totalTerminationRate: cfg.workforce?.total_termination_rate != null
                        ? cfg.workforce.total_termination_rate * 100
                        : prev.totalTerminationRate,
                      newHireTerminationRate: cfg.workforce?.new_hire_termination_rate != null
                        ? cfg.workforce.new_hire_termination_rate * 100
                        : prev.newHireTerminationRate,
                      // Data Sources - E100
                      censusDataPath: cfg.data_sources?.census_parquet_path || prev.censusDataPath,
                      censusDataStatus: cfg.data_sources?.census_parquet_path ? 'validating' : prev.censusDataStatus,
                      // Compensation
                      meritBudget: cfg.compensation?.merit_budget_percent ?? prev.meritBudget,
                      colaRate: cfg.compensation?.cola_rate_percent ?? prev.colaRate,
                      promoIncrease: cfg.compensation?.promotion_increase_percent ?? prev.promoIncrease,
                      promoDistributionRange: cfg.compensation?.promotion_distribution_range_percent ?? prev.promoDistributionRange,
                      promoBudget: cfg.compensation?.promotion_budget_percent ?? prev.promoBudget,
                      promoRateMultiplier: cfg.compensation?.promotion_rate_multiplier ?? prev.promoRateMultiplier,
                      // New Hire
                      newHireStrategy: cfg.new_hire?.strategy || prev.newHireStrategy,
                      targetPercentile: cfg.new_hire?.target_percentile ?? prev.targetPercentile,
                      newHireCompVariance: cfg.new_hire?.compensation_variance_percent ?? prev.newHireCompVariance,
                      marketScenario: cfg.new_hire?.market_scenario || prev.marketScenario,
                      // E082: New Hire Demographics
                      newHireAgeDistribution: cfg.new_hire?.age_distribution
                        ? cfg.new_hire.age_distribution.map((d: any, idx: number) => ({
                            age: d.age,
                            weight: d.weight,
                            description: prev.newHireAgeDistribution[idx]?.description || '',
                          }))
                        : prev.newHireAgeDistribution,
                      levelDistributionMode: cfg.new_hire?.level_distribution_mode || prev.levelDistributionMode,
                      newHireLevelDistribution: cfg.new_hire?.level_distribution
                        ? cfg.new_hire.level_distribution.map((d: any, idx: number) => ({
                            level: d.level,
                            name: prev.newHireLevelDistribution[idx]?.name || `Level ${d.level}`,
                            percentage: d.percentage * 100,
                          }))
                        : prev.newHireLevelDistribution,
                      // E082: Job Level Compensation
                      jobLevelCompensation: cfg.new_hire?.job_level_compensation
                        ? cfg.new_hire.job_level_compensation.map((d: any) => ({
                            level: d.level,
                            name: d.name,
                            minComp: d.min_compensation,
                            maxComp: d.max_compensation,
                          }))
                        : prev.jobLevelCompensation,
                      levelMarketAdjustments: cfg.new_hire?.level_market_adjustments
                        ? cfg.new_hire.level_market_adjustments.map((d: any) => ({
                            level: d.level,
                            adjustment: d.adjustment_percent,
                          }))
                        : prev.levelMarketAdjustments,
                      // DC Plan - Basic
                      dcEligibilityMonths: cfg.dc_plan?.eligibility_months ?? prev.dcEligibilityMonths,
                      dcAutoEnroll: cfg.dc_plan?.auto_enroll ?? prev.dcAutoEnroll,
                      dcDefaultDeferral: cfg.dc_plan?.default_deferral_percent ?? prev.dcDefaultDeferral,
                      // DC Plan - Auto-Enrollment Advanced (E084)
                      dcAutoEnrollWindowDays: cfg.dc_plan?.auto_enroll_window_days ?? prev.dcAutoEnrollWindowDays,
                      dcAutoEnrollOptOutGracePeriod: cfg.dc_plan?.auto_enroll_opt_out_grace_period ?? prev.dcAutoEnrollOptOutGracePeriod,
                      dcAutoEnrollScope: cfg.dc_plan?.auto_enroll_scope || prev.dcAutoEnrollScope,
                      dcAutoEnrollHireDateCutoff: cfg.dc_plan?.auto_enroll_hire_date_cutoff || prev.dcAutoEnrollHireDateCutoff,
                      // DC Plan - Match (E084 Phase B)
                      dcMatchTemplate: cfg.dc_plan?.match_template || prev.dcMatchTemplate,
                      dcMatchTiers: cfg.dc_plan?.match_tiers
                        ? cfg.dc_plan.match_tiers.map((t: any) => ({
                            deferralMin: (t.employee_min ?? 0) * 100,
                            deferralMax: (t.employee_max ?? 0) * 100,
                            matchRate: (t.match_rate ?? 0) * 100,
                          }))
                        : prev.dcMatchTiers,
                      // E046: Tenure/Points match mode
                      dcMatchMode: cfg.dc_plan?.match_status || prev.dcMatchMode,
                      dcTenureMatchTiers: cfg.dc_plan?.tenure_match_tiers?.length
                        ? cfg.dc_plan.tenure_match_tiers.map((t: any) => ({
                            minYears: t.min_years ?? 0,
                            maxYears: t.max_years ?? null,
                            matchRate: (t.match_rate ?? 0) * 100,
                            maxDeferralPct: (t.max_deferral_pct ?? 0) * 100,
                          }))
                        : prev.dcTenureMatchTiers,
                      dcPointsMatchTiers: cfg.dc_plan?.points_match_tiers?.length
                        ? cfg.dc_plan.points_match_tiers.map((t: any) => ({
                            minPoints: t.min_points ?? 0,
                            maxPoints: t.max_points ?? null,
                            matchRate: (t.match_rate ?? 0) * 100,
                            maxDeferralPct: (t.max_deferral_pct ?? 0) * 100,
                          }))
                        : prev.dcPointsMatchTiers,
                      // DC Plan - Match Eligibility
                      dcMatchMinTenureYears: cfg.dc_plan?.match_min_tenure_years ?? prev.dcMatchMinTenureYears,
                      dcMatchRequireYearEndActive: cfg.dc_plan?.match_require_year_end_active ?? prev.dcMatchRequireYearEndActive,
                      dcMatchMinHoursAnnual: cfg.dc_plan?.match_min_hours_annual ?? prev.dcMatchMinHoursAnnual,
                      dcMatchAllowTerminatedNewHires: cfg.dc_plan?.match_allow_terminated_new_hires ?? prev.dcMatchAllowTerminatedNewHires,
                      dcMatchAllowExperiencedTerminations: cfg.dc_plan?.match_allow_experienced_terminations ?? prev.dcMatchAllowExperiencedTerminations,
                      // DC Plan - Core Contribution
                      dcCoreEnabled: cfg.dc_plan?.core_enabled ?? prev.dcCoreEnabled,
                      dcCoreStatus: cfg.dc_plan?.core_status || prev.dcCoreStatus,
                      dcCoreContributionRate: cfg.dc_plan?.core_contribution_rate_percent ?? prev.dcCoreContributionRate,
                      dcCoreGradedSchedule: cfg.dc_plan?.core_graded_schedule
                        ? cfg.dc_plan.core_graded_schedule.map((tier: any) => ({
                            serviceYearsMin: tier.service_years_min,
                            serviceYearsMax: tier.service_years_max,
                            rate: (tier.contribution_rate ?? 0) * 100,
                          }))
                        : prev.dcCoreGradedSchedule,
                      // DC Plan - Core Eligibility (E084)
                      dcCoreMinTenureYears: cfg.dc_plan?.core_min_tenure_years ?? prev.dcCoreMinTenureYears,
                      dcCoreRequireYearEndActive: cfg.dc_plan?.core_require_year_end_active ?? prev.dcCoreRequireYearEndActive,
                      dcCoreMinHoursAnnual: cfg.dc_plan?.core_min_hours_annual ?? prev.dcCoreMinHoursAnnual,
                      dcCoreAllowTerminatedNewHires: cfg.dc_plan?.core_allow_terminated_new_hires ?? prev.dcCoreAllowTerminatedNewHires,
                      dcCoreAllowExperiencedTerminations: cfg.dc_plan?.core_allow_experienced_terminations ?? prev.dcCoreAllowExperiencedTerminations,
                      // DC Plan - Auto-Escalation
                      dcAutoEscalation: cfg.dc_plan?.auto_escalation ?? prev.dcAutoEscalation,
                      dcEscalationRate: cfg.dc_plan?.escalation_rate_percent ?? prev.dcEscalationRate,
                      dcEscalationCap: cfg.dc_plan?.escalation_cap_percent ?? prev.dcEscalationCap,
                      dcEscalationEffectiveDay: cfg.dc_plan?.escalation_effective_day || prev.dcEscalationEffectiveDay,
                      dcEscalationDelayYears: cfg.dc_plan?.escalation_delay_years ?? prev.dcEscalationDelayYears,
                      dcEscalationHireDateCutoff: cfg.dc_plan?.escalation_hire_date_cutoff || prev.dcEscalationHireDateCutoff,
                      // Advanced
                      engine: cfg.advanced?.engine || prev.engine,
                      enableMultithreading: cfg.advanced?.enable_multithreading ?? prev.enableMultithreading,
                      checkpointFrequency: cfg.advanced?.checkpoint_frequency || prev.checkpointFrequency,
                      memoryLimitGB: cfg.advanced?.memory_limit_gb ?? prev.memoryLimitGB,
                      logLevel: cfg.advanced?.log_level || prev.logLevel,
                      strictValidation: cfg.advanced?.strict_validation ?? prev.strictValidation,
                    }));

                    // E100: Validate census file
                    const censusPath = cfg.data_sources?.census_parquet_path;
                    if (censusPath && activeWorkspace?.id) {
                      try {
                        const validation = await validateFilePath(activeWorkspace.id, censusPath);
                        if (validation.valid && validation.row_count) {
                          setFormData(prev => ({
                            ...prev,
                            censusDataStatus: 'loaded',
                            censusRowCount: validation.row_count || prev.censusRowCount,
                            censusLastModified: validation.last_modified?.split('T')[0] || prev.censusLastModified,
                          }));
                        } else {
                          setFormData(prev => ({ ...prev, censusDataStatus: 'error' }));
                        }
                      } catch (validationError) {
                        console.error('E100: Census file validation failed:', validationError);
                        setFormData(prev => ({ ...prev, censusDataStatus: 'error' }));
                      }
                    }

                    // 313: Copy seed configs
                    if (cfg.promotion_hazard) {
                      const ph = cfg.promotion_hazard;
                      setPromotionHazardConfig({
                        base: { base_rate: ph.base_rate, level_dampener_factor: ph.level_dampener_factor },
                        age_multipliers: ph.age_multipliers || [],
                        tenure_multipliers: ph.tenure_multipliers || [],
                      });
                    }
                    if (cfg.age_bands && cfg.tenure_bands) {
                      setBandConfig({ age_bands: cfg.age_bands, tenure_bands: cfg.tenure_bands });
                    }

                    onClose();
                  } catch (error) {
                    console.error('Failed to copy scenario config:', error);
                  }
                }}
                className="w-full text-left p-4 border border-gray-200 rounded-lg hover:border-fidelity-green hover:bg-green-50 transition-colors"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-gray-900">{scenario.name}</h3>
                    <p className="text-sm text-gray-500 mt-1">{scenario.description || 'No description'}</p>
                  </div>
                  <span className={`px-2 py-1 text-xs font-medium rounded ${
                    scenario.status === 'completed' ? 'bg-green-100 text-green-700' :
                    scenario.status === 'running' ? 'bg-blue-100 text-blue-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {scenario.status || 'draft'}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
        <div className="p-4 border-t border-gray-200 bg-gray-50 flex-shrink-0 rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
