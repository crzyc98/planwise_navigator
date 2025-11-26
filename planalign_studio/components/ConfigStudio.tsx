import React, { useState, useEffect, useRef } from 'react';
import { Save, AlertTriangle, FileText, Settings, HelpCircle, TrendingUp, Users, DollarSign, Briefcase, Zap, Server, Shield, PieChart, Database, Upload, Check, X, Plus, Play, Trash2, Layers } from 'lucide-react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { LayoutContextType } from './Layout';
import { updateWorkspace as apiUpdateWorkspace, createScenario, listScenarios, deleteScenario, Scenario } from '../services/api';

export default function ConfigStudio() {
  const navigate = useNavigate();
  const { activeWorkspace } = useOutletContext<LayoutContextType>();
  const [activeSection, setActiveSection] = useState('scenarios');

  // File upload state
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
  const [uploadMessage, setUploadMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    signOnBonusAllowed: true,
    signOnBonusBudget: 50000,

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

    // Hiring Plan
    hiringTargets: {
      Engineering: 15,
      Sales: 20,
      Marketing: 5,
      Operations: 8
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

  const handleHiringTargetChange = (dept: string, val: string) => {
    setFormData(prev => ({
      ...prev,
      hiringTargets: {
        ...prev.hiringTargets,
        [dept]: parseInt(val) || 0
      }
    }));
  };

  // Save status state
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState('');

  // Scenario state
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenariosLoading, setScenariosLoading] = useState(false);
  const [newScenarioName, setNewScenarioName] = useState('');
  const [newScenarioDesc, setNewScenarioDesc] = useState('');
  const [isCreatingScenario, setIsCreatingScenario] = useState(false);

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
      signOnBonusAllowed: cfg.new_hire?.sign_on_bonus_allowed ?? prev.signOnBonusAllowed,
      signOnBonusBudget: cfg.new_hire?.sign_on_bonus_budget || prev.signOnBonusBudget,

      // Turnover
      baseTurnoverRate: cfg.turnover?.base_rate_percent || prev.baseTurnoverRate,
      regrettableFactor: cfg.turnover?.regrettable_factor || prev.regrettableFactor,
      involuntaryRate: cfg.turnover?.involuntary_rate_percent || prev.involuntaryRate,
      turnoverBands: cfg.turnover?.tenure_bands || prev.turnoverBands,

      // Hiring
      hiringTargets: cfg.hiring?.targets || prev.hiringTargets,

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

  // Load scenarios on mount
  useEffect(() => {
    const loadScenarios = async () => {
      if (!activeWorkspace?.id) return;
      setScenariosLoading(true);
      try {
        const data = await listScenarios(activeWorkspace.id);
        setScenarios(data);
      } catch (err) {
        console.error('Failed to load scenarios:', err);
      } finally {
        setScenariosLoading(false);
      }
    };
    loadScenarios();
  }, [activeWorkspace?.id]);

  // Create a new scenario
  const handleCreateScenario = async () => {
    if (!newScenarioName.trim() || !activeWorkspace?.id) return;
    setIsCreatingScenario(true);
    try {
      const created = await createScenario(activeWorkspace.id, {
        name: newScenarioName,
        description: newScenarioDesc || undefined,
      });
      setScenarios(prev => [...prev, created]);
      setNewScenarioName('');
      setNewScenarioDesc('');
    } catch (err) {
      console.error('Failed to create scenario:', err);
    } finally {
      setIsCreatingScenario(false);
    }
  };

  // Delete a scenario
  const handleDeleteScenario = async (scenarioId: string) => {
    if (!activeWorkspace?.id) return;
    if (!confirm('Are you sure you want to delete this scenario?')) return;
    try {
      await deleteScenario(activeWorkspace.id, scenarioId);
      setScenarios(prev => prev.filter(s => s.id !== scenarioId));
    } catch (err) {
      console.error('Failed to delete scenario:', err);
    }
  };

  // Handle save configuration
  const handleSaveConfig = async () => {
    setSaveStatus('saving');
    setSaveMessage('Saving configuration...');

    try {
      // Convert formData to the API config format
      const configPayload = {
        simulation: {
          name: formData.name,
          start_year: formData.startYear,
          end_year: formData.endYear,
          random_seed: formData.seed,
          target_growth_rate: formData.targetGrowthRate / 100, // Convert % to decimal
        },
        workforce: {
          total_termination_rate: formData.totalTerminationRate / 100, // Convert % to decimal
          new_hire_termination_rate: formData.newHireTerminationRate / 100,
        },
        data_sources: {
          census_parquet_path: formData.censusDataPath,
        },
        compensation: {
          merit_budget_percent: formData.meritBudget,
          cola_rate_percent: formData.colaRate,
          promotion_increase_percent: formData.promoIncrease,
          promotion_budget_percent: formData.promoBudget,
        },
        new_hire: {
          strategy: formData.newHireStrategy,
          target_percentile: formData.targetPercentile,
          compensation_variance_percent: formData.newHireCompVariance,
          sign_on_bonus_allowed: formData.signOnBonusAllowed,
          sign_on_bonus_budget: formData.signOnBonusBudget,
        },
        turnover: {
          base_rate_percent: formData.baseTurnoverRate,
          regrettable_factor: formData.regrettableFactor,
          involuntary_rate_percent: formData.involuntaryRate,
          tenure_bands: formData.turnoverBands,
        },
        hiring: {
          targets: formData.hiringTargets,
        },
        dc_plan: {
          eligibility_months: formData.dcEligibilityMonths,
          auto_enroll: formData.dcAutoEnroll,
          default_deferral_percent: formData.dcDefaultDeferral,
          match_formula: formData.dcMatchFormula,
          match_percent: formData.dcMatchPercent,
          match_limit_percent: formData.dcMatchLimit,
          vesting_schedule: formData.dcVestingSchedule,
          auto_escalation: formData.dcAutoEscalation,
          escalation_rate_percent: formData.dcEscalationRate,
          escalation_cap_percent: formData.dcEscalationCap,
        },
        advanced: {
          engine: formData.engine,
          enable_multithreading: formData.enableMultithreading,
          checkpoint_frequency: formData.checkpointFrequency,
          memory_limit_gb: formData.memoryLimitGB,
          log_level: formData.logLevel,
          strict_validation: formData.strictValidation,
        },
      };

      // Save to workspace via API
      await apiUpdateWorkspace(activeWorkspace.id, {
        base_config: configPayload,
      });
      console.log('Config saved to workspace:', activeWorkspace.id, configPayload);

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

  // Helper for input fields
  const InputField = ({ label, name, type = "text", width = "col-span-3", suffix = "", helper = "", step = "1", min }: any) => (
    <div className={`sm:${width}`}>
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      <div className="mt-1 relative rounded-md shadow-sm">
        <input
          type={type}
          name={name}
          value={(formData as any)[name]}
          onChange={handleChange}
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

  const calculateTotalHiringGrowth = () => {
    const totalPct = (Object.values(formData.hiringTargets) as number[]).reduce((acc, val) => acc + val, 0);
    return totalPct;
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex justify-between items-center mb-6">
        <div>
           <h1 className="text-2xl font-bold text-gray-900">Configuration Studio</h1>
           <p className="text-gray-500 text-sm">Create and edit simulation parameters.</p>
        </div>
        <div className="flex space-x-3">
           <button className="px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 flex items-center font-medium shadow-sm transition-colors">
             <FileText size={18} className="mr-2" />
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
               { id: 'scenarios', label: 'Scenarios', icon: Layers },
               { id: 'datasources', label: 'Data Sources', icon: Database },
               { id: 'simulation', label: 'Simulation Settings', icon: TrendingUp },
               { id: 'compensation', label: 'Compensation', icon: DollarSign },
               { id: 'newhire', label: 'New Hire Strategy', icon: Users },
               { id: 'turnover', label: 'Workforce & Turnover', icon: AlertTriangle },
               { id: 'hiring', label: 'Hiring Plan', icon: Briefcase },
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

            {/* --- SCENARIOS --- */}
            {activeSection === 'scenarios' && (
              <div className="space-y-8 animate-fadeIn">
                <div className="border-b border-gray-100 pb-4">
                  <h2 className="text-lg font-bold text-gray-900">Scenarios</h2>
                  <p className="text-sm text-gray-500">Create and manage simulation scenarios. Each scenario can have different configuration overrides.</p>
                </div>

                {/* Create New Scenario */}
                <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
                  <div className="flex items-center mb-4">
                    <Plus className="w-5 h-5 text-fidelity-green mr-3" />
                    <h3 className="font-semibold text-gray-900">Create New Scenario</h3>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Scenario Name</label>
                      <input
                        type="text"
                        value={newScenarioName}
                        onChange={(e) => setNewScenarioName(e.target.value)}
                        placeholder="e.g., Baseline 2025, High Growth, Conservative"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Description (Optional)</label>
                      <input
                        type="text"
                        value={newScenarioDesc}
                        onChange={(e) => setNewScenarioDesc(e.target.value)}
                        placeholder="Brief description of this scenario..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                      />
                    </div>
                    <button
                      onClick={handleCreateScenario}
                      disabled={!newScenarioName.trim() || isCreatingScenario}
                      className={`px-4 py-2 rounded-lg text-sm font-medium flex items-center ${
                        !newScenarioName.trim() || isCreatingScenario
                          ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                          : 'bg-fidelity-green text-white hover:bg-fidelity-dark'
                      }`}
                    >
                      {isCreatingScenario ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                          Creating...
                        </>
                      ) : (
                        <>
                          <Plus size={16} className="mr-2" />
                          Create Scenario
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Existing Scenarios */}
                <div>
                  <h3 className="font-semibold text-gray-900 mb-4">Existing Scenarios ({scenarios.length})</h3>

                  {scenariosLoading ? (
                    <div className="text-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
                      <p className="text-sm text-gray-500">Loading scenarios...</p>
                    </div>
                  ) : scenarios.length === 0 ? (
                    <div className="text-center py-8 bg-gray-50 rounded-lg border border-dashed border-gray-300">
                      <Layers className="w-10 h-10 text-gray-400 mx-auto mb-3" />
                      <p className="text-sm text-gray-600">No scenarios yet</p>
                      <p className="text-xs text-gray-400">Create your first scenario above to get started</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {scenarios.map((scenario) => (
                        <div
                          key={scenario.id}
                          className="bg-white rounded-lg p-4 border border-gray-200 flex items-center justify-between hover:shadow-sm transition-shadow"
                        >
                          <div className="flex-1">
                            <div className="flex items-center">
                              <h4 className="font-medium text-gray-900">{scenario.name}</h4>
                              <span className={`ml-3 px-2 py-0.5 text-xs rounded-full ${
                                scenario.status === 'completed' ? 'bg-green-100 text-green-700' :
                                scenario.status === 'running' ? 'bg-blue-100 text-blue-700' :
                                scenario.status === 'failed' ? 'bg-red-100 text-red-700' :
                                'bg-gray-100 text-gray-600'
                              }`}>
                                {scenario.status === 'not_run' ? 'Not Run' : scenario.status}
                              </span>
                            </div>
                            {scenario.description && (
                              <p className="text-sm text-gray-500 mt-1">{scenario.description}</p>
                            )}
                            <p className="text-xs text-gray-400 mt-1">
                              Created: {new Date(scenario.created_at).toLocaleDateString()}
                            </p>
                          </div>
                          <div className="flex items-center space-x-2">
                            <button
                              onClick={() => navigate('/simulate')}
                              className="px-3 py-1.5 bg-fidelity-green text-white rounded-lg text-sm hover:bg-fidelity-dark flex items-center"
                            >
                              <Play size={14} className="mr-1" />
                              Run
                            </button>
                            <button
                              onClick={() => handleDeleteScenario(scenario.id)}
                              className="p-1.5 text-gray-400 hover:text-red-500 rounded"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Info Box */}
                <div className="bg-blue-50 rounded-xl p-6 border border-blue-100">
                  <div className="flex items-start">
                    <HelpCircle className="w-5 h-5 text-blue-500 mr-3 mt-0.5" />
                    <div>
                      <h4 className="font-semibold text-blue-900 mb-2">How Scenarios Work</h4>
                      <ul className="text-sm text-blue-700 space-y-1">
                        <li>• Each scenario inherits the workspace's base configuration</li>
                        <li>• You can override specific settings per scenario</li>
                        <li>• Run simulations independently for each scenario</li>
                        <li>• Compare results across multiple scenarios</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            )}

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
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setUploadStatus('uploading');
                          setUploadMessage(`Uploading ${file.name}...`);
                          // TODO: Implement actual file upload to API
                          setTimeout(() => {
                            setFormData(prev => ({
                              ...prev,
                              censusDataPath: `data/${file.name}`,
                              censusDataStatus: 'loaded',
                              censusRowCount: 1000,
                              censusLastModified: new Date().toISOString().split('T')[0]
                            }));
                            setUploadStatus('success');
                            setUploadMessage('File uploaded successfully!');
                          }, 1500);
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
                        onClick={() => {
                          // TODO: Validate path and load file info
                          setFormData(prev => ({
                            ...prev,
                            censusDataStatus: 'loaded'
                          }));
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
                  <InputField label="Scenario Name" name="name" width="col-span-4" />

                  <div className="col-span-6 grid grid-cols-2 gap-4">
                    <InputField label="Start Year" name="startYear" type="number" width="col-span-1" />
                    <InputField label="End Year" name="endYear" type="number" width="col-span-1" />
                  </div>

                  <InputField
                    label="Random Seed"
                    name="seed"
                    type="number"
                    helper="Fixed seed (e.g., 42) ensures identical runs."
                  />

                  <InputField
                    label="Target Growth Rate"
                    name="targetGrowthRate"
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
                      <InputField label="Merit Budget" name="meritBudget" type="number" step="0.1" suffix="%" helper="Avg. annual performance increase" />
                      <InputField label="COLA / Inflation" name="colaRate" type="number" step="0.1" suffix="%" helper="Cost of living adjustment" />
                    </div>

                    <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider pt-4">Promotions</h3>
                    <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6 bg-gray-50 p-4 rounded-lg border border-gray-200">
                      <InputField label="Avg. Promotion Increase" name="promoIncrease" type="number" step="0.5" suffix="%" helper="Base pay bump on promotion" />

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

                      <InputField label="Promotion Budget" name="promoBudget" type="number" step="0.1" suffix="% of payroll" helper="Budget allocated for level-ups" />
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

                    <div className="pt-4 grid grid-cols-2 gap-6">
                       <InputField label="Sign-on Bonus Budget" name="signOnBonusBudget" type="number" suffix="$" />
                       <div className="flex items-center pt-6">
                          <input
                            type="checkbox"
                            name="signOnBonusAllowed"
                            checked={formData.signOnBonusAllowed}
                            onChange={handleChange}
                            className="h-4 w-4 text-fidelity-green focus:ring-fidelity-green border-gray-300 rounded"
                          />
                          <label className="ml-2 block text-sm text-gray-900">Allow Sign-on Bonuses</label>
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
                       name="totalTerminationRate"
                       type="number"
                       step="0.1"
                       suffix="%"
                       helper="Overall annual termination rate for experienced employees"
                     />
                     <InputField
                       label="New Hire Termination Rate"
                       name="newHireTerminationRate"
                       type="number"
                       step="0.1"
                       suffix="%"
                       helper="First-year termination rate (typically higher than overall)"
                     />
                   </div>
                 </div>

                 <div className="grid grid-cols-1 gap-y-6 gap-x-4 sm:grid-cols-6">
                    <InputField label="Base Annual Turnover" name="baseTurnoverRate" type="number" suffix="%" helper="Expected overall exit rate" />
                    <InputField label="Regrettable Factor" name="regrettableFactor" type="number" step="0.1" suffix="x" helper="Portion of exits that are regrettable (0.0-1.0)" />
                    <InputField label="Involuntary Rate" name="involuntaryRate" type="number" suffix="%" helper="Performance-based exits / layoffs" />
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

            {/* --- HIRING PLAN --- */}
            {activeSection === 'hiring' && (
               <div className="space-y-8 animate-fadeIn">
                 <div className="border-b border-gray-100 pb-4">
                   <h2 className="text-lg font-bold text-gray-900">Departmental Hiring Plan</h2>
                   <p className="text-sm text-gray-500">Set net growth targets by department for the simulation period.</p>
                 </div>

                 <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
                   <table className="min-w-full divide-y divide-gray-200">
                     <thead className="bg-gray-50">
                       <tr>
                         <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Department</th>
                         <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Annual Growth Target (%)</th>
                         <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Priority Level</th>
                       </tr>
                     </thead>
                     <tbody className="bg-white divide-y divide-gray-200">
                       {Object.entries(formData.hiringTargets).map(([dept, target]) => (
                         <tr key={dept}>
                           <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{dept}</td>
                           <td className="px-6 py-4 whitespace-nowrap">
                             <div className="flex items-center">
                               <input
                                 type="number"
                                 value={target}
                                 onChange={(e) => handleHiringTargetChange(dept, e.target.value)}
                                 className="w-20 shadow-sm focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm border-gray-300 rounded-md p-1 border text-right"
                               />
                               <span className="ml-2 text-gray-500">%</span>
                             </div>
                           </td>
                           <td className="px-6 py-4 whitespace-nowrap">
                              <select className="block w-full pl-3 pr-10 py-1 text-base border-gray-300 focus:outline-none focus:ring-fidelity-green focus:border-fidelity-green sm:text-sm rounded-md border">
                                <option>High</option>
                                <option>Medium</option>
                                <option>Low</option>
                              </select>
                           </td>
                         </tr>
                       ))}
                       {/* Summary Row */}
                       <tr className="bg-gray-50 font-semibold text-gray-900">
                          <td className="px-6 py-3 text-sm">Total / Weighted Avg</td>
                          <td className="px-6 py-3 text-sm flex items-center">
                             {calculateTotalHiringGrowth()}% <span className="text-xs font-normal text-gray-500 ml-2">(Aggregate Growth)</span>
                          </td>
                          <td className="px-6 py-3"></td>
                       </tr>
                     </tbody>
                   </table>
                   <div className="bg-gray-50 px-6 py-3 border-t border-gray-200">
                     <button className="text-sm text-fidelity-green font-medium hover:text-fidelity-dark flex items-center">
                       + Add Department
                     </button>
                   </div>
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

                    <InputField label="Eligibility Period" name="dcEligibilityMonths" type="number" suffix="Months" helper="Wait period before joining" />
                    <InputField label="Default Deferral Rate" name="dcDefaultDeferral" type="number" step="0.5" suffix="%" helper="Initial contribution for auto-enrolled" />

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

                    <InputField label="Match Percentage" name="dcMatchPercent" type="number" suffix="%" helper="% of employee contribution matched" />
                    <InputField label="Match Limit" name="dcMatchLimit" type="number" suffix="%" helper="Up to % of annual salary" />

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
                        <InputField label="Annual Increase" name="dcEscalationRate" type="number" step="0.5" suffix="%" helper="Yearly step-up" />
                        <InputField label="Escalation Cap" name="dcEscalationCap" type="number" suffix="%" helper="Max deferral rate" />
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
    </div>
  );
}
