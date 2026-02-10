import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  Scale, DollarSign, Users, TrendingDown, TrendingUp,
  RefreshCw, AlertCircle, ChevronDown, ChevronUp, Database, Loader2, Table, Calendar
} from 'lucide-react';
import {
  listWorkspaces,
  listScenarios,
  listVestingSchedules,
  analyzeVesting,
  getScenarioYears,
  Workspace,
  Scenario,
  VestingScheduleInfo,
  VestingScheduleConfig,
  VestingAnalysisResponse,
  VestingAnalysisRequest,
  EmployeeVestingDetail,
} from '../services/api';

type SortField = 'employee_id' | 'tenure_years' | 'total_employer_contributions' |
  'current_vesting_pct' | 'current_forfeiture' | 'proposed_vesting_pct' |
  'proposed_forfeiture' | 'forfeiture_variance';
type SortDirection = 'asc' | 'desc';

const formatCurrency = (value: number): string => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
};

const formatPercent = (value: number): string => {
  return `${(value * 100).toFixed(1)}%`;
};

const KPICard = ({ title, value, subtext, icon: Icon, color, trend, loading }: any) => (
  <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-200 flex items-start justify-between">
    <div>
      <p className="text-sm font-medium text-gray-500">{title}</p>
      {loading ? (
        <div className="h-8 w-20 bg-gray-200 rounded animate-pulse mt-1" />
      ) : (
        <>
          <h3 className="text-2xl font-bold text-gray-900 mt-1">{value}</h3>
          {subtext && (
            <div className="flex items-center mt-1">
              {trend === 'up' && <TrendingUp size={14} className="text-red-500 mr-1" />}
              {trend === 'down' && <TrendingDown size={14} className="text-green-500 mr-1" />}
              <span className={`text-xs font-medium ${
                trend === 'up' ? 'text-red-500' : trend === 'down' ? 'text-green-500' : 'text-gray-500'
              }`}>{subtext}</span>
            </div>
          )}
        </>
      )}
    </div>
    <div className={`p-2 rounded-lg bg-${color}-50 text-${color}-600`}>
      <Icon size={20} />
    </div>
  </div>
);

const EmptyState = ({ onRefresh }: { onRefresh: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-gray-400">
    <Database size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-gray-600 mb-2">No Analysis Results</h3>
    <p className="text-sm text-gray-500 mb-4 text-center max-w-md">
      Select a completed simulation and vesting schedules to compare, then click "Analyze" to see forfeiture projections.
    </p>
    <button
      onClick={onRefresh}
      className="flex items-center px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Refresh Data
    </button>
  </div>
);

const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-red-400">
    <AlertCircle size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-red-600 mb-2">Failed to Load Analysis</h3>
    <p className="text-sm text-gray-500 mb-4 text-center max-w-md">{message}</p>
    <button
      onClick={onRetry}
      className="flex items-center px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Retry
    </button>
  </div>
);

const TENURE_COLORS = {
  current: '#0088FE',
  proposed: '#00C49F',
};

export default function VestingAnalysis() {
  // State for workspace/scenario selection
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [schedules, setSchedules] = useState<VestingScheduleInfo[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('');
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('');

  // State for year selection
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined);
  const [loadingYears, setLoadingYears] = useState(false);

  // State for schedule selection
  const [currentSchedule, setCurrentSchedule] = useState<VestingScheduleConfig | null>(null);
  const [proposedSchedule, setProposedSchedule] = useState<VestingScheduleConfig | null>(null);

  // State for results
  const [analysisResult, setAnalysisResult] = useState<VestingAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // State for employee details sorting (T045)
  const [sortField, setSortField] = useState<SortField>('forfeiture_variance');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [showEmployeeDetails, setShowEmployeeDetails] = useState(false);

  // Fetch workspaces and schedules on mount
  useEffect(() => {
    fetchWorkspaces();
    fetchSchedules();
  }, []);

  // Fetch scenarios when workspace changes
  useEffect(() => {
    if (selectedWorkspaceId) {
      fetchScenarios(selectedWorkspaceId);
    } else {
      setScenarios([]);
      setSelectedScenarioId('');
    }
  }, [selectedWorkspaceId]);

  // Fetch available years when scenario changes
  useEffect(() => {
    if (selectedWorkspaceId && selectedScenarioId) {
      fetchYears(selectedWorkspaceId, selectedScenarioId);
    } else {
      setAvailableYears([]);
      setSelectedYear(undefined);
    }
  }, [selectedWorkspaceId, selectedScenarioId]);

  const fetchWorkspaces = async () => {
    try {
      const data = await listWorkspaces();
      setWorkspaces(data);
      if (data.length > 0) {
        setSelectedWorkspaceId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch workspaces:', err);
    }
  };

  const fetchScenarios = async (workspaceId: string) => {
    setLoadingScenarios(true);
    try {
      const data = await listScenarios(workspaceId);
      setScenarios(data);
      const completedScenarios = data.filter(s => s.status === 'completed');
      if (completedScenarios.length > 0 && !selectedScenarioId) {
        setSelectedScenarioId(completedScenarios[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const fetchSchedules = async () => {
    try {
      const data = await listVestingSchedules();
      setSchedules(data.schedules);
      // Set default selections
      if (data.schedules.length >= 2) {
        const graded5 = data.schedules.find(s => s.schedule_type === 'graded_5_year');
        const cliff3 = data.schedules.find(s => s.schedule_type === 'cliff_3_year');
        if (graded5) {
          setCurrentSchedule({
            schedule_type: graded5.schedule_type,
            name: graded5.name,
          });
        }
        if (cliff3) {
          setProposedSchedule({
            schedule_type: cliff3.schedule_type,
            name: cliff3.name,
          });
        }
      }
    } catch (err) {
      console.error('Failed to fetch vesting schedules:', err);
    }
  };

  const fetchYears = async (workspaceId: string, scenarioId: string) => {
    setLoadingYears(true);
    try {
      const data = await getScenarioYears(workspaceId, scenarioId);
      setAvailableYears(data.years);
      setSelectedYear(data.default_year);
    } catch (err) {
      console.error('Failed to fetch scenario years:', err);
      setAvailableYears([]);
      setSelectedYear(undefined);
    } finally {
      setLoadingYears(false);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedWorkspaceId || !selectedScenarioId || !currentSchedule || !proposedSchedule || !selectedYear) {
      return;
    }

    setAnalyzing(true);
    setError(null);

    try {
      const request: VestingAnalysisRequest = {
        current_schedule: currentSchedule,
        proposed_schedule: proposedSchedule,
        simulation_year: selectedYear,
      };
      const result = await analyzeVesting(selectedWorkspaceId, selectedScenarioId, request);
      setAnalysisResult(result);
    } catch (err: any) {
      console.error('Failed to run analysis:', err);
      setError(err.message || 'Failed to run vesting analysis');
      setAnalysisResult(null);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleRefresh = () => {
    fetchWorkspaces();
    fetchSchedules();
    if (selectedWorkspaceId) {
      fetchScenarios(selectedWorkspaceId);
    }
  };

  const handleScheduleChange = (type: 'current' | 'proposed', scheduleType: string) => {
    const schedule = schedules.find(s => s.schedule_type === scheduleType);
    if (schedule) {
      const existingConfig = type === 'current' ? currentSchedule : proposedSchedule;
      const config: VestingScheduleConfig = {
        schedule_type: schedule.schedule_type,
        name: schedule.name,
        // Preserve hours settings when switching schedule types (FR-008)
        require_hours_credit: existingConfig?.require_hours_credit ?? false,
        hours_threshold: existingConfig?.hours_threshold ?? 1000,
      };
      if (type === 'current') {
        setCurrentSchedule(config);
      } else {
        setProposedSchedule(config);
      }
    }
  };

  // T004: Handle hours requirement toggle (FR-001, FR-003)
  const handleHoursToggle = (type: 'current' | 'proposed', enabled: boolean) => {
    const setter = type === 'current' ? setCurrentSchedule : setProposedSchedule;
    const current = type === 'current' ? currentSchedule : proposedSchedule;
    if (current) {
      setter({
        ...current,
        require_hours_credit: enabled,
        hours_threshold: enabled ? (current.hours_threshold ?? 1000) : undefined,
      });
    }
  };

  // T005: Handle hours threshold input change (FR-002, FR-004)
  const handleHoursThresholdChange = (type: 'current' | 'proposed', value: number) => {
    const setter = type === 'current' ? setCurrentSchedule : setProposedSchedule;
    const current = type === 'current' ? currentSchedule : proposedSchedule;
    if (current) {
      setter({
        ...current,
        hours_threshold: Math.min(2080, Math.max(0, value)),
      });
    }
  };

  const completedScenarios = scenarios.filter(s => s.status === 'completed');

  // Prepare chart data for tenure band comparison
  const tenureBandChartData = analysisResult?.by_tenure_band.map(band => ({
    tenure_band: band.tenure_band,
    'Current Forfeitures': band.current_forfeitures,
    'Proposed Forfeitures': band.proposed_forfeitures,
    employees: band.employee_count,
  })) || [];

  const canAnalyze = selectedWorkspaceId && selectedScenarioId && currentSchedule && proposedSchedule && selectedYear;

  // Sort employee details (T045)
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const sortedEmployeeDetails: EmployeeVestingDetail[] = analysisResult?.employee_details
    ? [...analysisResult.employee_details].sort((a, b) => {
        const aVal = a[sortField];
        const bVal = b[sortField];
        const multiplier = sortDirection === 'asc' ? 1 : -1;
        if (typeof aVal === 'string' && typeof bVal === 'string') {
          return aVal.localeCompare(bVal) * multiplier;
        }
        return ((aVal as number) - (bVal as number)) * multiplier;
      })
    : [];

  // Sort header component
  const SortHeader = ({ field, label }: { field: SortField; label: string }) => (
    <th
      className="text-right py-3 px-4 font-semibold text-gray-600 cursor-pointer hover:bg-gray-50 select-none"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center justify-end gap-1">
        {label}
        {sortField === field ? (
          sortDirection === 'asc' ? (
            <ChevronUp size={14} className="text-fidelity-green" />
          ) : (
            <ChevronDown size={14} className="text-fidelity-green" />
          )
        ) : (
          <ChevronDown size={14} className="text-gray-300" />
        )}
      </div>
    </th>
  );

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Vesting Analysis</h1>
          <p className="text-gray-500 mt-1">Compare vesting schedules and project forfeiture differences.</p>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 text-gray-700 shadow-sm transition-colors"
          title="Refresh"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Selection Controls */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Workspace Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Workspace</label>
            <div className="relative">
              <select
                value={selectedWorkspaceId}
                onChange={(e) => {
                  setSelectedWorkspaceId(e.target.value);
                  setSelectedScenarioId('');
                  setAnalysisResult(null);
                }}
                className="appearance-none w-full bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
              >
                <option value="">Select Workspace</option>
                {workspaces.map(ws => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Scenario Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scenario</label>
            <div className="relative">
              <select
                value={selectedScenarioId}
                onChange={(e) => {
                  setSelectedScenarioId(e.target.value);
                  setAvailableYears([]);
                  setSelectedYear(undefined);
                  setAnalysisResult(null);
                }}
                disabled={!selectedWorkspaceId || loadingScenarios}
                className="appearance-none w-full bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm disabled:bg-gray-50 disabled:text-gray-400"
              >
                <option value="">
                  {loadingScenarios ? 'Loading...' : completedScenarios.length === 0 ? 'No completed runs' : 'Select Scenario'}
                </option>
                {completedScenarios.map(scenario => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Current Schedule Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Current Schedule</label>
            <div className="relative">
              <select
                value={currentSchedule?.schedule_type || ''}
                onChange={(e) => handleScheduleChange('current', e.target.value)}
                className="appearance-none w-full bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
              >
                <option value="">Select Schedule</option>
                {schedules.map(schedule => (
                  <option key={schedule.schedule_type} value={schedule.schedule_type}>
                    {schedule.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
            </div>
            {/* T007/T008: Hours Requirement Toggle for Current Schedule (FR-001, FR-002, FR-003, FR-007) */}
            <div className="mt-2">
              <label className="flex items-center text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={currentSchedule?.require_hours_credit ?? false}
                  onChange={(e) => handleHoursToggle('current', e.target.checked)}
                  className="mr-2 rounded border-gray-300 text-fidelity-green focus:ring-fidelity-green"
                />
                Require 1,000 hours
              </label>
              {currentSchedule?.require_hours_credit && (
                <div className="mt-1 flex items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    max={2080}
                    value={currentSchedule.hours_threshold ?? 1000}
                    onChange={(e) => handleHoursThresholdChange('current', parseInt(e.target.value) || 0)}
                    className="w-20 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-fidelity-green focus:border-fidelity-green"
                  />
                  <span className="text-xs text-gray-500">hours/year</span>
                </div>
              )}
              <p className="text-xs text-gray-400 mt-1">
                Employees below threshold lose 1 year vesting credit
              </p>
            </div>
          </div>

          {/* Proposed Schedule Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Proposed Schedule</label>
            <div className="relative">
              <select
                value={proposedSchedule?.schedule_type || ''}
                onChange={(e) => handleScheduleChange('proposed', e.target.value)}
                className="appearance-none w-full bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
              >
                <option value="">Select Schedule</option>
                {schedules.map(schedule => (
                  <option key={schedule.schedule_type} value={schedule.schedule_type}>
                    {schedule.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
            </div>
            {/* T009/T010: Hours Requirement Toggle for Proposed Schedule (FR-001, FR-002, FR-003, FR-007) */}
            <div className="mt-2">
              <label className="flex items-center text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={proposedSchedule?.require_hours_credit ?? false}
                  onChange={(e) => handleHoursToggle('proposed', e.target.checked)}
                  className="mr-2 rounded border-gray-300 text-fidelity-green focus:ring-fidelity-green"
                />
                Require 1,000 hours
              </label>
              {proposedSchedule?.require_hours_credit && (
                <div className="mt-1 flex items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    max={2080}
                    value={proposedSchedule.hours_threshold ?? 1000}
                    onChange={(e) => handleHoursThresholdChange('proposed', parseInt(e.target.value) || 0)}
                    className="w-20 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-fidelity-green focus:border-fidelity-green"
                  />
                  <span className="text-xs text-gray-500">hours/year</span>
                </div>
              )}
              <p className="text-xs text-gray-400 mt-1">
                Employees below threshold lose 1 year vesting credit
              </p>
            </div>
          </div>
        </div>

        {/* Analysis Year Selector */}
        <div className="mt-4 flex items-end gap-4">
          <div className="w-48">
            <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center">
              <Calendar size={14} className="mr-1.5 text-gray-400" />
              Analysis Year
            </label>
            <div className="relative">
              <select
                value={selectedYear ?? ''}
                onChange={(e) => {
                  setSelectedYear(e.target.value ? Number(e.target.value) : undefined);
                  setAnalysisResult(null);
                }}
                disabled={!selectedScenarioId || loadingYears || availableYears.length === 0}
                className="appearance-none w-full bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm disabled:bg-gray-50 disabled:text-gray-400"
              >
                {loadingYears ? (
                  <option value="">Loading...</option>
                ) : availableYears.length === 0 ? (
                  <option value="">No years available</option>
                ) : (
                  availableYears.map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))
                )}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
            </div>
          </div>
          <div className="flex-1" />
          {/* Analyze Button */}
          <button
            onClick={handleAnalyze}
            disabled={!canAnalyze || analyzing}
            className="flex items-center px-6 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {analyzing ? (
              <>
                <Loader2 size={16} className="mr-2 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Scale size={16} className="mr-2" />
                Analyze
              </>
            )}
          </button>
        </div>
      </div>

      {/* Content Area */}
      {analyzing ? (
        <div className="flex items-center justify-center h-96">
          <Loader2 size={48} className="animate-spin text-fidelity-green" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={handleAnalyze} />
      ) : !analysisResult ? (
        <EmptyState onRefresh={handleRefresh} />
      ) : (
        /* Analysis Results */
        <>
          {/* KPI Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <KPICard
              title="Terminated Employees"
              value={analysisResult.summary.terminated_employee_count.toLocaleString()}
              subtext={`In year ${analysisResult.summary.analysis_year}`}
              icon={Users}
              color="blue"
              loading={loading}
            />
            <KPICard
              title="Current Forfeitures"
              value={formatCurrency(analysisResult.summary.current_total_forfeited)}
              subtext={analysisResult.current_schedule.name}
              icon={DollarSign}
              color="orange"
              loading={loading}
            />
            <KPICard
              title="Proposed Forfeitures"
              value={formatCurrency(analysisResult.summary.proposed_total_forfeited)}
              subtext={analysisResult.proposed_schedule.name}
              icon={DollarSign}
              color="green"
              loading={loading}
            />
            <KPICard
              title="Forfeiture Variance"
              value={formatCurrency(Math.abs(analysisResult.summary.forfeiture_variance))}
              subtext={`${analysisResult.summary.forfeiture_variance >= 0 ? '+' : ''}${analysisResult.summary.forfeiture_variance_pct.toFixed(1)}% change`}
              icon={analysisResult.summary.forfeiture_variance >= 0 ? TrendingUp : TrendingDown}
              color={analysisResult.summary.forfeiture_variance >= 0 ? 'red' : 'green'}
              trend={analysisResult.summary.forfeiture_variance >= 0 ? 'up' : 'down'}
              loading={loading}
            />
          </div>

          {/* Scenario Info Banner */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-blue-900">{analysisResult.scenario_name}</h3>
                <p className="text-sm text-blue-700">
                  Total Employer Contributions: {formatCurrency(analysisResult.summary.total_employer_contributions)}
                </p>
              </div>
              <div className="text-right text-sm text-blue-600">
                <p>Analysis Year: {analysisResult.summary.analysis_year}</p>
              </div>
            </div>
            {/* T016-T019: Hours Requirement Display (FR-006) */}
            {(analysisResult.current_schedule.require_hours_credit ||
              analysisResult.proposed_schedule.require_hours_credit) && (
              <div className="mt-2 pt-2 border-t border-blue-200 text-xs text-blue-600">
                <span className="font-medium">Hours Requirement:</span>
                {analysisResult.current_schedule.require_hours_credit && (
                  <span className="ml-2">
                    Current: {analysisResult.current_schedule.hours_threshold ?? 1000} hrs
                  </span>
                )}
                {analysisResult.proposed_schedule.require_hours_credit && (
                  <span className="ml-2">
                    Proposed: {analysisResult.proposed_schedule.hours_threshold ?? 1000} hrs
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Tenure Band Chart */}
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-semibold text-gray-800 mb-6">Forfeitures by Tenure Band</h3>
            <div className="h-80">
              {tenureBandChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tenureBandChartData} barSize={40}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                    <XAxis dataKey="tenure_band" stroke="#9CA3AF" />
                    <YAxis stroke="#9CA3AF" tickFormatter={(value) => formatCurrency(value)} />
                    <Tooltip
                      cursor={{ fill: '#F3F4F6' }}
                      contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                      formatter={(value: number, name: string) => [formatCurrency(value), name]}
                      labelFormatter={(label) => `Tenure: ${label} years`}
                    />
                    <Legend verticalAlign="top" height={36} />
                    <Bar dataKey="Current Forfeitures" fill={TENURE_COLORS.current} name="Current Schedule" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Proposed Forfeitures" fill={TENURE_COLORS.proposed} name="Proposed Schedule" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-gray-400">
                  <p>No tenure band data available</p>
                </div>
              )}
            </div>
          </div>

          {/* Tenure Band Summary Table */}
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">Tenure Band Summary</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 font-semibold text-gray-600">Tenure Band</th>
                    <th className="text-right py-3 px-4 font-semibold text-gray-600">Employees</th>
                    <th className="text-right py-3 px-4 font-semibold text-gray-600">Contributions</th>
                    <th className="text-right py-3 px-4 font-semibold text-gray-600">Current Forfeitures</th>
                    <th className="text-right py-3 px-4 font-semibold text-gray-600">Proposed Forfeitures</th>
                    <th className="text-right py-3 px-4 font-semibold text-gray-600">Variance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {analysisResult.by_tenure_band.map((band) => (
                    <tr key={band.tenure_band}>
                      <td className="py-3 px-4 text-gray-700 font-medium">{band.tenure_band} years</td>
                      <td className="py-3 px-4 text-right">{band.employee_count.toLocaleString()}</td>
                      <td className="py-3 px-4 text-right">{formatCurrency(band.total_contributions)}</td>
                      <td className="py-3 px-4 text-right">{formatCurrency(band.current_forfeitures)}</td>
                      <td className="py-3 px-4 text-right">{formatCurrency(band.proposed_forfeitures)}</td>
                      <td className={`py-3 px-4 text-right font-medium ${
                        band.forfeiture_variance >= 0 ? 'text-red-600' : 'text-green-600'
                      }`}>
                        {band.forfeiture_variance >= 0 ? '+' : ''}{formatCurrency(band.forfeiture_variance)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-50 font-semibold">
                    <td className="py-3 px-4 text-gray-900">Total</td>
                    <td className="py-3 px-4 text-right">{analysisResult.summary.terminated_employee_count.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right">{formatCurrency(analysisResult.summary.total_employer_contributions)}</td>
                    <td className="py-3 px-4 text-right">{formatCurrency(analysisResult.summary.current_total_forfeited)}</td>
                    <td className="py-3 px-4 text-right">{formatCurrency(analysisResult.summary.proposed_total_forfeited)}</td>
                    <td className={`py-3 px-4 text-right ${
                      analysisResult.summary.forfeiture_variance >= 0 ? 'text-red-600' : 'text-green-600'
                    }`}>
                      {analysisResult.summary.forfeiture_variance >= 0 ? '+' : ''}{formatCurrency(analysisResult.summary.forfeiture_variance)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Employee Details Table (T044-T046) */}
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-800 flex items-center">
                <Table size={20} className="mr-2" />
                Employee Details
              </h3>
              <button
                onClick={() => setShowEmployeeDetails(!showEmployeeDetails)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              >
                {showEmployeeDetails ? 'Hide Details' : `Show Details (${analysisResult.employee_details.length})`}
              </button>
            </div>

            {showEmployeeDetails && (
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th
                        className="text-left py-3 px-4 font-semibold text-gray-600 cursor-pointer hover:bg-gray-50 select-none"
                        onClick={() => handleSort('employee_id')}
                      >
                        <div className="flex items-center gap-1">
                          Employee ID
                          {sortField === 'employee_id' ? (
                            sortDirection === 'asc' ? (
                              <ChevronUp size={14} className="text-fidelity-green" />
                            ) : (
                              <ChevronDown size={14} className="text-fidelity-green" />
                            )
                          ) : (
                            <ChevronDown size={14} className="text-gray-300" />
                          )}
                        </div>
                      </th>
                      <SortHeader field="tenure_years" label="Tenure" />
                      <SortHeader field="total_employer_contributions" label="Contributions" />
                      <SortHeader field="current_vesting_pct" label="Current %" />
                      <SortHeader field="current_forfeiture" label="Current Forf." />
                      <SortHeader field="proposed_vesting_pct" label="Proposed %" />
                      <SortHeader field="proposed_forfeiture" label="Proposed Forf." />
                      <SortHeader field="forfeiture_variance" label="Variance" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {sortedEmployeeDetails.slice(0, 100).map((emp) => (
                      <tr key={emp.employee_id} className="hover:bg-gray-50">
                        <td className="py-3 px-4 text-gray-700 font-mono text-sm">{emp.employee_id}</td>
                        <td className="py-3 px-4 text-right">{emp.tenure_years} yrs</td>
                        <td className="py-3 px-4 text-right">{formatCurrency(emp.total_employer_contributions)}</td>
                        <td className="py-3 px-4 text-right">{(emp.current_vesting_pct * 100).toFixed(1)}%</td>
                        <td className="py-3 px-4 text-right">{formatCurrency(emp.current_forfeiture)}</td>
                        <td className="py-3 px-4 text-right">{(emp.proposed_vesting_pct * 100).toFixed(1)}%</td>
                        <td className="py-3 px-4 text-right">{formatCurrency(emp.proposed_forfeiture)}</td>
                        <td className={`py-3 px-4 text-right font-medium ${
                          emp.forfeiture_variance >= 0 ? 'text-red-600' : 'text-green-600'
                        }`}>
                          {emp.forfeiture_variance >= 0 ? '+' : ''}{formatCurrency(emp.forfeiture_variance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {analysisResult.employee_details.length > 100 && (
                  <p className="text-sm text-gray-500 mt-4 text-center">
                    Showing first 100 of {analysisResult.employee_details.length} employees.
                    Sort by different columns to view other employees.
                  </p>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
