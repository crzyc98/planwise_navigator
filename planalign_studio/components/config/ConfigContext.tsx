import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react';
import type { FormData } from './types';
import { DEFAULT_FORM_DATA } from './constants';
import { buildConfigPayload } from './buildConfigPayload';
import {
  updateWorkspace as apiUpdateWorkspace,
  getScenario,
  getScenarioConfig,
  updateScenario,
  Scenario,
  Workspace,
  validateFilePath,
  getBandConfigs,
  BandConfig,
  BandValidationError,
  Band,
  getPromotionHazardConfig,
  PromotionHazardConfig,
} from '../../services/api';

// --- Context Type ---

export interface ConfigContextType {
  // Form state
  formData: FormData;
  setFormData: React.Dispatch<React.SetStateAction<FormData>>;
  savedFormData: FormData | null;

  // Seed config state (needed for dirty-tracking)
  promotionHazardConfig: PromotionHazardConfig | null;
  setPromotionHazardConfig: React.Dispatch<React.SetStateAction<PromotionHazardConfig | null>>;
  savedPromotionHazardConfig: PromotionHazardConfig | null;
  bandConfig: BandConfig | null;
  setBandConfig: React.Dispatch<React.SetStateAction<BandConfig | null>>;
  savedBandConfig: BandConfig | null;

  // Dirty tracking
  dirtySections: Set<string>;
  isDirty: boolean;

  // Save
  handleSaveConfig: () => Promise<void>;
  saveStatus: 'idle' | 'saving' | 'success' | 'error';
  saveMessage: string;

  // Generic handlers
  handleChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;
  inputProps: (name: string) => { name: string; value: any; onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void };

  // Route/workspace context
  activeWorkspace: Workspace;
  currentScenario: Scenario | null;
  scenarioId: string | undefined;
  scenarioLoading: boolean;
}

const ConfigContext = createContext<ConfigContextType | null>(null);

export function useConfigContext(): ConfigContextType {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error('useConfigContext must be used within a ConfigProvider');
  return ctx;
}

// --- Validation helpers (used by save handler) ---

function validateBandsClient(bands: Band[], bandType: 'age' | 'tenure'): BandValidationError[] {
  const errors: BandValidationError[] = [];
  if (bands.length === 0) {
    errors.push({ band_type: bandType, error_type: 'coverage', message: 'At least one band is required', band_ids: [] });
    return errors;
  }
  const sortedBands = [...bands].sort((a, b) => a.min_value - b.min_value);
  if (sortedBands[0].min_value !== 0) {
    errors.push({ band_type: bandType, error_type: 'coverage', message: `First band must start at 0, but starts at ${sortedBands[0].min_value}`, band_ids: [sortedBands[0].band_id] });
  }
  for (let i = 0; i < sortedBands.length; i++) {
    const band = sortedBands[i];
    if (band.max_value <= band.min_value) {
      errors.push({ band_type: bandType, error_type: 'invalid_range', message: `Band '${band.band_label}' has invalid range: max (${band.max_value}) must be > min (${band.min_value})`, band_ids: [band.band_id] });
    }
    if (i < sortedBands.length - 1) {
      const nextBand = sortedBands[i + 1];
      if (band.max_value < nextBand.min_value) {
        errors.push({ band_type: bandType, error_type: 'gap', message: `Gap detected between bands: ${band.max_value} to ${nextBand.min_value}`, band_ids: [band.band_id, nextBand.band_id] });
      }
      if (band.max_value > nextBand.min_value) {
        errors.push({ band_type: bandType, error_type: 'overlap', message: `Overlap detected between bands at value ${nextBand.min_value}`, band_ids: [band.band_id, nextBand.band_id] });
      }
    }
  }
  return errors;
}

function validatePromotionHazardConfigFn(config: PromotionHazardConfig): string[] {
  const errors: string[] = [];
  const baseRatePercent = config.base.base_rate * 100;
  const dampenerPercent = config.base.level_dampener_factor * 100;
  if (baseRatePercent < 0 || baseRatePercent > 100) errors.push('Base rate must be between 0% and 100%');
  if (dampenerPercent < 0 || dampenerPercent > 100) errors.push('Level dampener must be between 0% and 100%');
  for (const m of config.age_multipliers) {
    if (m.multiplier < 0) errors.push(`Age multiplier for band '${m.age_band}' must be non-negative`);
  }
  for (const m of config.tenure_multipliers) {
    if (m.multiplier < 0) errors.push(`Tenure multiplier for band '${m.tenure_band}' must be non-negative`);
  }
  return errors;
}

// --- Provider ---

interface ConfigProviderProps {
  activeWorkspace: Workspace;
  scenarioId: string | undefined;
  children: React.ReactNode;
}

export function ConfigProvider({ activeWorkspace, scenarioId, children }: ConfigProviderProps) {
  // Core form state
  const [formData, setFormData] = useState<FormData>(DEFAULT_FORM_DATA);
  const [savedFormData, setSavedFormData] = useState<FormData | null>(null);

  // Current scenario
  const [currentScenario, setCurrentScenario] = useState<Scenario | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(!!scenarioId);

  // Seed config state
  const [promotionHazardConfig, setPromotionHazardConfig] = useState<PromotionHazardConfig | null>(null);
  const [savedPromotionHazardConfig, setSavedPromotionHazardConfig] = useState<PromotionHazardConfig | null>(null);
  const [bandConfig, setBandConfig] = useState<BandConfig | null>(null);
  const [savedBandConfig, setSavedBandConfig] = useState<BandConfig | null>(null);

  // Save status
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState('');

  // --- useEffect 1: Load scenario config overlay ---
  useEffect(() => {
    const loadScenario = async () => {
      if (!scenarioId || !activeWorkspace?.id) {
        setCurrentScenario(null);
        setScenarioLoading(false);
        return;
      }

      setScenarioLoading(true);
      try {
        const scenario = await getScenario(activeWorkspace.id, scenarioId);
        setCurrentScenario(scenario);

        if (scenario.config_overrides) {
          const cfg = scenario.config_overrides;
          setFormData(prev => ({
            ...prev,
            // Simulation
            name: cfg.simulation?.name || prev.name,
            startYear: cfg.simulation?.start_year || prev.startYear,
            endYear: cfg.simulation?.end_year || prev.endYear,
            seed: cfg.simulation?.random_seed || prev.seed,
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

            // Data Sources
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
            jobLevelCompensation: cfg.new_hire?.job_level_compensation
              ? cfg.new_hire.job_level_compensation.map((d: any) => ({
                  level: d.level, name: d.name, minComp: d.min_compensation, maxComp: d.max_compensation,
                }))
              : prev.jobLevelCompensation,
            marketScenario: (['conservative', 'baseline', 'competitive', 'aggressive'].includes(cfg.new_hire?.market_scenario)
              ? cfg.new_hire.market_scenario : prev.marketScenario),
            levelMarketAdjustments: cfg.new_hire?.level_market_adjustments
              ? cfg.new_hire.level_market_adjustments.map((d: any) => ({ level: d.level, adjustment: d.adjustment_percent }))
              : prev.levelMarketAdjustments,

            // DC Plan - Basic
            dcEligibilityMonths: cfg.dc_plan?.eligibility_months ?? prev.dcEligibilityMonths,
            dcAutoEnroll: cfg.dc_plan?.auto_enroll ?? prev.dcAutoEnroll,
            dcDefaultDeferral: cfg.dc_plan?.default_deferral_percent ?? prev.dcDefaultDeferral,
            dcAutoEnrollWindowDays: cfg.dc_plan?.auto_enroll_window_days ?? prev.dcAutoEnrollWindowDays,
            dcAutoEnrollOptOutGracePeriod: cfg.dc_plan?.auto_enroll_opt_out_grace_period ?? prev.dcAutoEnrollOptOutGracePeriod,
            dcAutoEnrollScope: cfg.dc_plan?.auto_enroll_scope || prev.dcAutoEnrollScope,
            dcAutoEnrollHireDateCutoff: cfg.dc_plan?.auto_enroll_hire_date_cutoff || prev.dcAutoEnrollHireDateCutoff,
            dcMatchTemplate: cfg.dc_plan?.match_template || prev.dcMatchTemplate,
            dcMatchTiers: cfg.dc_plan?.match_tiers
              ? cfg.dc_plan.match_tiers.map((t: any) => ({
                  deferralMin: (t.employee_min ?? 0) * 100,
                  deferralMax: (t.employee_max ?? 0) * 100,
                  matchRate: (t.match_rate ?? 0) * 100,
                }))
              : prev.dcMatchTiers,
            dcMatchMode: cfg.dc_plan?.match_status || prev.dcMatchMode,
            dcTenureMatchTiers: cfg.dc_plan?.tenure_match_tiers
              ? cfg.dc_plan.tenure_match_tiers.map((t: any) => ({
                  minYears: t.min_years ?? 0,
                  maxYears: t.max_years ?? null,
                  matchRate: (t.match_rate != null && t.match_rate <= 1) ? t.match_rate * 100 : (t.match_rate ?? 0),
                  maxDeferralPct: (t.max_deferral_pct != null && t.max_deferral_pct <= 1) ? t.max_deferral_pct * 100 : (t.max_deferral_pct ?? 6),
                }))
              : prev.dcTenureMatchTiers,
            dcPointsMatchTiers: cfg.dc_plan?.points_match_tiers
              ? cfg.dc_plan.points_match_tiers.map((t: any) => ({
                  minPoints: t.min_points ?? 0,
                  maxPoints: t.max_points ?? null,
                  matchRate: (t.match_rate != null && t.match_rate <= 1) ? t.match_rate * 100 : (t.match_rate ?? 0),
                  maxDeferralPct: (t.max_deferral_pct != null && t.max_deferral_pct <= 1) ? t.max_deferral_pct * 100 : (t.max_deferral_pct ?? 6),
                }))
              : prev.dcPointsMatchTiers,
            dcMatchMinTenureYears: cfg.dc_plan?.match_min_tenure_years ?? prev.dcMatchMinTenureYears,
            dcMatchRequireYearEndActive: cfg.dc_plan?.match_require_year_end_active ?? prev.dcMatchRequireYearEndActive,
            dcMatchMinHoursAnnual: cfg.dc_plan?.match_min_hours_annual ?? prev.dcMatchMinHoursAnnual,
            dcMatchAllowTerminatedNewHires: cfg.dc_plan?.match_allow_terminated_new_hires ?? prev.dcMatchAllowTerminatedNewHires,
            dcMatchAllowExperiencedTerminations: cfg.dc_plan?.match_allow_experienced_terminations ?? prev.dcMatchAllowExperiencedTerminations,
            dcCoreEnabled: cfg.dc_plan?.core_enabled ?? prev.dcCoreEnabled,
            dcCoreStatus: cfg.dc_plan?.core_status || prev.dcCoreStatus,
            dcCoreContributionRate: cfg.dc_plan?.core_contribution_rate_percent ?? prev.dcCoreContributionRate,
            dcCoreGradedSchedule: cfg.dc_plan?.core_graded_schedule
              ? cfg.dc_plan.core_graded_schedule.map((tier: any) => ({
                  serviceYearsMin: tier.service_years_min,
                  serviceYearsMax: tier.service_years_max,
                  rate: tier.contribution_rate * 100,
                }))
              : prev.dcCoreGradedSchedule,
            dcCorePointsSchedule: cfg.dc_plan?.core_points_schedule
              ? cfg.dc_plan.core_points_schedule.map((tier: any) => ({
                  minPoints: tier.min_points ?? 0,
                  maxPoints: tier.max_points ?? null,
                  rate: (tier.contribution_rate != null && tier.contribution_rate <= 1) ? tier.contribution_rate * 100 : (tier.contribution_rate ?? 0),
                }))
              : prev.dcCorePointsSchedule,
            dcCoreMinTenureYears: cfg.dc_plan?.core_min_tenure_years ?? prev.dcCoreMinTenureYears,
            dcCoreRequireYearEndActive: cfg.dc_plan?.core_require_year_end_active ?? prev.dcCoreRequireYearEndActive,
            dcCoreMinHoursAnnual: cfg.dc_plan?.core_min_hours_annual ?? prev.dcCoreMinHoursAnnual,
            dcCoreAllowTerminatedNewHires: cfg.dc_plan?.core_allow_terminated_new_hires ?? prev.dcCoreAllowTerminatedNewHires,
            dcCoreAllowExperiencedTerminations: cfg.dc_plan?.core_allow_experienced_terminations ?? prev.dcCoreAllowExperiencedTerminations,
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

          // E089: Validate census file
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
              console.error('E089: Census file validation failed:', validationError);
              setFormData(prev => ({ ...prev, censusDataStatus: 'error' }));
            }
          }
        }
      } catch (err) {
        console.error('Failed to load scenario:', err);
        setCurrentScenario(null);
      } finally {
        setScenarioLoading(false);
      }
    };
    loadScenario();
  }, [scenarioId, activeWorkspace?.id]);

  // --- useEffect 2: Load config from workspace base_config ---
  useEffect(() => {
    if (!activeWorkspace?.base_config) return;
    const cfg = activeWorkspace.base_config;
    setFormData(prev => ({
      ...prev,
      // Simulation
      name: cfg.simulation?.name || prev.name,
      startYear: cfg.simulation?.start_year || prev.startYear,
      endYear: cfg.simulation?.end_year || prev.endYear,
      seed: cfg.simulation?.random_seed || prev.seed,
      targetGrowthRate: (cfg.simulation?.target_growth_rate || 0.03) * 100,
      // Workforce
      totalTerminationRate: (cfg.workforce?.total_termination_rate || 0.12) * 100,
      newHireTerminationRate: (cfg.workforce?.new_hire_termination_rate || 0.25) * 100,
      // Compensation
      meritBudget: cfg.compensation?.merit_budget_percent || prev.meritBudget,
      colaRate: cfg.compensation?.cola_rate_percent || prev.colaRate,
      promoIncrease: cfg.compensation?.promotion_increase_percent || prev.promoIncrease,
      promoDistributionRange: cfg.compensation?.promotion_distribution_range_percent ?? prev.promoDistributionRange,
      promoBudget: cfg.compensation?.promotion_budget_percent || prev.promoBudget,
      promoRateMultiplier: cfg.compensation?.promotion_rate_multiplier ?? prev.promoRateMultiplier,
      // New Hire
      newHireStrategy: cfg.new_hire?.strategy || prev.newHireStrategy,
      targetPercentile: cfg.new_hire?.target_percentile || prev.targetPercentile,
      newHireCompVariance: cfg.new_hire?.compensation_variance_percent || prev.newHireCompVariance,
      newHireAgeDistribution: cfg.new_hire?.age_distribution
        ? cfg.new_hire.age_distribution.map((d: any, idx: number) => ({
            age: d.age, weight: d.weight, description: prev.newHireAgeDistribution[idx]?.description || '',
          }))
        : prev.newHireAgeDistribution,
      levelDistributionMode: cfg.new_hire?.level_distribution_mode || prev.levelDistributionMode,
      newHireLevelDistribution: cfg.new_hire?.level_distribution
        ? cfg.new_hire.level_distribution.map((d: any, idx: number) => ({
            level: d.level, name: prev.newHireLevelDistribution[idx]?.name || `Level ${d.level}`,
            percentage: d.percentage * 100,
          }))
        : prev.newHireLevelDistribution,
      jobLevelCompensation: cfg.new_hire?.job_level_compensation
        ? cfg.new_hire.job_level_compensation.map((d: any) => ({
            level: d.level, name: d.name, minComp: d.min_compensation, maxComp: d.max_compensation,
          }))
        : prev.jobLevelCompensation,
      marketScenario: (['conservative', 'baseline', 'competitive', 'aggressive'].includes(cfg.new_hire?.market_scenario)
        ? cfg.new_hire.market_scenario : prev.marketScenario),
      levelMarketAdjustments: cfg.new_hire?.level_market_adjustments
        ? cfg.new_hire.level_market_adjustments.map((d: any) => ({ level: d.level, adjustment: d.adjustment_percent }))
        : prev.levelMarketAdjustments,
      // DC Plan
      dcEligibilityMonths: cfg.dc_plan?.eligibility_months || prev.dcEligibilityMonths,
      dcAutoEnroll: cfg.dc_plan?.auto_enroll ?? prev.dcAutoEnroll,
      dcDefaultDeferral: cfg.dc_plan?.default_deferral_percent || prev.dcDefaultDeferral,
      dcMatchTemplate: cfg.dc_plan?.match_template || prev.dcMatchTemplate,
      dcMatchTiers: cfg.dc_plan?.match_tiers
        ? cfg.dc_plan.match_tiers.map((t: any) => ({
            deferralMin: (t.employee_min ?? 0) * 100,
            deferralMax: (t.employee_max ?? 0) * 100,
            matchRate: (t.match_rate ?? 0) * 100,
          }))
        : prev.dcMatchTiers,
      dcMatchMode: cfg.dc_plan?.match_status || prev.dcMatchMode,
      dcTenureMatchTiers: cfg.dc_plan?.tenure_match_tiers
        ? cfg.dc_plan.tenure_match_tiers.map((t: any) => ({
            minYears: t.min_years ?? 0, maxYears: t.max_years ?? null,
            matchRate: (t.match_rate != null && t.match_rate <= 1) ? t.match_rate * 100 : (t.match_rate ?? 0),
            maxDeferralPct: (t.max_deferral_pct != null && t.max_deferral_pct <= 1) ? t.max_deferral_pct * 100 : (t.max_deferral_pct ?? 6),
          }))
        : prev.dcTenureMatchTiers,
      dcPointsMatchTiers: cfg.dc_plan?.points_match_tiers
        ? cfg.dc_plan.points_match_tiers.map((t: any) => ({
            minPoints: t.min_points ?? 0, maxPoints: t.max_points ?? null,
            matchRate: (t.match_rate != null && t.match_rate <= 1) ? t.match_rate * 100 : (t.match_rate ?? 0),
            maxDeferralPct: (t.max_deferral_pct != null && t.max_deferral_pct <= 1) ? t.max_deferral_pct * 100 : (t.max_deferral_pct ?? 6),
          }))
        : prev.dcPointsMatchTiers,
      dcAutoEscalation: cfg.dc_plan?.auto_escalation ?? prev.dcAutoEscalation,
      dcEscalationRate: cfg.dc_plan?.escalation_rate_percent || prev.dcEscalationRate,
      dcEscalationCap: cfg.dc_plan?.escalation_cap_percent || prev.dcEscalationCap,
      // Advanced
      engine: cfg.advanced?.engine || prev.engine,
      enableMultithreading: cfg.advanced?.enable_multithreading ?? prev.enableMultithreading,
      checkpointFrequency: cfg.advanced?.checkpoint_frequency || prev.checkpointFrequency,
      memoryLimitGB: cfg.advanced?.memory_limit_gb || prev.memoryLimitGB,
      logLevel: cfg.advanced?.log_level || prev.logLevel,
      strictValidation: cfg.advanced?.strict_validation ?? prev.strictValidation,
    }));
  }, [activeWorkspace?.base_config]);

  // --- useEffect 3: Load seed configs (bands + promotion hazard) ---
  useEffect(() => {
    const loadSeedConfigs = async () => {
      if (!activeWorkspace?.id) return;
      try {
        if (scenarioId) {
          const mergedConfig = await getScenarioConfig(activeWorkspace.id, scenarioId);
          if (mergedConfig.promotion_hazard) {
            const ph = mergedConfig.promotion_hazard;
            const phConfig: PromotionHazardConfig = {
              base: { base_rate: ph.base_rate, level_dampener_factor: ph.level_dampener_factor },
              age_multipliers: ph.age_multipliers || [],
              tenure_multipliers: ph.tenure_multipliers || [],
            };
            setPromotionHazardConfig(phConfig);
            setSavedPromotionHazardConfig(JSON.parse(JSON.stringify(phConfig)));
          }
          if (mergedConfig.age_bands && mergedConfig.tenure_bands) {
            const bc: BandConfig = { age_bands: mergedConfig.age_bands, tenure_bands: mergedConfig.tenure_bands };
            setBandConfig(bc);
            setSavedBandConfig(JSON.parse(JSON.stringify(bc)));
          }
        } else {
          const [bandCfg, phCfg] = await Promise.all([
            getBandConfigs(activeWorkspace.id),
            getPromotionHazardConfig(activeWorkspace.id),
          ]);
          setBandConfig(bandCfg);
          setSavedBandConfig(JSON.parse(JSON.stringify(bandCfg)));
          setPromotionHazardConfig(phCfg);
          setSavedPromotionHazardConfig(JSON.parse(JSON.stringify(phCfg)));
        }
      } catch (error) {
        console.error('Failed to load seed configurations:', error);
      }
    };
    loadSeedConfigs();
  }, [activeWorkspace?.id, scenarioId]);

  // --- useEffect 4: savedFormData snapshot ---
  useEffect(() => {
    if (savedFormData === null && (activeWorkspace?.base_config || currentScenario?.config_overrides)) {
      setSavedFormData({ ...formData });
    }
  }, [formData, activeWorkspace?.base_config, currentScenario?.config_overrides, savedFormData]);

  // --- useEffect 5: beforeunload warning ---
  const isDirty = useMemo(() => {
    if (!savedFormData) return false;
    const formDirty = JSON.stringify(formData) !== JSON.stringify(savedFormData);
    const promotionHazardDirty = JSON.stringify(promotionHazardConfig) !== JSON.stringify(savedPromotionHazardConfig);
    const bandDirty = JSON.stringify(bandConfig) !== JSON.stringify(savedBandConfig);
    return formDirty || promotionHazardDirty || bandDirty;
  }, [formData, savedFormData, promotionHazardConfig, savedPromotionHazardConfig, bandConfig, savedBandConfig]);

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  // --- dirtySections ---
  const dirtySections = useMemo(() => {
    if (!savedFormData) return new Set<string>();
    const dirty = new Set<string>();

    if (formData.name !== savedFormData.name ||
        formData.startYear !== savedFormData.startYear ||
        formData.endYear !== savedFormData.endYear ||
        formData.seed !== savedFormData.seed ||
        formData.targetGrowthRate !== savedFormData.targetGrowthRate) {
      dirty.add('simulation');
    }
    if (formData.censusDataPath !== savedFormData.censusDataPath) {
      dirty.add('datasources');
    }
    if (formData.meritBudget !== savedFormData.meritBudget ||
        formData.colaRate !== savedFormData.colaRate ||
        formData.promoIncrease !== savedFormData.promoIncrease ||
        formData.promoDistributionRange !== savedFormData.promoDistributionRange ||
        formData.promoBudget !== savedFormData.promoBudget ||
        formData.promoRateMultiplier !== savedFormData.promoRateMultiplier) {
      dirty.add('compensation');
    }
    if (formData.newHireStrategy !== savedFormData.newHireStrategy ||
        formData.targetPercentile !== savedFormData.targetPercentile ||
        formData.newHireCompVariance !== savedFormData.newHireCompVariance ||
        formData.levelDistributionMode !== savedFormData.levelDistributionMode ||
        formData.marketScenario !== savedFormData.marketScenario ||
        JSON.stringify(formData.newHireAgeDistribution) !== JSON.stringify(savedFormData.newHireAgeDistribution) ||
        JSON.stringify(formData.newHireLevelDistribution) !== JSON.stringify(savedFormData.newHireLevelDistribution) ||
        JSON.stringify(formData.jobLevelCompensation) !== JSON.stringify(savedFormData.jobLevelCompensation) ||
        JSON.stringify(formData.levelMarketAdjustments) !== JSON.stringify(savedFormData.levelMarketAdjustments)) {
      dirty.add('newhire');
    }
    if (formData.totalTerminationRate !== savedFormData.totalTerminationRate ||
        formData.newHireTerminationRate !== savedFormData.newHireTerminationRate) {
      dirty.add('turnover');
    }
    if (formData.dcEligibilityMonths !== savedFormData.dcEligibilityMonths ||
        formData.dcAutoEnroll !== savedFormData.dcAutoEnroll ||
        formData.dcDefaultDeferral !== savedFormData.dcDefaultDeferral ||
        formData.dcMatchTemplate !== savedFormData.dcMatchTemplate ||
        JSON.stringify(formData.dcMatchTiers) !== JSON.stringify(savedFormData.dcMatchTiers) ||
        formData.dcAutoEscalation !== savedFormData.dcAutoEscalation ||
        formData.dcEscalationRate !== savedFormData.dcEscalationRate ||
        formData.dcEscalationCap !== savedFormData.dcEscalationCap) {
      dirty.add('dcplan');
    }
    if (formData.engine !== savedFormData.engine ||
        formData.enableMultithreading !== savedFormData.enableMultithreading ||
        formData.checkpointFrequency !== savedFormData.checkpointFrequency ||
        formData.memoryLimitGB !== savedFormData.memoryLimitGB ||
        formData.logLevel !== savedFormData.logLevel ||
        formData.strictValidation !== savedFormData.strictValidation) {
      dirty.add('advanced');
    }
    if (JSON.stringify(promotionHazardConfig) !== JSON.stringify(savedPromotionHazardConfig)) {
      dirty.add('compensation');
    }
    if (JSON.stringify(bandConfig) !== JSON.stringify(savedBandConfig)) {
      dirty.add('segmentation');
    }
    return dirty;
  }, [formData, savedFormData, promotionHazardConfig, savedPromotionHazardConfig, bandConfig, savedBandConfig]);

  // --- Handlers ---
  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value
    }));
  }, []);

  const inputProps = useCallback((name: string) => ({
    name,
    value: (formData as any)[name],
    onChange: handleChange,
  }), [formData, handleChange]);

  const handleSaveConfig = useCallback(async () => {
    // Flush pending edits
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

    setSaveStatus('saving');
    setSaveMessage('Saving configuration...');

    try {
      const configPayload = buildConfigPayload(formData, promotionHazardConfig, bandConfig);

      // Validate seed configs before save
      if (promotionHazardConfig) {
        const hazardErrors = validatePromotionHazardConfigFn(promotionHazardConfig);
        if (hazardErrors.length > 0) {
          setSaveStatus('error');
          setSaveMessage(hazardErrors.join('; '));
          return;
        }
      }
      if (bandConfig) {
        const ageErrors = validateBandsClient(bandConfig.age_bands, 'age');
        const tenureErrors = validateBandsClient(bandConfig.tenure_bands, 'tenure');
        const allBandErrors = [...ageErrors, ...tenureErrors];
        if (allBandErrors.length > 0) {
          setSaveStatus('error');
          setSaveMessage(allBandErrors.map(e => e.message).join('; '));
          return;
        }
      }

      if (currentScenario && scenarioId) {
        await updateScenario(activeWorkspace.id, scenarioId, { config_overrides: configPayload });
        console.log('Config saved to scenario:', scenarioId, configPayload);
      } else {
        await apiUpdateWorkspace(activeWorkspace.id, { base_config: configPayload });
        console.log('Config saved to workspace:', activeWorkspace.id, configPayload);
      }

      setSaveStatus('success');
      setSaveMessage('Configuration saved successfully!');

      setSavedFormData({ ...formData });
      if (promotionHazardConfig) {
        setSavedPromotionHazardConfig(JSON.parse(JSON.stringify(promotionHazardConfig)));
      }
      if (bandConfig) {
        setSavedBandConfig(JSON.parse(JSON.stringify(bandConfig)));
      }

      setTimeout(() => { setSaveStatus('idle'); setSaveMessage(''); }, 3000);
    } catch (error) {
      setSaveStatus('error');
      setSaveMessage(error instanceof Error ? error.message : 'Failed to save configuration');
    }
  }, [formData, promotionHazardConfig, bandConfig, currentScenario, scenarioId, activeWorkspace]);

  const value = useMemo<ConfigContextType>(() => ({
    formData, setFormData, savedFormData,
    promotionHazardConfig, setPromotionHazardConfig, savedPromotionHazardConfig,
    bandConfig, setBandConfig, savedBandConfig,
    dirtySections, isDirty,
    handleSaveConfig, saveStatus, saveMessage,
    handleChange, inputProps,
    activeWorkspace, currentScenario, scenarioId, scenarioLoading,
  }), [
    formData, savedFormData,
    promotionHazardConfig, savedPromotionHazardConfig,
    bandConfig, savedBandConfig,
    dirtySections, isDirty,
    handleSaveConfig, saveStatus, saveMessage,
    handleChange, inputProps,
    activeWorkspace, currentScenario, scenarioId, scenarioLoading,
  ]);

  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}
