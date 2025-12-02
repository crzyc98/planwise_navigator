import React, { useState, useEffect, useRef, useMemo, useCallback, useContext } from 'react';
import { Save, AlertTriangle, FileText, Settings, HelpCircle, TrendingUp, Users, DollarSign, Zap, Server, Shield, PieChart, Database, Upload, Check, X, ArrowLeft, Target, Sparkles, Play } from 'lucide-react';
import { useNavigate, useOutletContext, useParams, useBlocker, UNSAFE_DataRouterContext } from 'react-router-dom';
import { LayoutContextType } from './Layout';
import { updateWorkspace as apiUpdateWorkspace, getScenario, updateScenario, Scenario, uploadCensusFile, validateFilePath, listTemplates, Template, analyzeAgeDistribution, analyzeCompensation, CompensationAnalysis, solveCompensationGrowth, CompensationSolverResponse } from '../services/api';

// Navigation blocker component - only rendered when in a data router context
// This prevents useBlocker from throwing when using <BrowserRouter>
interface NavigationBlockerProps {
  isDirty: boolean;
  dirtySections: Set<string>;
}

function NavigationBlocker({ isDirty, dirtySections }: NavigationBlockerProps) {
  const blocker = useBlocker(isDirty);

  if (blocker.state !== 'blocked') return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
        <div className="p-6">
          <div className="flex items-center mb-4">
            <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center mr-3">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900">Unsaved Changes</h3>
          </div>
          <p className="text-gray-600 mb-2">
            You have unsaved changes in {dirtySections.size} section{dirtySections.size !== 1 ? 's' : ''}:
          </p>
          <ul className="text-sm text-gray-500 mb-4 ml-4 list-disc">
            {Array.from(dirtySections).map(section => (
              <li key={section} className="capitalize">
                {section === 'newhire' ? 'New Hire Strategy' :
                 section === 'dcplan' ? 'DC Plan' :
                 section === 'datasources' ? 'Data Sources' :
                 section.charAt(0).toUpperCase() + section.slice(1)}
              </li>
            ))}
          </ul>
          <p className="text-gray-600">
            Are you sure you want to leave? Your changes will be lost.
          </p>
        </div>
        <div className="px-6 py-4 bg-gray-50 flex justify-end space-x-3">
          <button
            onClick={() => blocker.reset?.()}
            className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors font-medium"
          >
            Stay on Page
          </button>
          <button
            onClick={() => blocker.proceed?.()}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors font-medium"
          >
            Leave Without Saving
          </button>
        </div>
      </div>
    </div>
  );
}

// InputField component defined OUTSIDE ConfigStudio to prevent re-creation on every render
interface InputFieldProps {
  label: string;
  name: string;
  value: any;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  width?: string;
  suffix?: string;
  helper?: string;
  step?: string;
  min?: number;
}

const InputField: React.FC<InputFieldProps> = ({
  label,
  name,
  value,
  onChange,
  type = "text",
  width = "col-span-3",
  suffix = "",
  helper = "",
  step = "1",
  min
}) => (
  <div className={`sm:${width}`}>
    <label className="block text-sm font-medium text-gray-700">{label}</label>
    <div className="mt-1 relative rounded-md shadow-sm">
      <input
        type={type}
        name={name}
        value={value}
        onChange={onChange}
        step={step}
        min={min}
        className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
      />
      {suffix && (
        <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
          <span className="text-gray-500 sm:text-sm">{suffix}</span>
        </div>
      )}
    </div>
    {helper && <p className="mt-1 text-xs text-gray-500">{helper}</p>}
  </div>
);

export default function ConfigStudio() {
  const navigate = useNavigate();
  const { scenarioId } = useParams<{ scenarioId?: string }>();
  const { activeWorkspace } = useOutletContext<LayoutContextType>();
  const [activeSection, setActiveSection] = useState('simulation');

  // Current scenario being edited (null = editing base config)
  const [currentScenario, setCurrentScenario] = useState<Scenario | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);

  // File upload state
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  const [uploadMessage, setUploadMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Template modal state
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  // Compensation solver state
  const [targetCompGrowth, setTargetCompGrowth] = useState<number>(5.0); // Target comp growth %
  const [solverStatus, setSolverStatus] = useState<'idle' | 'solving' | 'success' | 'error'>('idle');
  const [solverResult, setSolverResult] = useState<CompensationSolverResponse | null>(null);
  const [solverError, setSolverError] = useState<string>('');

  // Expanded State for all tabs
  const [formData, setFormData] = useState({
    // Data Sources
    censusDataPath: 'data/census_preprocessed.parquet',
    censusDataStatus: 'loaded', // 'not_loaded' | 'loaded' | 'error'
    censusRowCount: 1000,
    censusLastModified: '2025-01-15',

    // Simulation
    name: 'Baseline 2025-2027',
    startYear: 2025,
    endYear: 2027,
    seed: 42,
    targetGrowthRate: 3.0, // Target workforce growth rate (%)

    // Compensation
    meritBudget: 3.5,
    colaRate: 2.0,
    promoIncrease: 12.5,
    promoDistributionRange: 5.0, // +/- 5%
    promoBudget: 1.5,
    promoRateMultiplier: 1.0, // Multiplier for promotion rates (1.0 = use seed defaults)

    // New Hire
    newHireStrategy: 'percentile', // 'percentile' | 'fixed'
    targetPercentile: 50,
    newHireCompVariance: 5.0, // +/- 5%

    // E082: New Hire Demographics
    newHireAgeDistribution: [
      { age: 22, weight: 0.05, description: 'Recent college graduates' },
      { age: 25, weight: 0.15, description: 'Early career' },
      { age: 28, weight: 0.20, description: 'Established early career' },
      { age: 32, weight: 0.25, description: 'Mid-career switchers' },
      { age: 35, weight: 0.15, description: 'Experienced hires' },
      { age: 40, weight: 0.10, description: 'Senior experienced' },
      { age: 45, weight: 0.08, description: 'Mature professionals' },
      { age: 50, weight: 0.02, description: 'Late career changes' },
    ],
    levelDistributionMode: 'adaptive' as 'adaptive' | 'fixed',
    newHireLevelDistribution: [
      { level: 1, name: 'Staff', percentage: 50 },
      { level: 2, name: 'Manager', percentage: 25 },
      { level: 3, name: 'Sr Manager', percentage: 15 },
      { level: 4, name: 'Director', percentage: 8 },
      { level: 5, name: 'VP', percentage: 2 },
    ],

    // E082: Job Level Compensation Ranges
    jobLevelCompensation: [
      { level: 1, name: 'Staff', minComp: 56000, maxComp: 80000 },
      { level: 2, name: 'Manager', minComp: 81000, maxComp: 120000 },
      { level: 3, name: 'Sr Manager', minComp: 121000, maxComp: 160000 },
      { level: 4, name: 'Director', minComp: 161000, maxComp: 300000 },
      { level: 5, name: 'VP', minComp: 275000, maxComp: 500000 },
    ],

    // E082: Market Scenario
    marketScenario: 'baseline' as 'conservative' | 'baseline' | 'competitive' | 'aggressive',
    levelMarketAdjustments: [
      { level: 1, adjustment: 0 },
      { level: 2, adjustment: 0 },
      { level: 3, adjustment: 0 },
      { level: 4, adjustment: 0 },
      { level: 5, adjustment: 0 },
    ],

    // Workforce & Turnover
    totalTerminationRate: 12.0, // Overall termination rate (%)
    newHireTerminationRate: 25.0, // New hire termination rate (%)
    baseTurnoverRate: 12.0,
    regrettableFactor: 0.6,
    involuntaryRate: 2.0,
    turnoverBands: {
      year1: 25.0,    // High risk
      year2_3: 15.0,  // Medium risk
      year4_plus: 8.0 // Low risk (stable)
    },

    // DC Plan
    dcEligibilityMonths: 3,
    dcAutoEnroll: true,
    dcDefaultDeferral: 3.0,
    dcMatchFormula: 'simple', // 'simple', 'tiered', 'stretch'
    dcMatchPercent: 50,
    dcMatchLimit: 6,
    dcVestingSchedule: 'cliff_3',
    dcAutoEscalation: true,
    dcEscalationRate: 1.0,
    dcEscalationCap: 10.0,

    // Advanced Settings
    engine: 'polars',
    enableMultithreading: true,
    checkpointFrequency: 'year', // 'year', 'stage', 'none'
    memoryLimitGB: 4.0,
    logLevel: 'INFO',
    strictValidation: true
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value
    }));
  };

  const handleNestedChange = (parent: string, key: string, value: string) => {
    setFormData((prev: any) => ({
      ...prev,
      [parent]: {
        ...prev[parent],
        [key]: parseFloat(value) || 0
      }
    }));
  };

  // E082: Handler for age distribution weight changes
  const handleAgeWeightChange = (index: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      newHireAgeDistribution: prev.newHireAgeDistribution.map((row, i) =>
        i === index ? { ...row, weight: parseFloat(value) / 100 || 0 } : row
      )
    }));
  };

  // E082: Handler for level distribution percentage changes
  const handleLevelPercentageChange = (index: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      newHireLevelDistribution: prev.newHireLevelDistribution.map((row, i) =>
        i === index ? { ...row, percentage: parseFloat(value) || 0 } : row
      )
    }));
  };

  // E082: State for "Match Census" loading (age distribution)
  const [matchCensusLoading, setMatchCensusLoading] = useState(false);
  const [matchCensusError, setMatchCensusError] = useState<string | null>(null);
  const [matchCensusSuccess, setMatchCensusSuccess] = useState(false);

  // E082: State for "Match Census" compensation analysis
  const [matchCompLoading, setMatchCompLoading] = useState(false);
  const [matchCompError, setMatchCompError] = useState<string | null>(null);
  const [matchCompSuccess, setMatchCompSuccess] = useState(false);
  const [compensationAnalysis, setCompensationAnalysis] = useState<CompensationAnalysis | null>(null);
  const [compLookbackYears, setCompLookbackYears] = useState<number>(4); // Default 4 years lookback
  const [compScaleFactor, setCompScaleFactor] = useState<number>(1.0); // Multiplier to scale up/down ranges

  // E082: Handler for job level compensation changes
  const handleJobLevelCompChange = (index: number, field: 'minComp' | 'maxComp', value: string) => {
    setFormData(prev => ({
      ...prev,
      jobLevelCompensation: prev.jobLevelCompensation.map((row, i) =>
        i === index ? { ...row, [field]: parseFloat(value) || 0 } : row
      )
    }));
  };

  // E082: Handler for level market adjustment changes
  const handleLevelAdjustmentChange = (index: number, value: string) => {
    setFormData(prev => ({
      ...prev,
      levelMarketAdjustments: prev.levelMarketAdjustments.map((row, i) =>
        i === index ? { ...row, adjustment: parseFloat(value) || 0 } : row
      )
    }));
  };

  // E082: Handler for "Match Census" compensation button
  const handleMatchCompensation = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) {
      setMatchCompError('Please upload a census file first');
      return;
    }

    setMatchCompLoading(true);
    setMatchCompError(null);
    setMatchCompSuccess(false);

    try {
      // Pass the lookback years setting to analyze recent hires
      const result = await analyzeCompensation(activeWorkspace.id, formData.censusDataPath, compLookbackYears);
      setCompensationAnalysis(result);

      // Apply scale factor to adjust ranges (e.g., 1.5x to hire at 150% of census-derived ranges)
      const scale = compScaleFactor;

      // If we have suggested levels (no level data in census), apply them
      if (!result.has_level_data && result.suggested_levels) {
        setFormData(prev => ({
          ...prev,
          jobLevelCompensation: result.suggested_levels!.map(sl => ({
            level: sl.level,
            name: sl.name,
            minComp: Math.round(sl.suggested_min * scale),
            maxComp: Math.round(sl.suggested_max * scale),
          }))
        }));
        setMatchCompSuccess(true);
        setTimeout(() => setMatchCompSuccess(false), 3000);
      } else if (result.has_level_data && result.levels) {
        // Apply actual level data from census (with scale factor)
        setFormData(prev => ({
          ...prev,
          jobLevelCompensation: result.levels!.map(l => ({
            level: l.level,
            name: l.name,
            minComp: Math.round(l.min_compensation * scale),
            maxComp: Math.round(l.max_compensation * scale),
          }))
        }));
        setMatchCompSuccess(true);
        setTimeout(() => setMatchCompSuccess(false), 3000);
      }
    } catch (error) {
      console.error('Failed to analyze compensation:', error);
      setMatchCompError(error instanceof Error ? error.message : 'Failed to analyze compensation');
    } finally {
      setMatchCompLoading(false);
    }
  };

  // E082: Market scenario multipliers
  const marketMultipliers = {
    conservative: { label: 'Conservative', adjustment: -5, description: 'Below market (cost savings focus)' },
    baseline: { label: 'Baseline', adjustment: 0, description: 'At market (competitive positioning)' },
    competitive: { label: 'Competitive', adjustment: 5, description: 'Above market (talent attraction focus)' },
    aggressive: { label: 'Aggressive', adjustment: 10, description: 'Well above market (premium talent strategy)' },
  };

  // Handler for compensation growth solver ("magic button")
  const handleSolveCompensation = async () => {
    if (!activeWorkspace?.id) {
      setSolverError('No workspace selected');
      setSolverStatus('error');
      return;
    }

    setSolverStatus('solving');
    setSolverError('');
    setSolverResult(null);

    try {
      // Call the solver API with target growth rate AND workforce dynamics
      // The solver now correctly accounts for turnover and new hire compensation effects
      const result = await solveCompensationGrowth(activeWorkspace.id, {
        file_path: formData.censusDataPath || undefined,
        target_growth_rate: targetCompGrowth / 100, // Convert % to decimal
        promotion_increase: formData.promoIncrease / 100, // Use current promo increase as constraint
        // Workforce dynamics - critical for accurate modeling
        turnover_rate: formData.totalTerminationRate / 100, // Use the configured turnover rate
        workforce_growth_rate: formData.targetGrowthRate / 100, // Use the configured workforce growth rate
        new_hire_comp_ratio: 0.85, // Default: new hires at 85% of avg (could be made configurable)
      });

      setSolverResult(result);
      setSolverStatus('success');

      // Auto-apply the solved values to the form
      setFormData(prev => ({
        ...prev,
        colaRate: result.cola_rate,
        meritBudget: result.merit_budget,
        promoIncrease: result.promotion_increase,
        promoBudget: result.promotion_budget,
      }));

    } catch (error) {
      console.error('Failed to solve compensation:', error);
      setSolverError(error instanceof Error ? error.message : 'Failed to solve');
      setSolverStatus('error');
    }
  };

  // E082: Handler for "Match Census" button (age distribution)
  const handleMatchCensus = async () => {
    if (!activeWorkspace?.id || !formData.censusDataPath) {
      setMatchCensusError('Please upload a census file first');
      return;
    }

    setMatchCensusLoading(true);
    setMatchCensusError(null);
    setMatchCensusSuccess(false);

    try {
      const result = await analyzeAgeDistribution(activeWorkspace.id, formData.censusDataPath);

      // Update form data with the analyzed distribution
      setFormData(prev => ({
        ...prev,
        newHireAgeDistribution: result.distribution.map(d => ({
          age: d.age,
          weight: d.weight,
          description: d.description,
        }))
      }));

      setMatchCensusSuccess(true);
      setTimeout(() => setMatchCensusSuccess(false), 3000);
    } catch (error) {
      console.error('Failed to analyze census:', error);
      setMatchCensusError(error instanceof Error ? error.message : 'Failed to analyze census');
    } finally {
      setMatchCensusLoading(false);
    }
  };

  // Save status state
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState('');

  // Track saved state for dirty detection (Option 3: Persist Draft + Warn on Page Leave)
  const [savedFormData, setSavedFormData] = useState<typeof formData | null>(null);


  // Load scenario if scenarioId is provided
  useEffect(() => {
    const loadScenario = async () => {
      if (!scenarioId || !activeWorkspace?.id) {
        setCurrentScenario(null);
        return;
      }

      setScenarioLoading(true);
      try {
        const scenario = await getScenario(activeWorkspace.id, scenarioId);
        setCurrentScenario(scenario);

        // Load scenario-specific config overrides into form
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
                  percentage: d.percentage * 100, // Convert from decimal
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
            marketScenario: cfg.new_hire?.market_scenario || prev.marketScenario,
            levelMarketAdjustments: cfg.new_hire?.level_market_adjustments
              ? cfg.new_hire.level_market_adjustments.map((d: any) => ({
                  level: d.level,
                  adjustment: d.adjustment_percent,
                }))
              : prev.levelMarketAdjustments,

            // Turnover
            baseTurnoverRate: cfg.turnover?.base_rate_percent ?? prev.baseTurnoverRate,
            regrettableFactor: cfg.turnover?.regrettable_factor ?? prev.regrettableFactor,
            involuntaryRate: cfg.turnover?.involuntary_rate_percent ?? prev.involuntaryRate,
            turnoverBands: cfg.turnover?.tenure_bands || prev.turnoverBands,

            // DC Plan
            dcEligibilityMonths: cfg.dc_plan?.eligibility_months ?? prev.dcEligibilityMonths,
            dcAutoEnroll: cfg.dc_plan?.auto_enroll ?? prev.dcAutoEnroll,
            dcDefaultDeferral: cfg.dc_plan?.default_deferral_percent ?? prev.dcDefaultDeferral,
            dcMatchFormula: cfg.dc_plan?.match_formula || prev.dcMatchFormula,
            dcMatchPercent: cfg.dc_plan?.match_percent ?? prev.dcMatchPercent,
            dcMatchLimit: cfg.dc_plan?.match_limit_percent ?? prev.dcMatchLimit,
            dcVestingSchedule: cfg.dc_plan?.vesting_schedule || prev.dcVestingSchedule,
            dcAutoEscalation: cfg.dc_plan?.auto_escalation ?? prev.dcAutoEscalation,
            dcEscalationRate: cfg.dc_plan?.escalation_rate_percent ?? prev.dcEscalationRate,
            dcEscalationCap: cfg.dc_plan?.escalation_cap_percent ?? prev.dcEscalationCap,

            // Advanced
            engine: cfg.advanced?.engine || prev.engine,
            enableMultithreading: cfg.advanced?.enable_multithreading ?? prev.enableMultithreading,
            checkpointFrequency: cfg.advanced?.checkpoint_frequency || prev.checkpointFrequency,
            memoryLimitGB: cfg.advanced?.memory_limit_gb ?? prev.memoryLimitGB,
            logLevel: cfg.advanced?.log_level || prev.logLevel,
            strictValidation: cfg.advanced?.strict_validation ?? prev.strictValidation,
          }));
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

  // Load config from workspace when it changes
  useEffect(() => {
    if (!activeWorkspace?.base_config) return;

    const cfg = activeWorkspace.base_config;
    setFormData(prev => ({
      ...prev,
      // Data Sources
      censusDataPath: cfg.data_sources?.census_parquet_path || prev.censusDataPath,

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
            percentage: d.percentage * 100, // Convert from decimal
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
      marketScenario: cfg.new_hire?.market_scenario || prev.marketScenario,
      levelMarketAdjustments: cfg.new_hire?.level_market_adjustments
        ? cfg.new_hire.level_market_adjustments.map((d: any) => ({
            level: d.level,
            adjustment: d.adjustment_percent,
          }))
        : prev.levelMarketAdjustments,

      // Turnover
      baseTurnoverRate: cfg.turnover?.base_rate_percent || prev.baseTurnoverRate,
      regrettableFactor: cfg.turnover?.regrettable_factor || prev.regrettableFactor,
      involuntaryRate: cfg.turnover?.involuntary_rate_percent || prev.involuntaryRate,
      turnoverBands: cfg.turnover?.tenure_bands || prev.turnoverBands,

      // DC Plan
      dcEligibilityMonths: cfg.dc_plan?.eligibility_months || prev.dcEligibilityMonths,
      dcAutoEnroll: cfg.dc_plan?.auto_enroll ?? prev.dcAutoEnroll,
      dcDefaultDeferral: cfg.dc_plan?.default_deferral_percent || prev.dcDefaultDeferral,
      dcMatchFormula: cfg.dc_plan?.match_formula || prev.dcMatchFormula,
      dcMatchPercent: cfg.dc_plan?.match_percent || prev.dcMatchPercent,
      dcMatchLimit: cfg.dc_plan?.match_limit_percent || prev.dcMatchLimit,
      dcVestingSchedule: cfg.dc_plan?.vesting_schedule || prev.dcVestingSchedule,
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

  // Initialize savedFormData when form is loaded (marks current state as "saved")
  useEffect(() => {
    // Only set savedFormData once we have loaded data and it hasn't been set yet
    if (savedFormData === null && (activeWorkspace?.base_config || currentScenario?.config_overrides)) {
      setSavedFormData({ ...formData });
    }
  }, [formData, activeWorkspace?.base_config, currentScenario?.config_overrides, savedFormData]);

  // Compute isDirty by comparing current formData with savedFormData
  const isDirty = useMemo(() => {
    if (!savedFormData) return false;
    return JSON.stringify(formData) !== JSON.stringify(savedFormData);
  }, [formData, savedFormData]);

  // Compute which sections have unsaved changes (for dirty indicators on tabs)
  const dirtySections = useMemo(() => {
    if (!savedFormData) return new Set<string>();

    const dirty = new Set<string>();

    // Simulation section fields
    if (formData.name !== savedFormData.name ||
        formData.startYear !== savedFormData.startYear ||
        formData.endYear !== savedFormData.endYear ||
        formData.seed !== savedFormData.seed ||
        formData.targetGrowthRate !== savedFormData.targetGrowthRate) {
      dirty.add('simulation');
    }

    // Data sources section
    if (formData.censusDataPath !== savedFormData.censusDataPath) {
      dirty.add('datasources');
    }

    // Compensation section
    if (formData.meritBudget !== savedFormData.meritBudget ||
        formData.colaRate !== savedFormData.colaRate ||
        formData.promoIncrease !== savedFormData.promoIncrease ||
        formData.promoDistributionRange !== savedFormData.promoDistributionRange ||
        formData.promoBudget !== savedFormData.promoBudget ||
        formData.promoRateMultiplier !== savedFormData.promoRateMultiplier) {
      dirty.add('compensation');
    }

    // New hire section
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

    // Turnover section
    if (formData.totalTerminationRate !== savedFormData.totalTerminationRate ||
        formData.newHireTerminationRate !== savedFormData.newHireTerminationRate ||
        formData.baseTurnoverRate !== savedFormData.baseTurnoverRate ||
        formData.regrettableFactor !== savedFormData.regrettableFactor ||
        formData.involuntaryRate !== savedFormData.involuntaryRate ||
        JSON.stringify(formData.turnoverBands) !== JSON.stringify(savedFormData.turnoverBands)) {
      dirty.add('turnover');
    }

    // DC Plan section
    if (formData.dcEligibilityMonths !== savedFormData.dcEligibilityMonths ||
        formData.dcAutoEnroll !== savedFormData.dcAutoEnroll ||
        formData.dcDefaultDeferral !== savedFormData.dcDefaultDeferral ||
        formData.dcMatchFormula !== savedFormData.dcMatchFormula ||
        formData.dcMatchPercent !== savedFormData.dcMatchPercent ||
        formData.dcMatchLimit !== savedFormData.dcMatchLimit ||
        formData.dcVestingSchedule !== savedFormData.dcVestingSchedule ||
        formData.dcAutoEscalation !== savedFormData.dcAutoEscalation ||
        formData.dcEscalationRate !== savedFormData.dcEscalationRate ||
        formData.dcEscalationCap !== savedFormData.dcEscalationCap) {
      dirty.add('dcplan');
    }

    // Advanced section
    if (formData.engine !== savedFormData.engine ||
        formData.enableMultithreading !== savedFormData.enableMultithreading ||
        formData.checkpointFrequency !== savedFormData.checkpointFrequency ||
        formData.memoryLimitGB !== savedFormData.memoryLimitGB ||
        formData.logLevel !== savedFormData.logLevel ||
        formData.strictValidation !== savedFormData.strictValidation) {
      dirty.add('advanced');
    }

    return dirty;
  }, [formData, savedFormData]);

  // Warn user when leaving page with unsaved changes (browser refresh/close)
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = ''; // Chrome requires returnValue to be set
        return '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  // Check if we're in a data router context (for conditional NavigationBlocker rendering)
  const dataRouterContext = useContext(UNSAFE_DataRouterContext);

  // Handle save configuration
  const handleSaveConfig = async () => {
    setSaveStatus('saving');
    setSaveMessage('Saving configuration...');

    try {
      // Convert formData to the API config format
      // Ensure numeric values are actual numbers, not strings
      const configPayload = {
        simulation: {
          name: formData.name,
          start_year: Number(formData.startYear),
          end_year: Number(formData.endYear),
          random_seed: Number(formData.seed),
          target_growth_rate: Number(formData.targetGrowthRate) / 100, // Convert % to decimal
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
          // E082: New Hire Demographics
          age_distribution: formData.newHireAgeDistribution.map(row => ({
            age: row.age,
            weight: row.weight,
          })),
          level_distribution_mode: formData.levelDistributionMode,
          level_distribution: formData.newHireLevelDistribution.map(row => ({
            level: row.level,
            percentage: row.percentage / 100, // Convert to decimal
          })),
          // E082: Job Level Compensation
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
        turnover: {
          base_rate_percent: Number(formData.baseTurnoverRate),
          regrettable_factor: Number(formData.regrettableFactor),
          involuntary_rate_percent: Number(formData.involuntaryRate),
          tenure_bands: formData.turnoverBands,
        },
        dc_plan: {
          eligibility_months: Number(formData.dcEligibilityMonths),
          auto_enroll: Boolean(formData.dcAutoEnroll),
          default_deferral_percent: Number(formData.dcDefaultDeferral),
          match_formula: formData.dcMatchFormula,
          match_percent: Number(formData.dcMatchPercent),
          match_limit_percent: Number(formData.dcMatchLimit),
          vesting_schedule: formData.dcVestingSchedule,
          auto_escalation: Boolean(formData.dcAutoEscalation),
          escalation_rate_percent: Number(formData.dcEscalationRate),
          escalation_cap_percent: Number(formData.dcEscalationCap),
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

      // Save to scenario or workspace depending on context
      if (currentScenario && scenarioId) {
        // Save to scenario's config_overrides
        await updateScenario(activeWorkspace.id, scenarioId, {
          config_overrides: configPayload,
        });
        console.log('Config saved to scenario:', scenarioId, configPayload);
      } else {
        // Save to workspace base_config
        await apiUpdateWorkspace(activeWorkspace.id, {
          base_config: configPayload,
        });
        console.log('Config saved to workspace:', activeWorkspace.id, configPayload);
      }

      setSaveStatus('success');
      setSaveMessage('Configuration saved successfully!');

      // Update savedFormData to reflect the new saved state (clears dirty indicators)
      setSavedFormData({ ...formData });

      // Reset status after 3 seconds
      setTimeout(() => {
        setSaveStatus('idle');
        setSaveMessage('');
      }, 3000);
    } catch (error) {
      setSaveStatus('error');
      setSaveMessage(error instanceof Error ? error.message : 'Failed to save configuration');
    }
  };

  // Helper function to create InputField props from formData
  const inputProps = (name: string) => ({
    name,
    value: (formData as any)[name],
    onChange: handleChange,
  });

  // Show loading state while fetching scenario
  if (scenarioLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
          <p className="text-sm text-gray-500">Loading scenario...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center space-x-3">
            {currentScenario && (
              <button
                onClick={() => navigate('/scenarios')}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                title="Back to Scenarios"
              >
                <ArrowLeft size={20} />
              </button>
            )}
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {currentScenario ? `Configure: ${currentScenario.name}` : 'Base Configuration'}
              </h1>
              <p className="text-gray-500 text-sm">
                {currentScenario
                  ? 'Edit scenario-specific configuration overrides.'
                  : 'Edit workspace default simulation parameters.'}
              </p>
            </div>
          </div>
        </div>
        <div className="flex space-x-3">
           <button
             onClick={async () => {
               setTemplatesLoading(true);
               try {
                 const response = await listTemplates();
                 setTemplates(response.templates);
                 setShowTemplateModal(true);
               } catch (error) {
                 console.error('Failed to load templates:', error);
               } finally {
                 setTemplatesLoading(false);
               }
             }}
             disabled={templatesLoading}
             className="px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 flex items-center font-medium shadow-sm transition-colors"
           >
             {templatesLoading ? (
               <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-700 mr-2" />
             ) : (
               <FileText size={18} className="mr-2" />
             )}
             Load Template
           </button>
           <button
             onClick={handleSaveConfig}
             disabled={saveStatus === 'saving'}
             className={`px-4 py-2 text-white rounded-lg flex items-center font-medium shadow-sm transition-colors ${
               saveStatus === 'saving'
                 ? 'bg-gray-400 cursor-not-allowed'
                 : saveStatus === 'success'
                 ? 'bg-green-600 hover:bg-green-700'
                 : isDirty
                 ? 'bg-amber-600 hover:bg-amber-700 ring-2 ring-amber-300'
                 : 'bg-fidelity-green hover:bg-fidelity-dark'
             }`}
           >
             {saveStatus === 'saving' ? (
               <>
                 <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                 Saving...
               </>
             ) : saveStatus === 'success' ? (
               <>
                 <Check size={18} className="mr-2" />
                 Saved!
               </>
             ) : isDirty ? (
               <>
                 <Save size={18} className="mr-2" />
                 Save Changes
               </>
             ) : (
               <>
                 <Save size={18} className="mr-2" />
                 Save Config
               </>
             )}
           </button>
           <button
             onClick={() => navigate(`/simulate?scenario=${scenarioId}`)}
             className={`px-4 py-2 rounded-lg flex items-center font-medium shadow-sm transition-all ${
               saveStatus === 'success'
                 ? 'bg-blue-600 hover:bg-blue-700 text-white animate-pulse'
                 : 'bg-blue-100 hover:bg-blue-200 text-blue-700 border border-blue-300'
             }`}
           >
             <Play size={18} className="mr-2" />
             Run Simulation
           </button>
        </div>
      </div>

      <div className="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-64 bg-gray-50 border-r border-gray-200 p-4 flex-shrink-0 overflow-y-auto">
          <nav className="space-y-1">
             {[
               { id: 'simulation', label: 'Simulation Settings', icon: TrendingUp },
               { id: 'datasources', label: 'Data Sources', icon: Database },
               { id: 'compensation', label: 'Compensation', icon: DollarSign },
               { id: 'newhire', label: 'New Hire Strategy', icon: Users },
               { id: 'turnover', label: 'Workforce & Turnover', icon: AlertTriangle },
               { id: 'dcplan', label: 'DC Plan', icon: PieChart },
               { id: 'advanced', label: 'Advanced Settings', icon: Settings }
             ].map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={`w-full text-left px-3 py-3 rounded-md text-sm font-medium transition-colors flex items-center justify-between ${
                    activeSection === item.id
                      ? 'bg-white text-fidelity-green shadow-sm border border-gray-200'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  <span className="flex items-center">
                    <item.icon size={16} className={`mr-3 ${activeSection === item.id ? 'text-fidelity-green' : 'text-gray-400'}`} />
                    {item.label}
                  </span>
                  {dirtySections.has(item.id) && (
                    <span className="w-2 h-2 bg-amber-500 rounded-full" title="Unsaved changes" />
                  )}
                </button>
             ))}
          </nav>

          <div className="mt-8 p-4 bg-blue-50 rounded-lg border border-blue-100">
            <h4 className="text-xs font-semibold text-blue-800 uppercase tracking-wider mb-2">Impact Preview</h4>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs text-blue-600 mb-1">
                   <span>Projected Headcount</span>
                   <span className="font-bold">1,061</span>
                </div>
                <div className="w-full bg-blue-200 rounded-full h-1.5">
                  <div className="bg-blue-600 h-1.5 rounded-full" style={{ width: '70%' }}></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs text-blue-600 mb-1">
                   <span>Turnover Cost</span>
                   <span className="font-bold">$2.4M</span>
                </div>
                <div className="w-full bg-blue-200 rounded-full h-1.5">
                   <div className="bg-red-400 h-1.5 rounded-full" style={{ width: '40%' }}></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Form Area */}
        <div className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-3xl">

            {/* --- DATA SOURCES --- */}
            {activeSection === 'datasources' && (
              <div className="space-y-8 animate-fadeIn">
                <div className="border-b border-gray-100 pb-4">
                  <h2 className="text-lg font-bold text-gray-900">Data Sources</h2>
                  <p className="text-sm text-gray-500">Configure your workforce census data and other input files.</p>
                </div>

                {/* Census Data Section */}
                <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center">
                      <Database className="w-5 h-5 text-fidelity-green mr-3" />
                      <h3 className="font-semibold text-gray-900">Census Data (Parquet)</h3>
                    </div>
                    {formData.censusDataStatus === 'loaded' && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        <Check size={12} className="mr-1" />
                        Loaded
                      </span>
                    )}
                  </div>

                  {/* Current File Info */}
                  {formData.censusDataStatus === 'loaded' && (
                    <div className="bg-white rounded-lg p-4 border border-gray-200 mb-4">
                      <div className="grid grid-cols-3 gap-4 text-sm">
                        <div>
                          <span className="text-gray-500 block">File Path</span>
                          <span className="font-mono text-gray-900 text-xs">{formData.censusDataPath}</span>
                        </div>
                        <div>
                          <span className="text-gray-500 block">Rows</span>
                          <span className="font-semibold text-gray-900">{formData.censusRowCount.toLocaleString()}</span>
                        </div>
                        <div>
                          <span className="text-gray-500 block">Last Modified</span>
                          <span className="text-gray-900">{formData.censusLastModified}</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Upload Section */}
                  <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-fidelity-green transition-colors">
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept=".parquet,.csv"
                      className="hidden"
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file || !activeWorkspace?.id) return;

                        setUploadStatus('uploading');
                        setUploadMessage(`Uploading ${file.name}...`);

                        try {
                          const result = await uploadCensusFile(activeWorkspace.id, file);

                          setFormData(prev => ({
                            ...prev,
                            censusDataPath: result.file_path,
                            censusDataStatus: 'loaded',
                            censusRowCount: result.row_count,
                            censusLastModified: result.upload_timestamp.split('T')[0]
                          }));

                          if (result.validation_warnings.length > 0) {
                            setUploadStatus('success');
                            setUploadMessage(`Uploaded with warnings: ${result.validation_warnings.join(', ')}`);
                          } else {
                            setUploadStatus('success');
                            setUploadMessage(`File uploaded successfully! ${result.row_count.toLocaleString()} rows, ${result.columns.length} columns`);
                          }
                        } catch (error) {
                          setUploadStatus('error');
                          setUploadMessage(error instanceof Error ? error.message : 'Upload failed');
                        }
                      }}
                    />
                    <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
                    <p className="text-sm text-gray-600 mb-2">
                      Drag and drop your census file here, or{' '}
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="text-fidelity-green font-medium hover:underline"
                      >
                        browse
                      </button>
                    </p>
                    <p className="text-xs text-gray-400">Supports Parquet (.parquet) or CSV (.csv) files</p>

                    {uploadStatus === 'uploading' && (
                      <div className="mt-4 flex items-center justify-center text-sm text-gray-600">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-fidelity-green mr-2"></div>
                        {uploadMessage}
                      </div>
                    )}
                    {uploadStatus === 'success' && (
                      <div className="mt-4 flex items-center justify-center text-sm text-green-600">
                        <Check size={16} className="mr-2" />
                        {uploadMessage}
                      </div>
                    )}
                  </div>

                  {/* Manual Path Input */}
                  <div className="mt-4">
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Or specify file path manually
                    </label>
                    <div className="flex space-x-2">
                      <input
                        type="text"
                        name="censusDataPath"
                        value={formData.censusDataPath}
                        onChange={handleChange}
                        placeholder="data/census_preprocessed.parquet"
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green font-mono"
                      />
                      <button
                        type="button"
                        className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors"
                        onClick={async () => {
                          if (!formData.censusDataPath.trim() || !activeWorkspace?.id) {
                            setUploadStatus('error');
                            setUploadMessage('Please enter a file path');
                            return;
                          }

                          setUploadStatus('uploading');
                          setUploadMessage('Validating path...');

                          try {
                            const result = await validateFilePath(
                              activeWorkspace.id,
                              formData.censusDataPath
                            );

                            if (result.valid) {
                              setFormData(prev => ({
                                ...prev,
                                censusDataStatus: 'loaded',
                                censusRowCount: result.row_count || 0,
                                censusLastModified: result.last_modified?.split('T')[0] || 'Unknown'
                              }));
                              setUploadStatus('success');
                              setUploadMessage(`Valid: ${result.row_count?.toLocaleString()} rows, ${result.columns?.length} columns`);
                            } else {
                              setUploadStatus('error');
                              setUploadMessage(result.error_message || 'Invalid path');
                              setFormData(prev => ({ ...prev, censusDataStatus: 'error' }));
                            }
                          } catch (error) {
                            setUploadStatus('error');
                            setUploadMessage(error instanceof Error ? error.message : 'Validation failed');
                          }
                        }}
                      >
                        Validate
                      </button>
                    </div>
                  </div>
                </div>

                {/* Required Columns Info */}
                <div className="bg-blue-50 rounded-xl p-6 border border-blue-100">
                  <div className="flex items-start">
                    <HelpCircle className="w-5 h-5 text-blue-500 mr-3 mt-0.5" />
                    <div>
                      <h4 className="font-semibold text-blue-900 mb-2">Required Census Columns</h4>
                      <p className="text-sm text-blue-700 mb-3">
                        Your census file must contain the following columns for the simulation to run correctly:
                      </p>
                      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                        {['employee_id', 'hire_date', 'department', 'job_level', 'annual_salary', 'birth_date', 'termination_date', 'status'].map(col => (
                          <div key={col} className="bg-white px-2 py-1 rounded border border-blue-200 text-blue-800">
                            {col}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* --- SIMULATION SETTINGS --- */}
            {activeSection === 'simulation' && (
              <div className="space-y-8 animate-fadeIn">
                <div className="border-b border-gray-100 pb-4">
                  <h2 className="text-lg font-bold text-gray-900">Simulation Parameters</h2>
                  <p className="text-sm text-gray-500">Define the temporal scope and reproducibility settings.</p>
                </div>

                <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
                  <div className="col-span-6 grid grid-cols-2 gap-4">
                    <InputField label="Start Year" {...inputProps('startYear')} type="number" width="col-span-1" />
                    <InputField label="End Year" {...inputProps('endYear')} type="number" width="col-span-1" />
                  </div>

                  <InputField
                    label="Random Seed"
                    {...inputProps('seed')}
                    type="number"
                    helper="Fixed seed (e.g., 42) ensures identical runs."
                  />

                  <InputField
                    label="Target Growth Rate"
                    {...inputProps('targetGrowthRate')}
                    type="number"
                    step="0.1"
                    suffix="%"
                    helper="Target annual workforce growth (e.g., 3% = 0.03)"
                  />

                  <div className="sm:col-span-6 pt-4">
                     <div className="rounded-md bg-yellow-50 p-4 border border-yellow-100">
                      <div className="flex">
                        <AlertTriangle className="h-5 w-5 text-yellow-400" />
                        <div className="ml-3">
                          <h3 className="text-sm font-medium text-yellow-800">Validation Note</h3>
                          <div className="mt-1 text-sm text-yellow-700">
                            <p>End year must be greater than Start year. Large gaps ({'>'} 10 years) may significantly increase processing time.</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* --- COMPENSATION --- */}
            {activeSection === 'compensation' && (
               <div className="space-y-8 animate-fadeIn">
                 <div className="border-b border-gray-100 pb-4">
                   <h2 className="text-lg font-bold text-gray-900">Compensation Strategy</h2>
                   <p className="text-sm text-gray-500">Set annual increase budgets and promotion guidelines.</p>
                 </div>

                 {/* Target Growth Solver - Magic Button */}
                 <div className="bg-gradient-to-r from-purple-50 to-indigo-50 p-5 rounded-xl border border-purple-200 shadow-sm">
                   <div className="flex items-start gap-4">
                     <div className="flex-shrink-0 bg-purple-100 rounded-lg p-2.5">
                       <Target className="h-6 w-6 text-purple-600" />
                     </div>
                     <div className="flex-1">
                       <h3 className="text-sm font-semibold text-purple-900">Target Compensation Growth</h3>
                       <p className="text-xs text-purple-700 mt-0.5">
                         Enter your target average compensation growth rate and we'll calculate the COLA, merit, and promotion settings needed.
                       </p>
                       <div className="mt-3 flex items-end gap-3">
                         <div className="flex-shrink-0 w-32">
                           <label className="block text-xs font-medium text-purple-800 mb-1">Target Growth</label>
                           <div className="relative">
                             <input
                               type="number"
                               value={targetCompGrowth}
                               onChange={(e) => setTargetCompGrowth(parseFloat(e.target.value) || 0)}
                               step="0.5"
                               min="0"
                               max="20"
                               className="w-full px-3 py-2 text-sm border border-purple-300 rounded-md focus:ring-purple-500 focus:border-purple-500 bg-white"
                             />
                             <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                               <span className="text-purple-500 text-sm">%</span>
                             </div>
                           </div>
                         </div>
                         <button
                           onClick={handleSolveCompensation}
                           disabled={solverStatus === 'solving'}
                           className={`
                             flex items-center gap-2 px-4 py-2 rounded-md font-medium text-sm transition-all
                             ${solverStatus === 'solving'
                               ? 'bg-purple-200 text-purple-400 cursor-wait'
                               : 'bg-purple-600 text-white hover:bg-purple-700 shadow-sm hover:shadow'
                             }
                           `}
                         >
                           <Sparkles className="h-4 w-4" />
                           {solverStatus === 'solving' ? 'Calculating...' : 'Calculate Settings'}
                         </button>
                       </div>

                       {/* Solver Results */}
                       {solverStatus === 'success' && solverResult && (
                         <div className="mt-4 p-3 bg-white rounded-lg border border-purple-200">
                           <div className="flex items-center gap-2 mb-2">
                             <Check className="h-4 w-4 text-green-600" />
                             <span className="text-sm font-medium text-green-800">Settings Applied!</span>
                           </div>
                           <div className="grid grid-cols-4 gap-3 text-center">
                             <div>
                               <div className="text-lg font-bold text-purple-900">{solverResult.cola_rate.toFixed(1)}%</div>
                               <div className="text-xs text-gray-500">COLA</div>
                             </div>
                             <div>
                               <div className="text-lg font-bold text-purple-900">{solverResult.merit_budget.toFixed(1)}%</div>
                               <div className="text-xs text-gray-500">Merit</div>
                             </div>
                             <div>
                               <div className="text-lg font-bold text-purple-900">{solverResult.promotion_increase.toFixed(1)}%</div>
                               <div className="text-xs text-gray-500">Promo Inc.</div>
                             </div>
                             <div>
                               <div className="text-lg font-bold text-purple-900">{solverResult.promotion_budget.toFixed(1)}%</div>
                               <div className="text-xs text-gray-500">Promo Budget</div>
                             </div>
                           </div>
                           <div className="mt-2 pt-2 border-t border-purple-100">
                             <p className="text-xs text-gray-600">
                               <span className="font-medium">Stayer raises:</span>{' '}
                               COLA {solverResult.cola_contribution.toFixed(1)}% +
                               Merit {solverResult.merit_contribution.toFixed(1)}% +
                               Promotions {solverResult.promo_contribution.toFixed(1)}%
                             </p>
                             <p className="text-xs text-gray-600 mt-1">
                               <span className="font-medium">Workforce dynamics:</span>{' '}
                               <span className={solverResult.turnover_contribution < 0 ? 'text-red-600' : 'text-green-600'}>
                                 {solverResult.turnover_contribution >= 0 ? '+' : ''}{solverResult.turnover_contribution.toFixed(1)}%
                               </span>
                               <span className="text-gray-400 ml-1">
                                 (turnover {solverResult.turnover_rate.toFixed(0)}%, growth {solverResult.workforce_growth_rate.toFixed(0)}%, new hires @ {solverResult.new_hire_comp_ratio.toFixed(0)}% avg)
                               </span>
                             </p>
                             <p className="text-xs mt-1">
                               <span className="font-medium">Net avg comp growth:</span>
                               <span className="font-semibold text-purple-700"> {solverResult.achieved_growth_rate.toFixed(1)}%</span>
                             </p>
                           </div>
                           {/* Recommendation for new hire compensation */}
                           {solverResult.recommended_scale_factor > 1.05 && (
                             <div className="mt-2 pt-2 border-t border-purple-100 bg-blue-50 -mx-3 px-3 py-2 rounded">
                               <p className="text-xs text-blue-800">
                                 <span className="font-semibold">Recommendation:</span> With standard raises (~5%), hire at{' '}
                                 <span className="font-bold">{solverResult.recommended_new_hire_ratio.toFixed(0)}%</span> of avg comp.
                                 Use <span className="font-bold">{solverResult.recommended_scale_factor.toFixed(1)}x</span> scale in Job Level Compensation Ranges.
                               </p>
                             </div>
                           )}
                           {solverResult.warnings.length > 0 && (
                             <div className="mt-2 pt-2 border-t border-purple-100">
                               {solverResult.warnings.map((warning, idx) => (
                                 <p key={idx} className="text-xs text-amber-600 flex items-start gap-1">
                                   <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                                   {warning}
                                 </p>
                               ))}
                             </div>
                           )}
                         </div>
                       )}

                       {solverStatus === 'error' && (
                         <div className="mt-3 p-2 bg-red-50 rounded border border-red-200">
                           <p className="text-xs text-red-700 flex items-center gap-1">
                             <X className="h-3 w-3" />
                             {solverError}
                           </p>
                         </div>
                       )}
                     </div>
                   </div>
                 </div>

                 <div className="space-y-6">
                    <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">Annual Review</h3>
                    <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
                      <InputField label="Merit Budget" {...inputProps('meritBudget')} type="number" step="0.1" suffix="%" helper="Avg. annual performance increase" />
                      <InputField label="COLA / Inflation" {...inputProps('colaRate')} type="number" step="0.1" suffix="%" helper="Cost of living adjustment" />
                    </div>

                    <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider pt-4">Promotions</h3>
                    <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
                      <InputField label="Avg. Promotion Increase" {...inputProps('promoIncrease')} type="number" step="0.5" suffix="%" helper="Base pay bump on promotion" />

                      <div className="sm:col-span-3">
                        <label className="block text-sm font-medium text-gray-700">Distribution Range</label>
                        <div className="mt-1 relative rounded-md shadow-sm">
                           <input
                             type="number"
                             step="0.5"
                             name="promoDistributionRange"
                             value={formData.promoDistributionRange}
                             onChange={handleChange}
                             className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                           />
                           <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                              <span className="text-gray-500 sm:text-sm">± %</span>
                           </div>
                        </div>
                        <p className="mt-1 text-xs text-gray-500">
                          Increases vary by ±{formData.promoDistributionRange}% (Range: {formData.promoIncrease - formData.promoDistributionRange}% - {formData.promoIncrease + formData.promoDistributionRange}%)
                        </p>
                      </div>

                      <div className="col-span-6 h-px bg-gray-200 my-1"></div>

                      <InputField label="Promotion Budget" {...inputProps('promoBudget')} type="number" step="0.1" suffix="% of payroll" helper="Budget allocated for level-ups" />

                      <div className="col-span-6 h-px bg-gray-200 my-1"></div>

                      <div className="col-span-6 sm:col-span-3">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Promotion Rate Multiplier
                        </label>
                        <div className="relative rounded-md shadow-sm">
                          <input
                            type="number"
                            step="0.1"
                            min="0"
                            max="5"
                            name="promoRateMultiplier"
                            value={formData.promoRateMultiplier}
                            onChange={handleChange}
                            className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2 border"
                          />
                          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                            <span className="text-gray-500 sm:text-sm">×</span>
                          </div>
                        </div>
                        <p className="mt-1 text-xs text-gray-500">
                          Multiplier applied to seed promotion rates (1.0 = use defaults, 1.5 = 50% more promotions)
                        </p>
                      </div>
                    </div>
                 </div>
               </div>
            )}

            {/* --- NEW HIRE STRATEGY --- */}
            {activeSection === 'newhire' && (
               <div className="space-y-8 animate-fadeIn">
                  <div className="border-b border-gray-100 pb-4">
                   <h2 className="text-lg font-bold text-gray-900">New Hire Compensation</h2>
                   <p className="text-sm text-gray-500">Define how offers are constructed for external candidates.</p>
                 </div>

                 <div className="space-y-4">
                    <div className="flex items-center space-x-4 mb-6">
                      <label className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors w-1/2 ${formData.newHireStrategy === 'percentile' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
                        <input
                          type="radio"
                          name="newHireStrategy"
                          value="percentile"
                          checked={formData.newHireStrategy === 'percentile'}
                          onChange={handleChange}
                          className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300"
                        />
                        <div className="ml-3">
                          <span className="block text-sm font-medium text-gray-900">Percentile Based</span>
                          <span className="block text-xs text-gray-500">Offers target market percentiles (e.g., P50)</span>
                        </div>
                      </label>
                      <label className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors w-1/2 ${formData.newHireStrategy === 'fixed' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
                        <input
                          type="radio"
                          name="newHireStrategy"
                          value="fixed"
                          checked={formData.newHireStrategy === 'fixed'}
                          onChange={handleChange}
                          className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300"
                        />
                         <div className="ml-3">
                          <span className="block text-sm font-medium text-gray-900">Fixed Bands</span>
                          <span className="block text-xs text-gray-500">Offers use rigid salary structures</span>
                        </div>
                      </label>
                    </div>

                    {formData.newHireStrategy === 'percentile' && (
                      <div className="bg-blue-50 p-6 rounded-lg border border-blue-100 space-y-4">
                        <div>
                          <label className="block text-sm font-medium text-blue-900 mb-2">Target Market Percentile</label>
                          <div className="flex items-center">
                            <input
                              type="range"
                              min="0"
                              max="100"
                              value={formData.targetPercentile}
                              onChange={(e) => setFormData({...formData, targetPercentile: parseInt(e.target.value)})}
                              className="w-full h-2 bg-blue-200 rounded-lg appearance-none cursor-pointer"
                            />
                            <span className="ml-4 font-bold text-blue-700 w-12">P{formData.targetPercentile}</span>
                          </div>
                          <p className="text-xs text-blue-600 mt-2">New hires will be offered salaries at the {formData.targetPercentile}th percentile.</p>
                        </div>

                        <div className="grid grid-cols-2 gap-4 pt-2">
                           <div>
                              <label className="block text-sm font-medium text-blue-900 mb-1">Offer Variance</label>
                              <div className="relative rounded-md shadow-sm">
                                 <input
                                   type="number"
                                   step="0.5"
                                   value={formData.newHireCompVariance}
                                   onChange={(e) => setFormData({...formData, newHireCompVariance: parseFloat(e.target.value)})}
                                   className="focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-blue-300 rounded-md p-2"
                                 />
                                 <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                                    <span className="text-blue-500 sm:text-sm">± %</span>
                                 </div>
                              </div>
                           </div>
                        </div>
                      </div>
                    )}

                    {/* E082: Age Distribution Section */}
                    <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-sm font-semibold text-gray-900">New Hire Age Profile</h3>
                        <button
                          type="button"
                          onClick={handleMatchCensus}
                          disabled={matchCensusLoading || !formData.censusDataPath || formData.censusDataStatus !== 'loaded'}
                          className={`inline-flex items-center px-3 py-1.5 border rounded-md text-xs font-medium transition-colors ${
                            matchCensusSuccess
                              ? 'bg-green-100 border-green-300 text-green-800'
                              : (formData.censusDataPath && formData.censusDataStatus === 'loaded')
                                ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                                : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                          }`}
                          title={formData.censusDataStatus !== 'loaded' ? 'Load a census file first' : 'Analyze census to match current workforce age distribution'}
                        >
                          {matchCensusLoading ? (
                            <>
                              <svg className="animate-spin -ml-0.5 mr-1.5 h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                              Analyzing...
                            </>
                          ) : matchCensusSuccess ? (
                            <>
                              <Check className="h-3 w-3 mr-1" />
                              Matched!
                            </>
                          ) : (
                            <>
                              <PieChart className="h-3 w-3 mr-1" />
                              Match Census
                            </>
                          )}
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mb-4">
                        Define the age distribution for new hires. Weights should sum to 100%.
                        {formData.censusDataStatus === 'loaded' && (
                          <span className="text-blue-600 ml-1">
                            Click "Match Census" to auto-fill based on your workforce.
                          </span>
                        )}
                      </p>
                      {matchCensusError && (
                        <div className="mb-4 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                          {matchCensusError}
                        </div>
                      )}
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-100">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Age</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Weight (%)</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {formData.newHireAgeDistribution.map((row, idx) => (
                              <tr key={row.age}>
                                <td className="px-4 py-2 text-sm text-gray-900 font-medium">{row.age}</td>
                                <td className="px-4 py-2">
                                  <input
                                    type="number"
                                    step="1"
                                    min="0"
                                    max="100"
                                    value={Math.round(row.weight * 100)}
                                    onChange={(e) => handleAgeWeightChange(idx, e.target.value)}
                                    className="w-20 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-right"
                                  />
                                </td>
                                <td className="px-4 py-2 text-sm text-gray-500">{row.description}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot className="bg-gray-50">
                            <tr>
                              <td className="px-4 py-2 text-sm font-semibold text-gray-900">Total</td>
                              <td className="px-4 py-2 text-sm font-semibold">
                                <span className={`${Math.abs(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) - 1) > 0.01 ? 'text-red-600' : 'text-green-600'}`}>
                                  {Math.round(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) * 100)}%
                                </span>
                              </td>
                              <td className="px-4 py-2 text-xs text-gray-500">
                                {Math.abs(formData.newHireAgeDistribution.reduce((sum, r) => sum + r.weight, 0) - 1) > 0.01 && (
                                  <span className="text-red-600">Weights should sum to 100%</span>
                                )}
                              </td>
                            </tr>
                          </tfoot>
                        </table>
                      </div>
                    </div>

                    {/* E082: Level Distribution Section */}
                    <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
                      <h3 className="text-sm font-semibold text-gray-900 mb-2">New Hire Level Distribution</h3>
                      <p className="text-xs text-gray-500 mb-4">
                        Choose how new hires are distributed across job levels.
                      </p>

                      <div className="flex items-center space-x-4 mb-4">
                        <label className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${formData.levelDistributionMode === 'adaptive' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
                          <input
                            type="radio"
                            name="levelDistributionMode"
                            value="adaptive"
                            checked={formData.levelDistributionMode === 'adaptive'}
                            onChange={(e) => setFormData({...formData, levelDistributionMode: e.target.value as 'adaptive' | 'fixed'})}
                            className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300"
                          />
                          <div className="ml-2">
                            <span className="block text-sm font-medium text-gray-900">Adaptive</span>
                            <span className="block text-xs text-gray-500">Maintain current workforce composition</span>
                          </div>
                        </label>
                        <label className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${formData.levelDistributionMode === 'fixed' ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
                          <input
                            type="radio"
                            name="levelDistributionMode"
                            value="fixed"
                            checked={formData.levelDistributionMode === 'fixed'}
                            onChange={(e) => setFormData({...formData, levelDistributionMode: e.target.value as 'adaptive' | 'fixed'})}
                            className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300"
                          />
                          <div className="ml-2">
                            <span className="block text-sm font-medium text-gray-900">Fixed Percentages</span>
                            <span className="block text-xs text-gray-500">Specify exact distribution below</span>
                          </div>
                        </label>
                      </div>

                      {formData.levelDistributionMode === 'fixed' && (
                        <div className="overflow-x-auto">
                          <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-100">
                              <tr>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Level</th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Percentage (%)</th>
                              </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                              {formData.newHireLevelDistribution.map((row, idx) => (
                                <tr key={row.level}>
                                  <td className="px-4 py-2 text-sm text-gray-900 font-medium">{row.level}</td>
                                  <td className="px-4 py-2 text-sm text-gray-700">{row.name}</td>
                                  <td className="px-4 py-2">
                                    <input
                                      type="number"
                                      step="1"
                                      min="0"
                                      max="100"
                                      value={row.percentage}
                                      onChange={(e) => handleLevelPercentageChange(idx, e.target.value)}
                                      className="w-20 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-right"
                                    />
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                            <tfoot className="bg-gray-50">
                              <tr>
                                <td className="px-4 py-2 text-sm font-semibold text-gray-900" colSpan={2}>Total</td>
                                <td className="px-4 py-2 text-sm font-semibold">
                                  <span className={`${Math.abs(formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0) - 100) > 1 ? 'text-red-600' : 'text-green-600'}`}>
                                    {formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0)}%
                                  </span>
                                  {Math.abs(formData.newHireLevelDistribution.reduce((sum, r) => sum + r.percentage, 0) - 100) > 1 && (
                                    <span className="text-red-600 text-xs ml-2">Should sum to 100%</span>
                                  )}
                                </td>
                              </tr>
                            </tfoot>
                          </table>
                        </div>
                      )}

                      {formData.levelDistributionMode === 'adaptive' && (
                        <div className="bg-blue-50 p-4 rounded-lg border border-blue-100">
                          <p className="text-sm text-blue-800">
                            <strong>Adaptive mode:</strong> New hires will be distributed across levels proportionally to match your current workforce composition. This maintains your existing organizational structure.
                          </p>
                        </div>
                      )}
                    </div>

                    {/* E082: Job Level Compensation Ranges */}
                    <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-sm font-semibold text-gray-900">Job Level Compensation Ranges</h3>
                        <div className="flex items-center gap-2">
                          {/* Lookback years selector */}
                          <div className="flex items-center gap-1">
                            <label className="text-xs text-gray-500">Source:</label>
                            <select
                              value={compLookbackYears}
                              onChange={(e) => setCompLookbackYears(parseInt(e.target.value))}
                              className="text-xs border border-gray-300 rounded px-1.5 py-1 bg-white focus:ring-blue-500 focus:border-blue-500"
                            >
                              <option value={0}>All employees</option>
                              <option value={1}>Last 1 year</option>
                              <option value={2}>Last 2 years</option>
                              <option value={3}>Last 3 years</option>
                              <option value={4}>Last 4 years</option>
                              <option value={5}>Last 5 years</option>
                            </select>
                          </div>
                          {/* Scale factor to adjust for tenured employee comp levels */}
                          <div className="flex items-center gap-1">
                            <label className="text-xs text-gray-500">Scale:</label>
                            <input
                              type="number"
                              value={compScaleFactor}
                              onChange={(e) => {
                                const val = parseFloat(e.target.value);
                                if (!isNaN(val) && val >= 0.5 && val <= 3.0) {
                                  setCompScaleFactor(val);
                                }
                              }}
                              min={0.5}
                              max={3.0}
                              step={0.1}
                              className="text-xs border border-gray-300 rounded px-1.5 py-1 w-16 bg-white focus:ring-blue-500 focus:border-blue-500"
                              title="Scale up ranges to match tenured employee compensation levels (0.5x - 3.0x)"
                            />
                            <span className="text-xs text-gray-400">x</span>
                          </div>
                          <button
                            type="button"
                            onClick={handleMatchCompensation}
                            disabled={matchCompLoading || !formData.censusDataPath || formData.censusDataStatus !== 'loaded'}
                            className={`inline-flex items-center px-3 py-1.5 border rounded-md text-xs font-medium transition-colors ${
                              matchCompSuccess
                                ? 'bg-green-100 border-green-300 text-green-800'
                                : (formData.censusDataPath && formData.censusDataStatus === 'loaded')
                                  ? 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
                                  : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                            }`}
                            title={formData.censusDataStatus !== 'loaded' ? 'Load a census file first' : 'Analyze census to suggest compensation ranges'}
                          >
                            {matchCompLoading ? (
                              <>
                                <svg className="animate-spin -ml-0.5 mr-1.5 h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Analyzing...
                              </>
                            ) : matchCompSuccess ? (
                              <>
                                <Check className="h-3 w-3 mr-1" />
                                Applied!
                              </>
                            ) : (
                              <>
                                <DollarSign className="h-3 w-3 mr-1" />
                                Match Census
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 mb-4">
                        Define min/max compensation for each job level. Used for new hire offers.
                        {formData.censusDataStatus === 'loaded' && (
                          <span className="text-blue-600 ml-1">
                            Select lookback period and click "Match Census" to derive ranges from recent hire data.
                          </span>
                        )}
                      </p>
                      {matchCompError && (
                        <div className="mb-4 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                          {matchCompError}
                        </div>
                      )}
                      {compensationAnalysis && (
                        <div className={`mb-4 p-2 rounded text-xs ${compensationAnalysis.recent_hires_only ? 'bg-blue-50 border border-blue-200 text-blue-700' : 'bg-yellow-50 border border-yellow-200 text-yellow-700'}`}>
                          <strong>Analysis:</strong> {compensationAnalysis.analysis_type} ({compensationAnalysis.total_employees} employees)
                          {compensationAnalysis.message && <div className="mt-1">{compensationAnalysis.message}</div>}
                        </div>
                      )}
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-100">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Level</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Min Compensation ($)</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Max Compensation ($)</th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {formData.jobLevelCompensation.map((row, idx) => (
                              <tr key={row.level}>
                                <td className="px-4 py-2 text-sm text-gray-900 font-medium">{row.level}</td>
                                <td className="px-4 py-2 text-sm text-gray-700">{row.name}</td>
                                <td className="px-4 py-2">
                                  <input
                                    type="number"
                                    step="1000"
                                    min="0"
                                    value={row.minComp}
                                    onChange={(e) => handleJobLevelCompChange(idx, 'minComp', e.target.value)}
                                    className="w-28 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-right"
                                  />
                                </td>
                                <td className="px-4 py-2">
                                  <input
                                    type="number"
                                    step="1000"
                                    min="0"
                                    value={row.maxComp}
                                    onChange={(e) => handleJobLevelCompChange(idx, 'maxComp', e.target.value)}
                                    className="w-28 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-right"
                                  />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* E082: Market Positioning Section */}
                    <div className="bg-gray-50 p-6 rounded-lg border border-gray-200 mt-6">
                      <h3 className="text-sm font-semibold text-gray-900 mb-2">Market Positioning</h3>
                      <p className="text-xs text-gray-500 mb-4">
                        Choose your overall compensation strategy relative to market rates.
                      </p>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                        {(Object.keys(marketMultipliers) as Array<keyof typeof marketMultipliers>).map((scenario) => (
                          <label
                            key={scenario}
                            className={`flex flex-col p-3 border rounded-lg cursor-pointer transition-colors text-center ${
                              formData.marketScenario === scenario
                                ? 'bg-green-50 border-fidelity-green ring-1 ring-fidelity-green'
                                : 'bg-white border-gray-200 hover:bg-gray-50'
                            }`}
                          >
                            <input
                              type="radio"
                              name="marketScenario"
                              value={scenario}
                              checked={formData.marketScenario === scenario}
                              onChange={(e) => setFormData({...formData, marketScenario: e.target.value as any})}
                              className="sr-only"
                            />
                            <span className="font-medium text-sm text-gray-900">{marketMultipliers[scenario].label}</span>
                            <span className={`text-xs mt-1 ${marketMultipliers[scenario].adjustment >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                              {marketMultipliers[scenario].adjustment >= 0 ? '+' : ''}{marketMultipliers[scenario].adjustment}%
                            </span>
                          </label>
                        ))}
                      </div>

                      <div className="bg-blue-50 p-3 rounded-lg border border-blue-100 mb-4">
                        <p className="text-xs text-blue-800">
                          <strong>{marketMultipliers[formData.marketScenario].label}:</strong>{' '}
                          {marketMultipliers[formData.marketScenario].description}
                        </p>
                      </div>

                      {/* Level-specific adjustments */}
                      <div className="mt-4">
                        <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-3">Level-Specific Adjustments</h4>
                        <p className="text-xs text-gray-500 mb-3">
                          Fine-tune market positioning by job level (in addition to overall scenario).
                        </p>
                        <div className="grid grid-cols-5 gap-2">
                          {formData.levelMarketAdjustments.map((row, idx) => (
                            <div key={row.level} className="bg-white p-2 rounded border border-gray-200">
                              <label className="block text-xs text-gray-500 mb-1 text-center">
                                Level {row.level}
                              </label>
                              <div className="relative">
                                <input
                                  type="number"
                                  step="1"
                                  value={row.adjustment}
                                  onChange={(e) => handleLevelAdjustmentChange(idx, e.target.value)}
                                  className="w-full shadow-sm focus:ring-fidelity-green focus:border-fidelity-green text-xs border-gray-300 rounded-md p-1 border text-center"
                                />
                                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs">%</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                 </div>
               </div>
            )}

            {/* --- TURNOVER --- */}
            {activeSection === 'turnover' && (
               <div className="space-y-8 animate-fadeIn">
                 <div className="border-b border-gray-100 pb-4">
                   <h2 className="text-lg font-bold text-gray-900">Workforce & Turnover</h2>
                   <p className="text-sm text-gray-500">Model employee attrition rates and retention risks.</p>
                 </div>

                 {/* Core Workforce Parameters */}
                 <div className="bg-orange-50 rounded-lg p-4 border border-orange-200">
                   <h4 className="text-sm font-semibold text-orange-900 mb-3 uppercase tracking-wider">Core Termination Rates</h4>
                   <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
                     <InputField
                       label="Total Termination Rate"
                       {...inputProps('totalTerminationRate')}
                       type="number"
                       step="0.1"
                       suffix="%"
                       helper="Overall annual termination rate for experienced employees"
                     />
                     <InputField
                       label="New Hire Termination Rate"
                       {...inputProps('newHireTerminationRate')}
                       type="number"
                       step="0.1"
                       suffix="%"
                       helper="First-year termination rate (typically higher than overall)"
                     />
                   </div>
                 </div>

                 <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
                    <InputField label="Base Annual Turnover" {...inputProps('baseTurnoverRate')} type="number" suffix="%" helper="Expected overall exit rate" />
                    <InputField label="Regrettable Factor" {...inputProps('regrettableFactor')} type="number" step="0.1" suffix="x" helper="Portion of exits that are regrettable (0.0-1.0)" />
                    <InputField label="Involuntary Rate" {...inputProps('involuntaryRate')} type="number" suffix="%" helper="Performance-based exits / layoffs" />
                 </div>

                 <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 mt-6">
                   <h4 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wider">Tenure-Based Attrition Risks</h4>
                   <div className="grid grid-cols-3 gap-4">
                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">Year 1 (High Risk)</label>
                        <div className="relative rounded-md shadow-sm">
                          <input
                            type="number"
                            value={formData.turnoverBands.year1}
                            onChange={(e) => handleNestedChange('turnoverBands', 'year1', e.target.value)}
                            className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2"
                          />
                          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                             <span className="text-gray-400 text-xs">%</span>
                          </div>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">Year 2-3 (Medium)</label>
                        <div className="relative rounded-md shadow-sm">
                          <input
                            type="number"
                            value={formData.turnoverBands.year2_3}
                            onChange={(e) => handleNestedChange('turnoverBands', 'year2_3', e.target.value)}
                            className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2"
                          />
                          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                             <span className="text-gray-400 text-xs">%</span>
                          </div>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-500 mb-1">Year 4+ (Stable)</label>
                        <div className="relative rounded-md shadow-sm">
                          <input
                            type="number"
                            value={formData.turnoverBands.year4_plus}
                            onChange={(e) => handleNestedChange('turnoverBands', 'year4_plus', e.target.value)}
                            className="shadow-sm focus:ring-fidelity-green focus:border-fidelity-green block w-full sm:text-sm border-gray-300 rounded-md p-2"
                          />
                          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                             <span className="text-gray-400 text-xs">%</span>
                          </div>
                        </div>
                      </div>
                   </div>
                   <p className="text-xs text-gray-500 mt-3">
                     Configures specific hazard rates for employees at different tenure stages.
                   </p>
                 </div>

                 <div className="bg-blue-50 rounded-lg p-4 border border-blue-100">
                   <h4 className="text-sm font-medium text-blue-900 mb-2 flex items-center">
                     <HelpCircle size={16} className="mr-2 text-blue-500"/> Calculated Projection
                   </h4>
                   <p className="text-sm text-blue-800">
                     Based on these inputs, an organization of 1,000 employees will see approximately <span className="font-bold">{Math.round(1000 * (formData.baseTurnoverRate / 100))}</span> exits per year, of which <span className="font-bold">{Math.round(1000 * (formData.baseTurnoverRate / 100) * formData.regrettableFactor)}</span> would be regrettable losses.
                   </p>
                 </div>
               </div>
            )}

             {/* --- DC PLAN --- */}
            {activeSection === 'dcplan' && (
               <div className="space-y-8 animate-fadeIn">
                 <div className="border-b border-gray-100 pb-4">
                   <h2 className="text-lg font-bold text-gray-900">401(k) / DC Plan Config</h2>
                   <p className="text-sm text-gray-500">Configure retirement plan eligibility, matching rules, and vesting.</p>
                 </div>

                 <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
                    <div className="sm:col-span-6 bg-green-50 p-4 rounded-lg border border-green-100 mb-2 flex items-start">
                       <input
                            type="checkbox"
                            name="dcAutoEnroll"
                            checked={formData.dcAutoEnroll}
                            onChange={handleChange}
                            className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded mt-1"
                       />
                       <div className="ml-3">
                          <label className="block text-sm font-medium text-green-900">Enable Auto-Enrollment</label>
                          <p className="text-xs text-green-700 mt-0.5">New hires will be automatically enrolled upon eligibility.</p>
                       </div>
                    </div>

                    <InputField label="Eligibility Period" {...inputProps('dcEligibilityMonths')} type="number" suffix="Months" helper="Wait period before joining" />
                    <InputField label="Default Deferral Rate" {...inputProps('dcDefaultDeferral')} type="number" step="0.5" suffix="%" helper="Initial contribution for auto-enrolled" />

                    <div className="sm:col-span-3">
                       <label className="block text-sm font-medium text-gray-700">Vesting Schedule</label>
                       <select
                         name="dcVestingSchedule"
                         value={formData.dcVestingSchedule}
                         onChange={handleChange}
                         className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border shadow-sm"
                       >
                         <option value="immediate">Immediate</option>
                         <option value="cliff_3">3-Year Cliff</option>
                         <option value="graded_5">5-Year Graded</option>
                       </select>
                    </div>

                    <div className="col-span-6 h-px bg-gray-200 my-2"></div>
                    <h4 className="col-span-6 text-sm font-semibold text-gray-900">Employer Match Formula</h4>

                    <div className="sm:col-span-6 mb-2">
                       <label className="block text-sm font-medium text-gray-700 mb-2">Formula Structure</label>
                       <div className="grid grid-cols-3 gap-4">
                         {['simple', 'tiered', 'stretch'].map((type) => (
                           <label key={type} className={`flex items-center justify-center px-4 py-2 border rounded-md cursor-pointer text-sm font-medium uppercase ${formData.dcMatchFormula === type ? 'bg-fidelity-green text-white border-fidelity-green' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}>
                             <input type="radio" name="dcMatchFormula" value={type} checked={formData.dcMatchFormula === type} onChange={handleChange} className="sr-only" />
                             {type}
                           </label>
                         ))}
                       </div>
                    </div>

                    <InputField label="Match Percentage" {...inputProps('dcMatchPercent')} type="number" suffix="%" helper="% of employee contribution matched" />
                    <InputField label="Match Limit" {...inputProps('dcMatchLimit')} type="number" suffix="%" helper="Up to % of annual salary" />

                    <div className="col-span-6 h-px bg-gray-200 my-2"></div>
                    <div className="sm:col-span-6 flex items-center justify-between mb-2">
                        <h4 className="text-sm font-semibold text-gray-900">Auto-Escalation</h4>
                        <div className="flex items-center">
                            <input type="checkbox" name="dcAutoEscalation" checked={formData.dcAutoEscalation} onChange={handleChange} className="h-4 w-4 text-fidelity-green rounded" />
                            <span className="ml-2 text-sm text-gray-600">Enabled</span>
                        </div>
                    </div>
                    {formData.dcAutoEscalation && (
                      <>
                        <InputField label="Annual Increase" {...inputProps('dcEscalationRate')} type="number" step="0.5" suffix="%" helper="Yearly step-up" />
                        <InputField label="Escalation Cap" {...inputProps('dcEscalationCap')} type="number" suffix="%" helper="Max deferral rate" />
                      </>
                    )}
                 </div>
               </div>
            )}

            {/* --- ADVANCED SETTINGS --- */}
            {activeSection === 'advanced' && (
              <div className="space-y-8 animate-fadeIn">
                <div className="border-b border-gray-100 pb-4">
                  <h2 className="text-lg font-bold text-gray-900">Advanced Execution Settings</h2>
                  <p className="text-sm text-gray-500">Configure engine performance, logging, and validation rules.</p>
                </div>

                {/* Engine Selection */}
                <div className="bg-gray-50 p-6 rounded-lg border border-gray-200">
                  <h3 className="text-sm font-bold text-gray-900 flex items-center mb-4">
                    <Zap size={16} className="mr-2 text-yellow-500" /> Simulation Engine
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <label className={`relative flex flex-col p-4 border rounded-lg cursor-pointer transition-all ${formData.engine === 'polars' ? 'border-fidelity-green bg-green-50 ring-1 ring-fidelity-green' : 'border-gray-200 bg-white hover:border-gray-300'}`}>
                      <input
                        type="radio"
                        name="engine"
                        value="polars"
                        checked={formData.engine === 'polars'}
                        onChange={handleChange}
                        className="absolute top-4 right-4 h-4 w-4 text-fidelity-green focus:ring-fidelity-green"
                      />
                      <span className="font-bold text-gray-900">Polars Engine (Recommended)</span>
                      <span className="text-xs text-gray-500 mt-1">High-performance Rust-based engine. Up to 375x faster for large datasets.</span>
                      <span className="mt-3 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 w-fit">Fastest</span>
                    </label>

                    <label className={`relative flex flex-col p-4 border rounded-lg cursor-pointer transition-all ${formData.engine === 'pandas' ? 'border-fidelity-green bg-green-50 ring-1 ring-fidelity-green' : 'border-gray-200 bg-white hover:border-gray-300'}`}>
                      <input
                        type="radio"
                        name="engine"
                        value="pandas"
                        checked={formData.engine === 'pandas'}
                        onChange={handleChange}
                        className="absolute top-4 right-4 h-4 w-4 text-fidelity-green focus:ring-fidelity-green"
                      />
                      <span className="font-bold text-gray-900">Pandas Engine (Legacy)</span>
                      <span className="text-xs text-gray-500 mt-1">Standard Python dataframe library. Better for debugging custom logic.</span>
                      <span className="mt-3 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 w-fit">Stable</span>
                    </label>
                  </div>
                </div>

                {/* System Configuration */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                   <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                      <h3 className="text-sm font-bold text-gray-900 flex items-center mb-4">
                        <Server size={16} className="mr-2 text-blue-500" /> System Resources
                      </h3>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                           <span className="text-sm text-gray-700">Enable Multithreading</span>
                           <input
                              type="checkbox"
                              name="enableMultithreading"
                              checked={formData.enableMultithreading}
                              onChange={handleChange}
                              className="h-5 w-5 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
                           />
                        </div>
                        <div className="flex items-center justify-between">
                           <span className="text-sm text-gray-700">Checkpoint Frequency</span>
                           <select
                              name="checkpointFrequency"
                              value={formData.checkpointFrequency}
                              onChange={handleChange}
                              className="text-sm border-gray-300 rounded-md shadow-sm focus:ring-fidelity-green focus:border-fidelity-green"
                           >
                              <option value="year">Every Year</option>
                              <option value="stage">Every Stage (Debug)</option>
                              <option value="none">Disabled (Fastest)</option>
                           </select>
                        </div>
                        <div className="pt-2 border-t border-gray-100">
                           <label className="block text-xs font-medium text-gray-500 mb-1">Max Memory Limit (GB)</label>
                           <input
                             type="number"
                             name="memoryLimitGB"
                             value={formData.memoryLimitGB}
                             onChange={handleChange}
                             className="w-full text-sm border-gray-300 rounded-md p-1.5 border"
                           />
                        </div>
                      </div>
                   </div>

                   <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
                      <h3 className="text-sm font-bold text-gray-900 flex items-center mb-4">
                        <Shield size={16} className="mr-2 text-purple-500" /> Safety & Logging
                      </h3>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                           <span className="text-sm text-gray-700">Strict Schema Validation</span>
                           <input
                              type="checkbox"
                              name="strictValidation"
                              checked={formData.strictValidation}
                              onChange={handleChange}
                              className="h-5 w-5 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
                           />
                        </div>
                        <div className="flex items-center justify-between">
                           <span className="text-sm text-gray-700">Logging Level</span>
                           <select
                              name="logLevel"
                              value={formData.logLevel}
                              onChange={handleChange}
                              className="text-sm border-gray-300 rounded-md shadow-sm focus:ring-fidelity-green focus:border-fidelity-green"
                           >
                              <option value="DEBUG">DEBUG</option>
                              <option value="INFO">INFO</option>
                              <option value="WARNING">WARNING</option>
                           </select>
                        </div>
                      </div>
                   </div>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>

      {/* Navigation Blocker - only rendered in data router context */}
      {dataRouterContext && (
        <NavigationBlocker isDirty={isDirty} dirtySections={dirtySections} />
      )}

      {/* Template Selection Modal */}
      {showTemplateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
            <div className="p-6 border-b border-gray-200 flex-shrink-0">
              <h2 className="text-xl font-bold text-gray-900">Load Configuration Template</h2>
              <p className="text-sm text-gray-500 mt-1">Select a template to pre-fill configuration values</p>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-3">
              {templates.map(template => (
                <button
                  key={template.id}
                  onClick={() => {
                    // Apply template config to form
                    const cfg = template.config;
                    setFormData(prev => ({
                      ...prev,
                      // Simulation
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
                      // Compensation
                      meritBudget: cfg.compensation?.merit_budget_percent ?? prev.meritBudget,
                      colaRate: cfg.compensation?.cola_rate_percent ?? prev.colaRate,
                      // DC Plan
                      dcAutoEnroll: cfg.dc_plan?.auto_enroll ?? prev.dcAutoEnroll,
                      dcMatchPercent: cfg.dc_plan?.match_percent ?? prev.dcMatchPercent,
                      dcMatchLimit: cfg.dc_plan?.match_limit_percent ?? prev.dcMatchLimit,
                      dcAutoEscalation: cfg.dc_plan?.auto_escalation ?? prev.dcAutoEscalation,
                    }));
                    setShowTemplateModal(false);
                  }}
                  className="w-full text-left p-4 border border-gray-200 rounded-lg hover:border-fidelity-green hover:bg-green-50 transition-colors"
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-semibold text-gray-900">{template.name}</h3>
                      <p className="text-sm text-gray-500 mt-1">{template.description}</p>
                    </div>
                    <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded capitalize">
                      {template.category}
                    </span>
                  </div>
                </button>
              ))}
            </div>
            <div className="p-4 border-t border-gray-200 bg-gray-50 flex-shrink-0 rounded-b-xl">
              <button
                onClick={() => setShowTemplateModal(false)}
                className="px-4 py-2 text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
