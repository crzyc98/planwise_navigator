import React, { useState, useEffect, useRef } from 'react';
import { Save, AlertTriangle, FileText, Settings, HelpCircle, TrendingUp, Users, DollarSign, Zap, Server, Shield, PieChart, Database, Upload, Check, X, ArrowLeft } from 'lucide-react';
import { useNavigate, useOutletContext, useParams } from 'react-router-dom';
import { LayoutContextType } from './Layout';
import { updateWorkspace as apiUpdateWorkspace, getScenario, updateScenario, Scenario, uploadCensusFile, validateFilePath, listTemplates, Template } from '../services/api';

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

    // New Hire
    newHireStrategy: 'percentile', // 'percentile' | 'fixed'
    targetPercentile: 50,
    newHireCompVariance: 5.0, // +/- 5%

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

  // Save status state
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState('');


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
            promoBudget: cfg.compensation?.promotion_budget_percent ?? prev.promoBudget,

            // New Hire
            newHireStrategy: cfg.new_hire?.strategy || prev.newHireStrategy,
            targetPercentile: cfg.new_hire?.target_percentile ?? prev.targetPercentile,
            newHireCompVariance: cfg.new_hire?.compensation_variance_percent ?? prev.newHireCompVariance,

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
      promoBudget: cfg.compensation?.promotion_budget_percent || prev.promoBudget,

      // New Hire
      newHireStrategy: cfg.new_hire?.strategy || prev.newHireStrategy,
      targetPercentile: cfg.new_hire?.target_percentile || prev.targetPercentile,
      newHireCompVariance: cfg.new_hire?.compensation_variance_percent || prev.newHireCompVariance,

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
          promotion_budget_percent: Number(formData.promoBudget),
        },
        new_hire: {
          strategy: formData.newHireStrategy,
          target_percentile: Number(formData.targetPercentile),
          compensation_variance_percent: Number(formData.newHireCompVariance),
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
             ) : (
               <>
                 <Save size={18} className="mr-2" />
                 Save Config
               </>
             )}
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
                  className={`w-full text-left px-3 py-3 rounded-md text-sm font-medium transition-colors flex items-center ${
                    activeSection === item.id
                      ? 'bg-white text-fidelity-green shadow-sm border border-gray-200'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  <item.icon size={16} className={`mr-3 ${activeSection === item.id ? 'text-fidelity-green' : 'text-gray-400'}`} />
                  {item.label}
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
