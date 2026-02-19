import React, { useState, useEffect, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Shield, ChevronDown, Loader2, AlertCircle, RefreshCw, CheckCircle,
  XCircle, ChevronRight, Users, DollarSign, Info
} from 'lucide-react';
import {
  listScenarios,
  runACPTest,
  getNDTAvailableYears,
  Scenario,
  ACPTestResponse,
  ACPScenarioResult,
} from '../services/api';
import { MAX_SCENARIO_SELECTION } from '../constants';
import type { LayoutContextType } from './Layout';

const formatPercent = (value: number): string => {
  return `${(value * 100).toFixed(2)}%`;
};

const formatCurrency = (value: number): string => {
  if (value >= 1000000) return `$${(value / 1000000).toFixed(2)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

export default function NDTTesting() {
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  // Selection state
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [comparisonMode, setComparisonMode] = useState(false);

  // Results state
  const [testResponse, setTestResponse] = useState<ACPTestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [loadingYears, setLoadingYears] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Detail state (US2)
  const [showEmployees, setShowEmployees] = useState(false);

  // Fetch scenarios when workspace changes
  useEffect(() => {
    if (activeWorkspace?.id) {
      fetchScenarios(activeWorkspace.id);
    }
  }, [activeWorkspace?.id]);

  // Fetch available years when scenario changes (single mode)
  useEffect(() => {
    if (activeWorkspace?.id && selectedScenarioIds.length === 1) {
      fetchYears(activeWorkspace.id, selectedScenarioIds[0]);
    } else if (selectedScenarioIds.length === 0) {
      setAvailableYears([]);
      setSelectedYear(null);
    }
  }, [activeWorkspace?.id, selectedScenarioIds]);

  // Clear results when selection changes
  useEffect(() => {
    setTestResponse(null);
    setShowEmployees(false);
    setError(null);
  }, [selectedScenarioIds, selectedYear, comparisonMode]);

  const fetchScenarios = async (workspaceId: string) => {
    setLoadingScenarios(true);
    try {
      const data = await listScenarios(workspaceId);
      setScenarios(data);
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const fetchYears = async (workspaceId: string, scenarioId: string) => {
    setLoadingYears(true);
    try {
      const data = await getNDTAvailableYears(workspaceId, scenarioId);
      setAvailableYears(data.years);
      setSelectedYear(data.default_year);
    } catch (err) {
      console.error('Failed to fetch years:', err);
      setAvailableYears([]);
      setSelectedYear(null);
    } finally {
      setLoadingYears(false);
    }
  };

  const handleRunTest = useCallback(async () => {
    if (!activeWorkspace?.id || selectedScenarioIds.length === 0 || !selectedYear) return;

    setLoading(true);
    setError(null);
    setTestResponse(null);

    try {
      const data = await runACPTest(
        activeWorkspace.id,
        selectedScenarioIds,
        selectedYear,
        showEmployees,
      );
      setTestResponse(data);
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to run ACP test');
    } finally {
      setLoading(false);
    }
  }, [activeWorkspace?.id, selectedScenarioIds, selectedYear, showEmployees]);

  const handleToggleEmployees = useCallback(async () => {
    const newVal = !showEmployees;
    setShowEmployees(newVal);

    // Re-fetch with employee details if we have existing results
    if (newVal && testResponse && activeWorkspace?.id && selectedYear) {
      setLoading(true);
      try {
        const data = await runACPTest(
          activeWorkspace.id,
          selectedScenarioIds,
          selectedYear,
          true,
        );
        setTestResponse(data);
      } catch (err: any) {
        setError(err.detail || err.message || 'Failed to load employee details');
      } finally {
        setLoading(false);
      }
    }
  }, [showEmployees, testResponse, activeWorkspace?.id, selectedScenarioIds, selectedYear]);

  const handleScenarioToggle = (scenarioId: string) => {
    if (comparisonMode) {
      if (selectedScenarioIds.includes(scenarioId)) {
        setSelectedScenarioIds(selectedScenarioIds.filter(id => id !== scenarioId));
      } else if (selectedScenarioIds.length < MAX_SCENARIO_SELECTION) {
        setSelectedScenarioIds([...selectedScenarioIds, scenarioId]);
      }
    } else {
      setSelectedScenarioIds([scenarioId]);
    }
  };

  const completedScenarios = scenarios.filter(s => s.status === 'completed');
  const canRun = selectedScenarioIds.length > 0 && selectedYear !== null && !loading;

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center">
            <Shield size={28} className="mr-3 text-fidelity-green" />
            NDT Testing
          </h1>
          <p className="text-gray-500 mt-1">
            Run IRS non-discrimination tests against completed simulations.
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 space-y-4">
        <div className="flex flex-wrap gap-3 items-end">
          {/* Test Type */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Test Type</label>
            <div className="relative">
              <select
                className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[140px]"
                defaultValue="acp"
              >
                <option value="acp">ACP Test</option>
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Scenario Selector (single mode) */}
          {!comparisonMode && (
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Scenario</label>
              <div className="relative">
                <select
                  value={selectedScenarioIds[0] || ''}
                  onChange={(e) => handleScenarioToggle(e.target.value)}
                  disabled={loadingScenarios}
                  className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[200px] disabled:bg-gray-50 disabled:text-gray-400"
                >
                  <option value="">
                    {loadingScenarios ? 'Loading...' : completedScenarios.length === 0 ? 'No completed runs' : 'Select Scenario'}
                  </option>
                  {completedScenarios.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
                <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
              </div>
            </div>
          )}

          {/* Year Selector */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Year</label>
            <div className="relative">
              <select
                value={selectedYear ?? ''}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                disabled={availableYears.length === 0 || loadingYears}
                className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[120px] disabled:bg-gray-50 disabled:text-gray-400"
              >
                <option value="">
                  {loadingYears ? 'Loading...' : availableYears.length === 0 ? 'Select scenario first' : 'Select Year'}
                </option>
                {availableYears.map(y => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Comparison Mode Toggle */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">&nbsp;</label>
            <button
              onClick={() => {
                setComparisonMode(!comparisonMode);
                if (!comparisonMode) {
                  setSelectedScenarioIds([]);
                  setTestResponse(null);
                }
              }}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                comparisonMode
                  ? 'bg-fidelity-green text-white'
                  : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              Compare {comparisonMode && `(${selectedScenarioIds.length}/${MAX_SCENARIO_SELECTION})`}
            </button>
          </div>

          {/* Run Test Button */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">&nbsp;</label>
            <button
              onClick={handleRunTest}
              disabled={!canRun}
              className={`flex items-center px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
                canRun
                  ? 'bg-fidelity-green text-white hover:bg-fidelity-dark'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
              }`}
            >
              {loading ? (
                <Loader2 size={16} className="mr-2 animate-spin" />
              ) : (
                <Shield size={16} className="mr-2" />
              )}
              Run Test
            </button>
          </div>
        </div>

        {/* Comparison Mode Scenario Pills */}
        {comparisonMode && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm font-medium text-blue-900 mb-2">
              Select scenarios to compare (click to select/deselect):
            </p>
            <div className="flex flex-wrap gap-2">
              {completedScenarios.map(scenario => (
                <button
                  key={scenario.id}
                  onClick={() => handleScenarioToggle(scenario.id)}
                  disabled={!selectedScenarioIds.includes(scenario.id) && selectedScenarioIds.length >= MAX_SCENARIO_SELECTION}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    selectedScenarioIds.includes(scenario.id)
                      ? 'bg-fidelity-green text-white'
                      : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed'
                  }`}
                >
                  {scenario.name}
                </button>
              ))}
              {completedScenarios.length === 0 && (
                <p className="text-sm text-gray-500">No completed scenarios available.</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Results Area */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="flex flex-col items-center">
            <Loader2 size={48} className="animate-spin text-fidelity-green mb-3" />
            <p className="text-sm text-gray-500">Running ACP test...</p>
          </div>
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center h-64 text-red-400">
          <AlertCircle size={48} className="mb-4" />
          <h3 className="text-lg font-semibold text-red-600 mb-2">Test Failed</h3>
          <p className="text-sm text-gray-500 mb-4 text-center max-w-md">{error}</p>
          <button
            onClick={handleRunTest}
            className="flex items-center px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
          >
            <RefreshCw size={16} className="mr-2" />
            Retry
          </button>
        </div>
      ) : !testResponse ? (
        <div className="flex flex-col items-center justify-center h-64 text-gray-400">
          <Shield size={48} className="mb-4" />
          <h3 className="text-lg font-semibold text-gray-600 mb-2">No Test Results</h3>
          <p className="text-sm text-gray-500 text-center max-w-md">
            {completedScenarios.length === 0
              ? 'No completed simulations available. Run a simulation first.'
              : 'Select a scenario and year, then click "Run Test" to see ACP results.'}
          </p>
        </div>
      ) : testResponse.results.length === 1 && !comparisonMode ? (
        // Single scenario results
        <SingleScenarioResult
          result={testResponse.results[0]}
          showEmployees={showEmployees}
          onToggleEmployees={handleToggleEmployees}
          loading={loading}
        />
      ) : (
        // Multi-scenario comparison results
        <ComparisonResults results={testResponse.results} />
      )}
    </div>
  );
}

// ==============================================================================
// Single Scenario Result (US1 + US2)
// ==============================================================================

function SingleScenarioResult({
  result,
  showEmployees,
  onToggleEmployees,
  loading,
}: {
  result: ACPScenarioResult;
  showEmployees: boolean;
  onToggleEmployees: () => void;
  loading: boolean;
}) {
  const isPassing = result.test_result === 'pass';
  const isError = result.test_result === 'error';

  if (isError) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6">
        <div className="flex items-center mb-2">
          <AlertCircle size={24} className="text-yellow-600 mr-3" />
          <h3 className="text-lg font-semibold text-yellow-800">Test Error</h3>
        </div>
        <p className="text-sm text-yellow-700">{result.test_message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Pass/Fail Card */}
      <div className={`rounded-xl p-6 border-2 ${
        isPassing ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'
      }`}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            {isPassing ? (
              <CheckCircle size={32} className="text-green-600 mr-3" />
            ) : (
              <XCircle size={32} className="text-red-600 mr-3" />
            )}
            <div>
              <h3 className="text-xl font-bold">
                <span className={isPassing ? 'text-green-800' : 'text-red-800'}>
                  ACP Test: {isPassing ? 'PASS' : 'FAIL'}
                </span>
              </h3>
              <p className={`text-sm ${isPassing ? 'text-green-600' : 'text-red-600'}`}>
                {result.scenario_name} &mdash; Year {result.simulation_year}
              </p>
            </div>
          </div>
          <div className={`text-right px-4 py-2 rounded-lg ${
            isPassing ? 'bg-green-100' : 'bg-red-100'
          }`}>
            <p className="text-xs font-medium text-gray-500">Margin</p>
            <p className={`text-lg font-bold ${isPassing ? 'text-green-700' : 'text-red-700'}`}>
              {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
            </p>
          </div>
        </div>

        {/* Key Metrics Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white/70 rounded-lg p-3">
            <p className="text-xs text-gray-500">HCE Avg ACP</p>
            <p className="text-lg font-bold text-gray-900">{formatPercent(result.hce_average_acp)}</p>
          </div>
          <div className="bg-white/70 rounded-lg p-3">
            <p className="text-xs text-gray-500">NHCE Avg ACP</p>
            <p className="text-lg font-bold text-gray-900">{formatPercent(result.nhce_average_acp)}</p>
          </div>
          <div className="bg-white/70 rounded-lg p-3">
            <p className="text-xs text-gray-500">Applied Threshold</p>
            <p className="text-lg font-bold text-gray-900">{formatPercent(result.applied_threshold)}</p>
          </div>
          <div className="bg-white/70 rounded-lg p-3">
            <p className="text-xs text-gray-500">Test Method</p>
            <p className="text-lg font-bold text-gray-900 capitalize">{result.applied_test}</p>
          </div>
        </div>
      </div>

      {/* Detailed Breakdown (US2) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center">
          <Info size={20} className="mr-2 text-gray-400" />
          Detailed Breakdown
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500 flex items-center"><Users size={12} className="mr-1" /> HCE Count</p>
            <p className="text-xl font-bold text-gray-900">{result.hce_count}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500 flex items-center"><Users size={12} className="mr-1" /> NHCE Count</p>
            <p className="text-xl font-bold text-gray-900">{result.nhce_count}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">Excluded (zero comp)</p>
            <p className="text-xl font-bold text-gray-900">{result.excluded_count}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <p className="text-xs text-gray-500">Eligible Not Enrolled</p>
            <p className="text-xl font-bold text-gray-900">{result.eligible_not_enrolled_count}</p>
          </div>
        </div>

        {/* Threshold Comparison */}
        <div className="bg-gray-50 rounded-lg p-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Basic Test (NHCE x 1.25)</span>
            <span className={`font-medium ${result.applied_test === 'basic' ? 'text-fidelity-green font-bold' : 'text-gray-700'}`}>
              {formatPercent(result.basic_test_threshold)}
              {result.applied_test === 'basic' && ' (applied)'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Alternative Test (min of NHCE x 2, NHCE + 2%)</span>
            <span className={`font-medium ${result.applied_test === 'alternative' ? 'text-fidelity-green font-bold' : 'text-gray-700'}`}>
              {formatPercent(result.alternative_test_threshold)}
              {result.applied_test === 'alternative' && ' (applied)'}
            </span>
          </div>
          <div className="border-t border-gray-200 pt-2 mt-2 flex justify-between text-sm">
            <span className="text-gray-600">HCE Compensation Threshold</span>
            <span className="font-medium text-gray-700">{formatCurrency(result.hce_threshold_used)}</span>
          </div>
        </div>
      </div>

      {/* Employee Detail Table (US2) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <button
          onClick={onToggleEmployees}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors rounded-xl"
        >
          <span className="text-sm font-semibold text-gray-800 flex items-center">
            <ChevronRight size={18} className={`mr-2 transition-transform ${showEmployees ? 'rotate-90' : ''}`} />
            Employee Details ({result.hce_count + result.nhce_count} employees)
          </span>
          {loading && <Loader2 size={16} className="animate-spin text-gray-400" />}
        </button>

        {showEmployees && result.employees && (
          <div className="px-6 pb-6 overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Employee ID</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Classification</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Enrolled</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Match Amount</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Eligible Comp</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">ACP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {result.employees.map((emp) => (
                  <tr key={emp.employee_id} className="hover:bg-gray-50">
                    <td className="py-2 px-3 text-sm text-gray-900 font-mono">{emp.employee_id}</td>
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        emp.is_hce
                          ? 'bg-purple-100 text-purple-800'
                          : 'bg-blue-100 text-blue-800'
                      }`}>
                        {emp.is_hce ? 'HCE' : 'NHCE'}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        emp.is_enrolled
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-600'
                      }`}>
                        {emp.is_enrolled ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-sm text-right text-gray-700">{formatCurrency(emp.employer_match_amount)}</td>
                    <td className="py-2 px-3 text-sm text-right text-gray-700">{formatCurrency(emp.eligible_compensation)}</td>
                    <td className="py-2 px-3 text-sm text-right font-medium text-gray-900">{formatPercent(emp.individual_acp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ==============================================================================
// Multi-Scenario Comparison Results (US3)
// ==============================================================================

function ComparisonResults({ results }: { results: ACPScenarioResult[] }) {
  return (
    <div className="space-y-6">
      {/* Comparison Grid */}
      <div className={`grid gap-6 ${
        results.length === 2 ? 'grid-cols-1 md:grid-cols-2' :
        results.length === 3 ? 'grid-cols-1 md:grid-cols-3' :
        'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
      }`}>
        {results.map((result) => {
          const isPassing = result.test_result === 'pass';
          const isError = result.test_result === 'error';

          return (
            <div
              key={result.scenario_id}
              className={`rounded-xl p-5 border-2 ${
                isError
                  ? 'bg-yellow-50 border-yellow-300'
                  : isPassing
                  ? 'bg-green-50 border-green-300'
                  : 'bg-red-50 border-red-300'
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-gray-800 truncate mr-2">{result.scenario_name}</h3>
                {isError ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-yellow-200 text-yellow-800">
                    ERROR
                  </span>
                ) : isPassing ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-green-200 text-green-800 flex items-center">
                    <CheckCircle size={12} className="mr-1" /> PASS
                  </span>
                ) : (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-red-200 text-red-800 flex items-center">
                    <XCircle size={12} className="mr-1" /> FAIL
                  </span>
                )}
              </div>

              {isError ? (
                <p className="text-xs text-yellow-700">{result.test_message}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">HCE Avg ACP</span>
                    <span className="font-medium text-gray-900">{formatPercent(result.hce_average_acp)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">NHCE Avg ACP</span>
                    <span className="font-medium text-gray-900">{formatPercent(result.nhce_average_acp)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Threshold</span>
                    <span className="font-medium text-gray-900">{formatPercent(result.applied_threshold)}</span>
                  </div>
                  <div className={`flex justify-between text-sm border-t pt-2 ${
                    isPassing ? 'border-green-200' : 'border-red-200'
                  }`}>
                    <span className="text-gray-600">Margin</span>
                    <span className={`font-bold ${isPassing ? 'text-green-700' : 'text-red-700'}`}>
                      {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-gray-500 pt-1">
                    <span>HCE: {result.hce_count} | NHCE: {result.nhce_count}</span>
                    <span className="capitalize">{result.applied_test} test</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
