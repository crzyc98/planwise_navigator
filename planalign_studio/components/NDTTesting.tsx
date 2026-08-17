import React, { useState, useEffect, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Shield, ChevronDown, Loader2, AlertCircle, RefreshCw, CheckCircle,
  XCircle, ChevronRight, Users, DollarSign, Info, AlertTriangle,
  ArrowUp, ArrowDown, CheckSquare, Square
} from 'lucide-react';
import {
  listScenarios,
  runACPTest,
  run401a4Test,
  run415Test,
  runADPTest,
  getNDTAvailableYears,
  Scenario,
  ACPTestResponse,
  ACPScenarioResult,
  Section401a4TestResponse,
  Section401a4ScenarioResult,
  Section415TestResponse,
  Section415ScenarioResult,
  ADPTestResponse,
  ADPScenarioResult,
} from '../services/api';
import { MAX_SCENARIO_SELECTION } from '../constants';
import type { LayoutContextType } from './Layout';

type TestType = 'acp' | '401a4' | '415' | 'adp';
type AnyTestResponse = ACPTestResponse | Section401a4TestResponse | Section415TestResponse | ADPTestResponse;

const formatPercent = (value: number): string => {
  return `${(value * 100).toFixed(2)}%`;
};

const formatCurrency = (value: number): string => {
  if (value >= 1000000) return `$${(value / 1000000).toFixed(2)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

const getGridColsClass = (count: number): string => {
  if (count === 2) return 'grid-cols-1 md:grid-cols-2';
  if (count === 3) return 'grid-cols-1 md:grid-cols-3';
  return 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3';
};

const TEST_TYPE_LABELS: Record<TestType, string> = {
  acp: 'ACP Test',
  adp: 'ADP Test',
  '401a4': '401(a)(4) General Test',
  '415': '415 Annual Additions',
};

export default function NDTTesting() {
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  // Selection state
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [comparisonMode, setComparisonMode] = useState(false);
  const [testType, setTestType] = useState<TestType>('acp');

  // Test-specific options
  const [includeMatch, setIncludeMatch] = useState(false);
  const [warningThreshold, setWarningThreshold] = useState(0.95);
  const [safeHarbor, setSafeHarbor] = useState(false);
  const [testingMethod, setTestingMethod] = useState<'current' | 'prior'>('current');

  // Results state
  const [testResponse, setTestResponse] = useState<AnyTestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [loadingYears, setLoadingYears] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Detail state
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
  }, [selectedScenarioIds, selectedYear, comparisonMode, testType]);

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
      let data: AnyTestResponse;
      if (testType === 'acp') {
        data = await runACPTest(
          activeWorkspace.id, selectedScenarioIds, selectedYear, showEmployees,
        );
      } else if (testType === 'adp') {
        data = await runADPTest(
          activeWorkspace.id, selectedScenarioIds, selectedYear, showEmployees, safeHarbor, testingMethod,
        );
      } else if (testType === '401a4') {
        data = await run401a4Test(
          activeWorkspace.id, selectedScenarioIds, selectedYear, showEmployees, includeMatch,
        );
      } else {
        data = await run415Test(
          activeWorkspace.id, selectedScenarioIds, selectedYear, showEmployees, warningThreshold,
        );
      }
      setTestResponse(data);
    } catch (err: any) {
      setError(err.detail || err.message || `Failed to run ${TEST_TYPE_LABELS[testType]}`);
    } finally {
      setLoading(false);
    }
  }, [activeWorkspace?.id, selectedScenarioIds, selectedYear, showEmployees, testType, includeMatch, warningThreshold, safeHarbor, testingMethod]);

  const handleToggleEmployees = useCallback(async () => {
    const newVal = !showEmployees;
    setShowEmployees(newVal);

    if (newVal && testResponse && activeWorkspace?.id && selectedYear) {
      setLoading(true);
      try {
        let data: AnyTestResponse;
        if (testType === 'acp') {
          data = await runACPTest(activeWorkspace.id, selectedScenarioIds, selectedYear, true);
        } else if (testType === 'adp') {
          data = await runADPTest(activeWorkspace.id, selectedScenarioIds, selectedYear, true, safeHarbor, testingMethod);
        } else if (testType === '401a4') {
          data = await run401a4Test(activeWorkspace.id, selectedScenarioIds, selectedYear, true, includeMatch);
        } else {
          data = await run415Test(activeWorkspace.id, selectedScenarioIds, selectedYear, true, warningThreshold);
        }
        setTestResponse(data);
      } catch (err: any) {
        setError(err.detail || err.message || 'Failed to load employee details');
      } finally {
        setLoading(false);
      }
    }
  }, [showEmployees, testResponse, activeWorkspace?.id, selectedScenarioIds, selectedYear, testType, includeMatch, warningThreshold, safeHarbor, testingMethod]);

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

  const moveScenarioUp = useCallback((id: string) => {
    setSelectedScenarioIds(prev => {
      const idx = prev.indexOf(id);
      if (idx <= 0) return prev;
      const newArr = [...prev];
      [newArr[idx - 1], newArr[idx]] = [newArr[idx], newArr[idx - 1]];
      return newArr;
    });
  }, []);

  const moveScenarioDown = useCallback((id: string) => {
    setSelectedScenarioIds(prev => {
      const idx = prev.indexOf(id);
      if (idx < 0 || idx >= prev.length - 1) return prev;
      const newArr = [...prev];
      [newArr[idx], newArr[idx + 1]] = [newArr[idx + 1], newArr[idx]];
      return newArr;
    });
  }, []);

  const completedScenarios = scenarios.filter(s => s.status === 'completed');
  const canRun = selectedScenarioIds.length > 0 && selectedYear !== null && !loading;
  const scenarioPlaceholder = completedScenarios.length === 0 ? 'No completed runs' : 'Select Scenario';
  const yearPlaceholder = availableYears.length === 0 ? 'Select scenario first' : 'Select Year';

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink flex items-center">
            <Shield size={28} className="mr-3 text-fidelity-green" />
            NDT Testing
          </h1>
          <p className="text-ink-muted mt-1">
            Run IRS non-discrimination tests against completed simulations.
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border space-y-4">
        <div className="flex flex-wrap gap-3 items-end">
          {/* Test Type */}
          <div>
            <label htmlFor="ndt-test-type" className="block text-xs font-medium text-ink-muted mb-1">Test Type</label>
            <div className="relative">
              <select
                id="ndt-test-type"
                className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[200px]"
                value={testType}
                onChange={(e) => { setTestType(e.target.value as TestType); setTestResponse(null); setError(null); }}
              >
                <option value="acp">ACP Test</option>
                <option value="adp">ADP Test</option>
                <option value="401a4">401(a)(4) General Test</option>
                <option value="415">415 Annual Additions</option>
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
            </div>
          </div>

          {/* Scenario Selector (single mode) */}
          {!comparisonMode && (
            <div>
              <label htmlFor="ndt-scenario" className="block text-xs font-medium text-ink-muted mb-1">Scenario</label>
              <div className="relative">
                <select
                  id="ndt-scenario"
                  value={selectedScenarioIds[0] || ''}
                  onChange={(e) => handleScenarioToggle(e.target.value)}
                  disabled={loadingScenarios}
                  className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[200px] disabled:bg-surface-subtle disabled:text-ink-subtle"
                >
                  <option value="">
                    {loadingScenarios ? 'Loading...' : scenarioPlaceholder}
                  </option>
                  {completedScenarios.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
                <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
              </div>
            </div>
          )}

          {/* Year Selector */}
          <div>
            <label htmlFor="ndt-year" className="block text-xs font-medium text-ink-muted mb-1">Year</label>
            <div className="relative">
              <select
                id="ndt-year"
                value={selectedYear ?? ''}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                disabled={availableYears.length === 0 || loadingYears}
                className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[120px] disabled:bg-surface-subtle disabled:text-ink-subtle"
              >
                <option value="">
                  {loadingYears ? 'Loading...' : yearPlaceholder}
                </option>
                {availableYears.map(y => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
            </div>
          </div>

          {/* 401(a)(4) specific: Include Match toggle */}
          {testType === '401a4' && (
            <div>
              <span className="block text-xs font-medium text-ink-muted mb-1">&nbsp;</span>
              <label htmlFor="ndt-include-match" className="flex items-center px-3 py-2 bg-surface-raised border border-border-strong rounded-lg cursor-pointer hover:bg-surface-subtle">
                <input
                  id="ndt-include-match"
                  type="checkbox"
                  checked={includeMatch}
                  onChange={(e) => setIncludeMatch(e.target.checked)}
                  className="mr-2 rounded border-border-strong text-fidelity-green focus:ring-fidelity-green"
                />
                <span className="text-sm text-ink-muted">Include Match</span>
              </label>
            </div>
          )}

          {/* 415 specific: Warning Threshold */}
          {testType === '415' && (
            <div>
              <label htmlFor="ndt-warning-threshold" className="block text-xs font-medium text-ink-muted mb-1">Warning Threshold</label>
              <div className="relative">
                <select
                  id="ndt-warning-threshold"
                  value={warningThreshold}
                  onChange={(e) => setWarningThreshold(Number(e.target.value))}
                  className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[100px]"
                >
                  <option value={0.90}>90%</option>
                  <option value={0.95}>95%</option>
                  <option value={1.0}>100%</option>
                </select>
                <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
              </div>
            </div>
          )}

          {/* ADP specific: Safe Harbor toggle */}
          {testType === 'adp' && (
            <div>
              <span className="block text-xs font-medium text-ink-muted mb-1">&nbsp;</span>
              <label htmlFor="ndt-safe-harbor" className="flex items-center px-3 py-2 bg-surface-raised border border-border-strong rounded-lg cursor-pointer hover:bg-surface-subtle">
                <input
                  id="ndt-safe-harbor"
                  type="checkbox"
                  checked={safeHarbor}
                  onChange={(e) => setSafeHarbor(e.target.checked)}
                  className="mr-2 rounded border-border-strong text-fidelity-green focus:ring-fidelity-green"
                />
                <span className="text-sm text-ink-muted">Safe Harbor</span>
              </label>
            </div>
          )}

          {/* ADP specific: Testing Method selector */}
          {testType === 'adp' && (
            <div>
              <label htmlFor="ndt-testing-method" className="block text-xs font-medium text-ink-muted mb-1">Testing Method</label>
              <div className="relative">
                <select
                  id="ndt-testing-method"
                  value={testingMethod}
                  onChange={(e) => setTestingMethod(e.target.value as 'current' | 'prior')}
                  className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[140px]"
                >
                  <option value="current">Current Year</option>
                  <option value="prior">Prior Year</option>
                </select>
                <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
              </div>
            </div>
          )}

          {/* Comparison Mode Toggle */}
          <div>
            <span className="block text-xs font-medium text-ink-muted mb-1">&nbsp;</span>
            <button
              onClick={() => {
                setComparisonMode(!comparisonMode);
                if (!comparisonMode) {
                  setSelectedScenarioIds([]);
                  setTestResponse(null);
                }
              }}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${comparisonMode ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised border border-border-strong text-ink-muted hover:bg-surface-subtle'}`}
            >
              Compare {comparisonMode && `(${selectedScenarioIds.length}/${MAX_SCENARIO_SELECTION})`}
            </button>
          </div>

          {/* Run Test Button */}
          <div>
            <span className="block text-xs font-medium text-ink-muted mb-1">&nbsp;</span>
            <button
              onClick={handleRunTest}
              disabled={!canRun}
              className={`flex items-center px-5 py-2 rounded-lg text-sm font-medium transition-colors ${canRun ? 'bg-fidelity-green text-ink-inverse hover:bg-fidelity-dark' : 'bg-surface-disabled text-ink-subtle cursor-not-allowed'}`}
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

        {/* Comparison Mode Scenario List */}
        {comparisonMode && (
          <div className="bg-info-surface border border-info-border rounded-lg p-4 space-y-2">
            {/* Selected scenarios with reorder controls */}
            {selectedScenarioIds.length > 0 && (
              <>
                <div className="text-[10px] font-bold text-ink-subtle uppercase tracking-widest">
                  Selected ({selectedScenarioIds.length})
                </div>
                {selectedScenarioIds.map((id, index) => {
                  const scenario = completedScenarios.find(s => s.id === id);
                  if (!scenario) return null;
                  const canMoveUp = index > 0;
                  const canMoveDown = index < selectedScenarioIds.length - 1;

                  return (
                    <div
                      key={id}
                      className="group w-full text-left px-3 py-2 rounded-lg flex items-center justify-between transition-all border bg-fidelity-green/5 border-fidelity-green/20"
                    >
                      <button
                        onClick={() => handleScenarioToggle(id)}
                        className="flex items-center flex-1 min-w-0"
                      >
                        <CheckSquare size={16} className="text-fidelity-green mr-3 flex-shrink-0" />
                        <span className="text-xs font-semibold text-fidelity-green truncate">
                          {scenario.name}
                        </span>
                      </button>
                      {selectedScenarioIds.length > 1 && (
                        <div className="flex flex-col ml-2">
                          <button
                            onClick={() => moveScenarioUp(id)}
                            disabled={!canMoveUp}
                            className="p-0.5 rounded text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            title="Move up"
                          >
                            <ArrowUp size={12} />
                          </button>
                          <button
                            onClick={() => moveScenarioDown(id)}
                            disabled={!canMoveDown}
                            className="p-0.5 rounded text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            title="Move down"
                          >
                            <ArrowDown size={12} />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </>
            )}

            {/* Unselected scenarios */}
            {completedScenarios.filter(s => !selectedScenarioIds.includes(s.id)).length > 0 && (
              <>
                <div className="text-[10px] font-bold text-ink-subtle uppercase tracking-widest mt-2">
                  Available
                </div>
                {completedScenarios.filter(s => !selectedScenarioIds.includes(s.id)).map(scenario => {
                  const isAtLimit = selectedScenarioIds.length >= MAX_SCENARIO_SELECTION;
                  return (
                    <div
                      key={scenario.id}
                      className={`w-full text-left px-3 py-2 rounded-lg flex items-center transition-all border ${isAtLimit ? 'bg-surface-subtle border-transparent opacity-50 cursor-not-allowed' : 'hover:bg-surface-subtle border-transparent'}`}
                    >
                      <button
                        onClick={() => !isAtLimit && handleScenarioToggle(scenario.id)}
                        disabled={isAtLimit}
                        className="flex items-center flex-1 min-w-0"
                      >
                        <Square size={16} className="text-ink-subtle mr-3 flex-shrink-0" />
                        <span className="text-xs font-medium text-ink-muted truncate">
                          {scenario.name}
                        </span>
                      </button>
                    </div>
                  );
                })}
              </>
            )}

            {completedScenarios.length === 0 && (
              <p className="text-sm text-ink-muted">No completed scenarios available.</p>
            )}
          </div>
        )}
      </div>

      {/* Results Area */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="flex flex-col items-center">
            <Loader2 size={48} className="animate-spin text-fidelity-green mb-3" />
            <p className="text-sm text-ink-muted">Running {TEST_TYPE_LABELS[testType]}...</p>
          </div>
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center h-64 text-danger-ink">
          <AlertCircle size={48} className="mb-4" />
          <h3 className="text-lg font-semibold text-danger-ink mb-2">Test Failed</h3>
          <p className="text-sm text-ink-muted mb-4 text-center max-w-md">{error}</p>
          <button
            onClick={handleRunTest}
            className="flex items-center px-4 py-2 bg-danger-solid text-ink-inverse rounded-lg text-sm font-medium hover:bg-danger-solid-hover transition-colors"
          >
            <RefreshCw size={16} className="mr-2" />
            Retry
          </button>
        </div>
      ) : !testResponse ? (
        <div className="flex flex-col items-center justify-center h-64 text-ink-subtle">
          <Shield size={48} className="mb-4" />
          <h3 className="text-lg font-semibold text-ink-muted mb-2">No Test Results</h3>
          <p className="text-sm text-ink-muted text-center max-w-md">
            {completedScenarios.length === 0
              ? 'No completed simulations available. Run a simulation first.'
              : `Select a scenario and year, then click "Run Test" to see ${TEST_TYPE_LABELS[testType]} results.`}
          </p>
        </div>
      ) : testType === 'adp' ? (
        // ADP results
        testResponse.results.length === 1 && !comparisonMode ? (
          <ADPSingleResult
            result={(testResponse as ADPTestResponse).results[0]}
            showEmployees={showEmployees}
            onToggleEmployees={handleToggleEmployees}
            loading={loading}
          />
        ) : (
          <ADPComparisonResults results={(testResponse as ADPTestResponse).results} scenarioOrder={selectedScenarioIds} />
        )
      ) : testType === 'acp' ? (
        // ACP results
        testResponse.results.length === 1 && !comparisonMode ? (
          <ACPSingleResult
            result={(testResponse as ACPTestResponse).results[0]}
            showEmployees={showEmployees}
            onToggleEmployees={handleToggleEmployees}
            loading={loading}
          />
        ) : (
          <ACPComparisonResults results={(testResponse as ACPTestResponse).results} scenarioOrder={selectedScenarioIds} />
        )
      ) : testType === '401a4' ? (
        // 401(a)(4) results
        testResponse.results.length === 1 && !comparisonMode ? (
          <Section401a4SingleResult
            result={(testResponse as Section401a4TestResponse).results[0]}
            showEmployees={showEmployees}
            onToggleEmployees={handleToggleEmployees}
            loading={loading}
          />
        ) : (
          <Section401a4ComparisonResults results={(testResponse as Section401a4TestResponse).results} scenarioOrder={selectedScenarioIds} />
        )
      ) : (
        // 415 results
        testResponse.results.length === 1 && !comparisonMode ? (
          <Section415SingleResult
            result={(testResponse as Section415TestResponse).results[0]}
            showEmployees={showEmployees}
            onToggleEmployees={handleToggleEmployees}
            loading={loading}
          />
        ) : (
          <Section415ComparisonResults results={(testResponse as Section415TestResponse).results} scenarioOrder={selectedScenarioIds} />
        )
      )}
    </div>
  );
}

// ==============================================================================
// ACP Single Scenario Result
// ==============================================================================

function ACPSingleResult({
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
      <div className="bg-warning-surface border border-warning-border rounded-xl p-6">
        <div className="flex items-center mb-2">
          <AlertCircle size={24} className="text-warning-ink mr-3" />
          <h3 className="text-lg font-semibold text-warning-ink">Test Error</h3>
        </div>
        <p className="text-sm text-warning-ink">{result.test_message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className={`rounded-xl p-6 border-2 ${isPassing ? 'bg-success-surface border-success-border' : 'bg-danger-surface border-danger-border'}`}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            {isPassing ? (
              <CheckCircle size={32} className="text-success-ink mr-3" />
            ) : (
              <XCircle size={32} className="text-danger-ink mr-3" />
            )}
            <div>
              <h3 className="text-xl font-bold">
                <span className={isPassing ? 'text-success-ink' : 'text-danger-ink'}>
                  ACP Test: {isPassing ? 'PASS' : 'FAIL'}
                </span>
              </h3>
              <p className={`text-sm ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
                {result.scenario_name} &mdash; Year {result.simulation_year}
              </p>
            </div>
          </div>
          <div className={`text-right px-4 py-2 rounded-lg ${isPassing ? 'bg-success-surface' : 'bg-danger-surface'}`}>
            <p className="text-xs font-medium text-ink-muted">Margin</p>
            <p className={`text-lg font-bold ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
              {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">HCE Avg ACP</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.hce_average_acp)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">NHCE Avg ACP</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.nhce_average_acp)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Applied Threshold</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.applied_threshold)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Test Method</p>
            <p className="text-lg font-bold text-ink capitalize">{result.applied_test}</p>
          </div>
        </div>
      </div>

      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <h3 className="text-lg font-semibold text-ink mb-4 flex items-center">
          <Info size={20} className="mr-2 text-ink-subtle" />
          Detailed Breakdown
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted flex items-center"><Users size={12} className="mr-1" /> HCE Count</p>
            <p className="text-xl font-bold text-ink">{result.hce_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted flex items-center"><Users size={12} className="mr-1" /> NHCE Count</p>
            <p className="text-xl font-bold text-ink">{result.nhce_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted">Excluded (zero comp)</p>
            <p className="text-xl font-bold text-ink">{result.excluded_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted">Eligible Not Enrolled</p>
            <p className="text-xl font-bold text-ink">{result.eligible_not_enrolled_count}</p>
          </div>
        </div>
        <div className="bg-surface-subtle rounded-lg p-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Basic Test (NHCE x 1.25)</span>
            <span className={`font-medium ${result.applied_test === 'basic' ? 'text-fidelity-green font-bold' : 'text-ink-muted'}`}>
              {formatPercent(result.basic_test_threshold)}
              {result.applied_test === 'basic' && ' (applied)'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Alternative Test (min of NHCE x 2, NHCE + 2%)</span>
            <span className={`font-medium ${result.applied_test === 'alternative' ? 'text-fidelity-green font-bold' : 'text-ink-muted'}`}>
              {formatPercent(result.alternative_test_threshold)}
              {result.applied_test === 'alternative' && ' (applied)'}
            </span>
          </div>
          <div className="border-t border-border pt-2 mt-2 flex justify-between text-sm">
            <span className="text-ink-muted">HCE Compensation Threshold</span>
            <span className="font-medium text-ink-muted">{formatCurrency(result.hce_threshold_used)}</span>
          </div>
        </div>
      </div>

      {/* Employee Detail Table */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border">
        <button
          onClick={onToggleEmployees}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-surface-subtle transition-colors rounded-xl"
        >
          <span className="text-sm font-semibold text-ink flex items-center">
            <ChevronRight size={18} className={`mr-2 transition-transform ${showEmployees ? 'rotate-90' : ''}`} />
            Employee Details ({result.hce_count + result.nhce_count} employees)
          </span>
          {loading && <Loader2 size={16} className="animate-spin text-ink-subtle" />}
        </button>
        {showEmployees && result.employees && (
          <div className="px-6 pb-6 overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Employee ID</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Classification</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Enrolled</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Match Amount</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Eligible Comp</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">ACP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.employees.map((emp) => (
                  <tr key={emp.employee_id} className="hover:bg-surface-subtle">
                    <td className="py-2 px-3 text-sm text-ink font-mono">{emp.employee_id}</td>
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${emp.is_hce ? 'bg-info-surface text-info-ink' : 'bg-info-surface text-info-ink'}`}>
                        {emp.is_hce ? 'HCE' : 'NHCE'}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${emp.is_enrolled ? 'bg-success-surface text-success-ink' : 'bg-surface-subtle text-ink-muted'}`}>
                        {emp.is_enrolled ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.employer_match_amount)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.eligible_compensation)}</td>
                    <td className="py-2 px-3 text-sm text-right font-medium text-ink">{formatPercent(emp.individual_acp)}</td>
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
// ACP Comparison Results
// ==============================================================================

function ACPComparisonResults({ results, scenarioOrder }: { results: ACPScenarioResult[]; scenarioOrder: string[] }) {
  const ordered = [...results].sort((a, b) => scenarioOrder.indexOf(a.scenario_id) - scenarioOrder.indexOf(b.scenario_id));
  return (
    <div className="space-y-6">
      <div className={`grid gap-6 ${getGridColsClass(ordered.length)}`}>
        {ordered.map((result) => {
          const isPassing = result.test_result === 'pass';
          const isError = result.test_result === 'error';
          const cardClass = isPassing ? 'bg-success-surface border-success-border' : 'bg-danger-surface border-danger-border';
          return (
            <div key={result.scenario_id} className={`rounded-xl p-5 border-2 ${isError ? 'bg-warning-surface border-warning-border' : cardClass}`}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-ink truncate mr-2">{result.scenario_name}</h3>
                {isError ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-warning-surface text-warning-ink">ERROR</span>
                ) : isPassing ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-success-surface text-success-ink flex items-center">
                    <CheckCircle size={12} className="mr-1" /> PASS
                  </span>
                ) : (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-danger-surface text-danger-ink flex items-center">
                    <XCircle size={12} className="mr-1" /> FAIL
                  </span>
                )}
              </div>
              {isError ? (
                <p className="text-xs text-warning-ink">{result.test_message}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">HCE Avg ACP</span>
                    <span className="font-medium text-ink">{formatPercent(result.hce_average_acp)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">NHCE Avg ACP</span>
                    <span className="font-medium text-ink">{formatPercent(result.nhce_average_acp)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">Threshold</span>
                    <span className="font-medium text-ink">{formatPercent(result.applied_threshold)}</span>
                  </div>
                  <div className={`flex justify-between text-sm border-t pt-2 ${isPassing ? 'border-success-border' : 'border-danger-border'}`}>
                    <span className="text-ink-muted">Margin</span>
                    <span className={`font-bold ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
                      {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-ink-muted pt-1">
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

// ==============================================================================
// 401(a)(4) Single Scenario Result
// ==============================================================================

function Section401a4SingleResult({
  result,
  showEmployees,
  onToggleEmployees,
  loading,
}: {
  result: Section401a4ScenarioResult;
  showEmployees: boolean;
  onToggleEmployees: () => void;
  loading: boolean;
}) {
  const isPassing = result.test_result === 'pass';
  const isError = result.test_result === 'error';

  if (isError) {
    return (
      <div className="bg-warning-surface border border-warning-border rounded-xl p-6">
        <div className="flex items-center mb-2">
          <AlertCircle size={24} className="text-warning-ink mr-3" />
          <h3 className="text-lg font-semibold text-warning-ink">Test Error</h3>
        </div>
        <p className="text-sm text-warning-ink">{result.test_message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Pass/Fail Card */}
      <div className={`rounded-xl p-6 border-2 ${isPassing ? 'bg-success-surface border-success-border' : 'bg-danger-surface border-danger-border'}`}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            {isPassing ? (
              <CheckCircle size={32} className="text-success-ink mr-3" />
            ) : (
              <XCircle size={32} className="text-danger-ink mr-3" />
            )}
            <div>
              <h3 className="text-xl font-bold">
                <span className={isPassing ? 'text-success-ink' : 'text-danger-ink'}>
                  401(a)(4) Test: {isPassing ? 'PASS' : 'FAIL'}
                </span>
              </h3>
              <p className={`text-sm ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
                {result.scenario_name} &mdash; Year {result.simulation_year}
                <span className="ml-2 text-xs opacity-75">
                  ({result.applied_test === 'ratio' ? 'Ratio Test' : 'General Test'})
                </span>
              </p>
            </div>
          </div>
          <div className={`text-right px-4 py-2 rounded-lg ${isPassing ? 'bg-success-surface' : 'bg-danger-surface'}`}>
            <p className="text-xs font-medium text-ink-muted">Margin</p>
            <p className={`text-lg font-bold ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
              {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">HCE Avg Rate</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.hce_average_rate)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">NHCE Avg Rate</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.nhce_average_rate)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Ratio (NHCE/HCE)</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.ratio)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Applied Test</p>
            <p className="text-lg font-bold text-ink capitalize">{result.applied_test}</p>
          </div>
        </div>
      </div>

      {/* Nondiscrimination review caveat */}
      {result.service_risk_flag && (
        <div className="bg-warning-surface border border-warning-border rounded-xl p-4 flex items-start">
          <AlertTriangle size={20} className="text-warning-ink mr-3 mt-0.5 flex-shrink-0" />
          <div>
            <h4 className="text-sm font-semibold text-warning-ink">Nondiscrimination Review Required</h4>
            <p className="text-sm text-warning-ink mt-1">
              The employer core contribution design may require further nondiscrimination review.
              This result is not a legal qualification conclusion. {result.service_risk_detail}
            </p>
          </div>
        </div>
      )}

      {/* Detailed Breakdown */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <h3 className="text-lg font-semibold text-ink mb-4 flex items-center">
          <Info size={20} className="mr-2 text-ink-subtle" />
          Detailed Breakdown
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted flex items-center"><Users size={12} className="mr-1" /> HCE Count</p>
            <p className="text-xl font-bold text-ink">{result.hce_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted flex items-center"><Users size={12} className="mr-1" /> NHCE Count</p>
            <p className="text-xl font-bold text-ink">{result.nhce_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted">Excluded</p>
            <p className="text-xl font-bold text-ink">{result.excluded_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted">Include Match</p>
            <p className="text-xl font-bold text-ink">{result.include_match ? 'Yes' : 'No'}</p>
          </div>
        </div>
        <div className="bg-surface-subtle rounded-lg p-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Ratio Test (NHCE avg / HCE avg &gt;= 70%)</span>
            <span className={`font-medium ${result.ratio >= 0.70 ? 'text-success-ink' : 'text-danger-ink'}`}>
              {formatPercent(result.ratio)} {result.ratio >= 0.70 ? 'PASS' : 'FAIL'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">General Test (NHCE median / HCE median &gt;= 70%)</span>
            <span className="font-medium text-ink-muted">
              {result.hce_median_rate > 0
                ? `${formatPercent(result.nhce_median_rate / result.hce_median_rate)}`
                : 'N/A'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">HCE Median Rate</span>
            <span className="font-medium text-ink-muted">{formatPercent(result.hce_median_rate)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">NHCE Median Rate</span>
            <span className="font-medium text-ink-muted">{formatPercent(result.nhce_median_rate)}</span>
          </div>
          <div className="border-t border-border pt-2 mt-2 flex justify-between text-sm">
            <span className="text-ink-muted">HCE Compensation Threshold</span>
            <span className="font-medium text-ink-muted">{formatCurrency(result.hce_threshold_used)}</span>
          </div>
        </div>
      </div>

      {/* Employee Detail Table */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border">
        <button
          onClick={onToggleEmployees}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-surface-subtle transition-colors rounded-xl"
        >
          <span className="text-sm font-semibold text-ink flex items-center">
            <ChevronRight size={18} className={`mr-2 transition-transform ${showEmployees ? 'rotate-90' : ''}`} />
            Employee Details ({result.hce_count + result.nhce_count} employees)
          </span>
          {loading && <Loader2 size={16} className="animate-spin text-ink-subtle" />}
        </button>
        {showEmployees && result.employees && (
          <div className="px-6 pb-6 overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Employee ID</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Classification</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">NEC Amount</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Match Amount</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Total Employer</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Plan Comp</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Rate</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Yrs of Svc</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.employees.map((emp) => (
                  <tr key={emp.employee_id} className="hover:bg-surface-subtle">
                    <td className="py-2 px-3 text-sm text-ink font-mono">{emp.employee_id}</td>
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${emp.is_hce ? 'bg-info-surface text-info-ink' : 'bg-info-surface text-info-ink'}`}>
                        {emp.is_hce ? 'HCE' : 'NHCE'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.employer_nec_amount)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.employer_match_amount)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.total_employer_amount)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.plan_compensation)}</td>
                    <td className="py-2 px-3 text-sm text-right font-medium text-ink">{formatPercent(emp.contribution_rate)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{emp.years_of_service.toFixed(1)}</td>
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
// 401(a)(4) Comparison Results
// ==============================================================================

function Section401a4ComparisonResults({ results, scenarioOrder }: { results: Section401a4ScenarioResult[]; scenarioOrder: string[] }) {
  const ordered = [...results].sort((a, b) => scenarioOrder.indexOf(a.scenario_id) - scenarioOrder.indexOf(b.scenario_id));
  return (
    <div className="space-y-6">
      <div className={`grid gap-6 ${getGridColsClass(ordered.length)}`}>
        {ordered.map((result) => {
          const isPassing = result.test_result === 'pass';
          const isError = result.test_result === 'error';
          const cardClass = isPassing ? 'bg-success-surface border-success-border' : 'bg-danger-surface border-danger-border';
          return (
            <div key={result.scenario_id} className={`rounded-xl p-5 border-2 ${isError ? 'bg-warning-surface border-warning-border' : cardClass}`}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-ink truncate mr-2">{result.scenario_name}</h3>
                {isError ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-warning-surface text-warning-ink">ERROR</span>
                ) : isPassing ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-success-surface text-success-ink flex items-center">
                    <CheckCircle size={12} className="mr-1" /> PASS
                  </span>
                ) : (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-danger-surface text-danger-ink flex items-center">
                    <XCircle size={12} className="mr-1" /> FAIL
                  </span>
                )}
              </div>
              {isError ? (
                <p className="text-xs text-warning-ink">{result.test_message}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">HCE Avg Rate</span>
                    <span className="font-medium text-ink">{formatPercent(result.hce_average_rate)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">NHCE Avg Rate</span>
                    <span className="font-medium text-ink">{formatPercent(result.nhce_average_rate)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">Ratio</span>
                    <span className="font-medium text-ink">{formatPercent(result.ratio)}</span>
                  </div>
                  <div className={`flex justify-between text-sm border-t pt-2 ${isPassing ? 'border-success-border' : 'border-danger-border'}`}>
                    <span className="text-ink-muted">Margin</span>
                    <span className={`font-bold ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
                      {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-ink-muted pt-1">
                    <span>HCE: {result.hce_count} | NHCE: {result.nhce_count}</span>
                    <span className="capitalize">{result.applied_test} test</span>
                  </div>
                  {result.service_risk_flag && (
                    <div className="flex items-center text-xs text-warning-ink bg-warning-surface rounded px-2 py-1 mt-1">
                      <AlertTriangle size={12} className="mr-1" /> Review caveat
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==============================================================================
// 415 Single Scenario Result
// ==============================================================================

function Section415SingleResult({
  result,
  showEmployees,
  onToggleEmployees,
  loading,
}: {
  result: Section415ScenarioResult;
  showEmployees: boolean;
  onToggleEmployees: () => void;
  loading: boolean;
}) {
  const isPassing = result.test_result === 'pass';
  const isError = result.test_result === 'error';

  let maxUtilColorClass: string;
  if (result.max_utilization_pct > 1.0) { maxUtilColorClass = 'text-danger-ink'; }
  else if (result.max_utilization_pct >= result.warning_threshold_pct) { maxUtilColorClass = 'text-warning-ink'; }
  else { maxUtilColorClass = 'text-success-ink'; }

  if (isError) {
    return (
      <div className="bg-warning-surface border border-warning-border rounded-xl p-6">
        <div className="flex items-center mb-2">
          <AlertCircle size={24} className="text-warning-ink mr-3" />
          <h3 className="text-lg font-semibold text-warning-ink">Test Error</h3>
        </div>
        <p className="text-sm text-warning-ink">{result.test_message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Pass/Fail Card */}
      <div className={`rounded-xl p-6 border-2 ${isPassing ? 'bg-success-surface border-success-border' : 'bg-danger-surface border-danger-border'}`}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            {isPassing ? (
              <CheckCircle size={32} className="text-success-ink mr-3" />
            ) : (
              <XCircle size={32} className="text-danger-ink mr-3" />
            )}
            <div>
              <h3 className="text-xl font-bold">
                <span className={isPassing ? 'text-success-ink' : 'text-danger-ink'}>
                  415 Test: {isPassing ? 'PASS' : 'FAIL'}
                </span>
              </h3>
              <p className={`text-sm ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
                {result.scenario_name} &mdash; Year {result.simulation_year}
              </p>
            </div>
          </div>
          <div className={`text-right px-4 py-2 rounded-lg ${isPassing ? 'bg-success-surface' : 'bg-danger-surface'}`}>
            <p className="text-xs font-medium text-ink-muted">Max Utilization</p>
            <p className={`text-lg font-bold ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
              {formatPercent(result.max_utilization_pct)}
            </p>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Breach</p>
            <p className={`text-lg font-bold ${result.breach_count > 0 ? 'text-danger-ink' : 'text-ink'}`}>
              {result.breach_count}
            </p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">At Risk</p>
            <p className={`text-lg font-bold ${result.at_risk_count > 0 ? 'text-warning-ink' : 'text-ink'}`}>
              {result.at_risk_count}
            </p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Passing</p>
            <p className="text-lg font-bold text-success-ink">{result.passing_count}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">IRS Limit</p>
            <p className="text-lg font-bold text-ink">{formatCurrency(result.annual_additions_limit)}</p>
          </div>
        </div>
      </div>

      {/* Detailed Breakdown */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <h3 className="text-lg font-semibold text-ink mb-4 flex items-center">
          <Info size={20} className="mr-2 text-ink-subtle" />
          Test Details
        </h3>
        <div className="bg-surface-subtle rounded-lg p-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Total Participants Tested</span>
            <span className="font-medium text-ink-muted">{result.total_participants}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Excluded (zero comp)</span>
            <span className="font-medium text-ink-muted">{result.excluded_count}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">IRS 415(c) Dollar Limit</span>
            <span className="font-medium text-ink-muted">{formatCurrency(result.annual_additions_limit)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Warning Threshold</span>
            <span className="font-medium text-ink-muted">{formatPercent(result.warning_threshold_pct)}</span>
          </div>
          <div className="border-t border-border pt-2 mt-2 flex justify-between text-sm">
            <span className="text-ink-muted">Max Utilization</span>
            <span className={`font-bold ${maxUtilColorClass}`}>
              {formatPercent(result.max_utilization_pct)}
            </span>
          </div>
        </div>
        <div className="mt-3 bg-info-surface border border-info-border rounded-lg p-3">
          <p className="text-xs text-info-ink">
            <Info size={12} className="inline mr-1" />
            Forfeitures are excluded from the 415 annual additions calculation per current data availability.
          </p>
        </div>
      </div>

      {/* Participant Detail Table */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border">
        <button
          onClick={onToggleEmployees}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-surface-subtle transition-colors rounded-xl"
        >
          <span className="text-sm font-semibold text-ink flex items-center">
            <ChevronRight size={18} className={`mr-2 transition-transform ${showEmployees ? 'rotate-90' : ''}`} />
            Participant Details ({result.total_participants} participants)
          </span>
          {loading && <Loader2 size={16} className="animate-spin text-ink-subtle" />}
        </button>
        {showEmployees && result.employees && (
          <div className="px-6 pb-6 overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Employee ID</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Status</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Deferrals</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Match</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">NEC</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Total</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Limit</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Headroom</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Util %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.employees.map((emp) => {
                  const statusLabel = emp.status === 'at_risk' ? 'AT RISK' : 'PASS';
                  const rowBgClass = emp.status === 'at_risk' ? 'bg-warning-surface' : '';
                  let badgeClass: string;
                  if (emp.status === 'breach') { badgeClass = 'bg-danger-surface text-danger-ink'; }
                  else if (emp.status === 'at_risk') { badgeClass = 'bg-warning-surface text-warning-ink'; }
                  else { badgeClass = 'bg-success-surface text-success-ink'; }
                  let utilColorClass: string;
                  if (emp.utilization_pct > 1.0) { utilColorClass = 'text-danger-ink'; }
                  else if (emp.utilization_pct >= 0.95) { utilColorClass = 'text-warning-ink'; }
                  else { utilColorClass = 'text-ink'; }
                  return (
                  <tr key={emp.employee_id} className={`hover:bg-surface-subtle ${emp.status === 'breach' ? 'bg-danger-surface' : rowBgClass}`}>
                    <td className="py-2 px-3 text-sm text-ink font-mono">{emp.employee_id}</td>
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${badgeClass}`}>
                        {emp.status === 'breach' ? 'BREACH' : statusLabel}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.employee_deferrals)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.employer_match)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.employer_nec)}</td>
                    <td className="py-2 px-3 text-sm text-right font-medium text-ink">{formatCurrency(emp.total_annual_additions)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.applicable_limit)}</td>
                    <td className={`py-2 px-3 text-sm text-right font-medium ${emp.headroom < 0 ? 'text-danger-ink' : 'text-ink-muted'}`}>
                      {formatCurrency(emp.headroom)}
                    </td>
                    <td className={`py-2 px-3 text-sm text-right font-medium ${utilColorClass}`}>
                      {formatPercent(emp.utilization_pct)}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ==============================================================================
// 415 Comparison Results
// ==============================================================================

function Section415ComparisonResults({ results, scenarioOrder }: { results: Section415ScenarioResult[]; scenarioOrder: string[] }) {
  const ordered = [...results].sort((a, b) => scenarioOrder.indexOf(a.scenario_id) - scenarioOrder.indexOf(b.scenario_id));
  return (
    <div className="space-y-6">
      <div className={`grid gap-6 ${getGridColsClass(ordered.length)}`}>
        {ordered.map((result) => {
          const isPassing = result.test_result === 'pass';
          const isError = result.test_result === 'error';
          const cardClass = isPassing ? 'bg-success-surface border-success-border' : 'bg-danger-surface border-danger-border';
          let maxUtilColorClass: string;
          if (result.max_utilization_pct > 1.0) { maxUtilColorClass = 'text-danger-ink'; }
          else if (result.max_utilization_pct >= 0.95) { maxUtilColorClass = 'text-warning-ink'; }
          else { maxUtilColorClass = 'text-success-ink'; }
          return (
            <div key={result.scenario_id} className={`rounded-xl p-5 border-2 ${isError ? 'bg-warning-surface border-warning-border' : cardClass}`}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-ink truncate mr-2">{result.scenario_name}</h3>
                {isError ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-warning-surface text-warning-ink">ERROR</span>
                ) : isPassing ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-success-surface text-success-ink flex items-center">
                    <CheckCircle size={12} className="mr-1" /> PASS
                  </span>
                ) : (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-danger-surface text-danger-ink flex items-center">
                    <XCircle size={12} className="mr-1" /> FAIL
                  </span>
                )}
              </div>
              {isError ? (
                <p className="text-xs text-warning-ink">{result.test_message}</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">Breach</span>
                    <span className={`font-medium ${result.breach_count > 0 ? 'text-danger-ink' : 'text-ink'}`}>
                      {result.breach_count}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">At Risk</span>
                    <span className={`font-medium ${result.at_risk_count > 0 ? 'text-warning-ink' : 'text-ink'}`}>
                      {result.at_risk_count}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">Passing</span>
                    <span className="font-medium text-success-ink">{result.passing_count}</span>
                  </div>
                  <div className={`flex justify-between text-sm border-t pt-2 ${isPassing ? 'border-success-border' : 'border-danger-border'}`}>
                    <span className="text-ink-muted">Max Util</span>
                    <span className={`font-bold ${maxUtilColorClass}`}>
                      {formatPercent(result.max_utilization_pct)}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs text-ink-muted pt-1">
                    <span>Participants: {result.total_participants}</span>
                    <span>Limit: {formatCurrency(result.annual_additions_limit)}</span>
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

// ==============================================================================
// ADP Single Scenario Result
// ==============================================================================

function ADPSingleResult({
  result,
  showEmployees,
  onToggleEmployees,
  loading,
}: {
  result: ADPScenarioResult;
  showEmployees: boolean;
  onToggleEmployees: () => void;
  loading: boolean;
}) {
  const isPassing = result.test_result === 'pass';
  const isExempt = result.test_result === 'exempt';
  const isFailing = result.test_result === 'fail';
  const isError = result.test_result === 'error';

  if (isError) {
    return (
      <div className="bg-warning-surface border border-warning-border rounded-xl p-6">
        <div className="flex items-center mb-2">
          <AlertCircle size={24} className="text-warning-ink mr-3" />
          <h3 className="text-lg font-semibold text-warning-ink">Test Error</h3>
        </div>
        <p className="text-sm text-warning-ink">{result.test_message}</p>
      </div>
    );
  }

  if (isExempt) {
    return (
      <div className="bg-info-surface border-2 border-info-border rounded-xl p-6">
        <div className="flex items-center mb-2">
          <Shield size={32} className="text-info-ink mr-3" />
          <div>
            <h3 className="text-xl font-bold text-info-ink">ADP Test: EXEMPT</h3>
            <p className="text-sm text-info-ink">
              {result.scenario_name} &mdash; Year {result.simulation_year}
            </p>
          </div>
        </div>
        <div className="mt-3 bg-info-surface rounded-lg p-3">
          <p className="text-sm text-info-ink">
            <Info size={14} className="inline mr-1" />
            Safe harbor plan &mdash; ADP test is not required.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className={`rounded-xl p-6 border-2 ${isPassing ? 'bg-success-surface border-success-border' : 'bg-danger-surface border-danger-border'}`}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            {isPassing ? (
              <CheckCircle size={32} className="text-success-ink mr-3" />
            ) : (
              <XCircle size={32} className="text-danger-ink mr-3" />
            )}
            <div>
              <h3 className="text-xl font-bold">
                <span className={isPassing ? 'text-success-ink' : 'text-danger-ink'}>
                  ADP Test: {isPassing ? 'PASS' : 'FAIL'}
                </span>
              </h3>
              <p className={`text-sm ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
                {result.scenario_name} &mdash; Year {result.simulation_year}
                {result.testing_method === 'prior' && (
                  <span className="ml-2 text-xs opacity-75">(Prior Year Method)</span>
                )}
              </p>
            </div>
          </div>
          <div className={`text-right px-4 py-2 rounded-lg ${isPassing ? 'bg-success-surface' : 'bg-danger-surface'}`}>
            <p className="text-xs font-medium text-ink-muted">Margin</p>
            <p className={`text-lg font-bold ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
              {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">HCE Avg ADP</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.hce_average_adp)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">NHCE Avg ADP</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.nhce_average_adp)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Applied Threshold</p>
            <p className="text-lg font-bold text-ink">{formatPercent(result.applied_threshold)}</p>
          </div>
          <div className="bg-surface-raised/70 rounded-lg p-3">
            <p className="text-xs text-ink-muted">Test Method</p>
            <p className="text-lg font-bold text-ink capitalize">{result.applied_test}</p>
          </div>
        </div>
      </div>

      {/* Excess HCE Amount (prominent when failing) */}
      {isFailing && result.excess_hce_amount != null && (
        <div className="bg-danger-surface border border-danger-border rounded-xl p-4 flex items-start">
          <DollarSign size={20} className="text-danger-ink mr-3 mt-0.5 flex-shrink-0" />
          <div>
            <h4 className="text-sm font-semibold text-danger-ink">Excess HCE Deferrals</h4>
            <p className="text-2xl font-bold text-danger-ink mt-1">{formatCurrency(result.excess_hce_amount)}</p>
            <p className="text-xs text-danger-ink mt-1">
              Aggregate HCE deferral reduction needed for HCE average ADP to meet the applied threshold.
            </p>
          </div>
        </div>
      )}

      {/* Testing method fallback warning */}
      {result.test_message && (
        <div className="bg-warning-surface border border-warning-border rounded-xl p-3 flex items-start">
          <AlertTriangle size={16} className="text-warning-ink mr-2 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-warning-ink">{result.test_message}</p>
        </div>
      )}

      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <h3 className="text-lg font-semibold text-ink mb-4 flex items-center">
          <Info size={20} className="mr-2 text-ink-subtle" />
          Detailed Breakdown
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted flex items-center"><Users size={12} className="mr-1" /> HCE Count</p>
            <p className="text-xl font-bold text-ink">{result.hce_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted flex items-center"><Users size={12} className="mr-1" /> NHCE Count</p>
            <p className="text-xl font-bold text-ink">{result.nhce_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted">Excluded (zero comp)</p>
            <p className="text-xl font-bold text-ink">{result.excluded_count}</p>
          </div>
          <div className="bg-surface-subtle rounded-lg p-3">
            <p className="text-xs text-ink-muted">Testing Method</p>
            <p className="text-xl font-bold text-ink capitalize">{result.testing_method}</p>
          </div>
        </div>
        <div className="bg-surface-subtle rounded-lg p-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Basic Test (NHCE x 1.25)</span>
            <span className={`font-medium ${result.applied_test === 'basic' ? 'text-fidelity-green font-bold' : 'text-ink-muted'}`}>
              {formatPercent(result.basic_test_threshold)}
              {result.applied_test === 'basic' && ' (applied)'}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-ink-muted">Alternative Test (min of NHCE x 2, NHCE + 2%)</span>
            <span className={`font-medium ${result.applied_test === 'alternative' ? 'text-fidelity-green font-bold' : 'text-ink-muted'}`}>
              {formatPercent(result.alternative_test_threshold)}
              {result.applied_test === 'alternative' && ' (applied)'}
            </span>
          </div>
          <div className="border-t border-border pt-2 mt-2 flex justify-between text-sm">
            <span className="text-ink-muted">HCE Compensation Threshold</span>
            <span className="font-medium text-ink-muted">{formatCurrency(result.hce_threshold_used)}</span>
          </div>
        </div>
      </div>

      {/* Employee Detail Table */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border">
        <button
          onClick={onToggleEmployees}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-surface-subtle transition-colors rounded-xl"
        >
          <span className="text-sm font-semibold text-ink flex items-center">
            <ChevronRight size={18} className={`mr-2 transition-transform ${showEmployees ? 'rotate-90' : ''}`} />
            Employee Details ({result.hce_count + result.nhce_count} employees)
          </span>
          {loading && <Loader2 size={16} className="animate-spin text-ink-subtle" />}
        </button>
        {showEmployees && result.employees && (
          <div className="px-6 pb-6 overflow-x-auto">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Employee ID</th>
                  <th className="text-left py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Classification</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Deferrals</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Compensation</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">ADP</th>
                  <th className="text-right py-2 px-3 text-xs font-semibold text-ink-muted uppercase">Prior Year Comp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {result.employees.map((emp) => (
                  <tr key={emp.employee_id} className="hover:bg-surface-subtle">
                    <td className="py-2 px-3 text-sm text-ink font-mono">{emp.employee_id}</td>
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${emp.is_hce ? 'bg-info-surface text-info-ink' : 'bg-info-surface text-info-ink'}`}>
                        {emp.is_hce ? 'HCE' : 'NHCE'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.employee_deferrals)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">{formatCurrency(emp.plan_compensation)}</td>
                    <td className="py-2 px-3 text-sm text-right font-medium text-ink">{formatPercent(emp.individual_adp)}</td>
                    <td className="py-2 px-3 text-sm text-right text-ink-muted">
                      {emp.prior_year_compensation != null ? formatCurrency(emp.prior_year_compensation) : '—'}
                    </td>
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
// ADP Comparison Results
// ==============================================================================

function ADPComparisonResults({ results, scenarioOrder }: { results: ADPScenarioResult[]; scenarioOrder: string[] }) {
  const ordered = [...results].sort((a, b) => scenarioOrder.indexOf(a.scenario_id) - scenarioOrder.indexOf(b.scenario_id));
  return (
    <div className="space-y-6">
      <div className={`grid gap-6 ${getGridColsClass(ordered.length)}`}>
        {ordered.map((result) => {
          const isPassing = result.test_result === 'pass';
          const isExempt = result.test_result === 'exempt';
          const isFailing = result.test_result === 'fail';
          const isError = result.test_result === 'error';
          let cardClass: string;
          if (isError) { cardClass = 'bg-warning-surface border-warning-border'; }
          else if (isExempt) { cardClass = 'bg-info-surface border-info-border'; }
          else if (isPassing) { cardClass = 'bg-success-surface border-success-border'; }
          else { cardClass = 'bg-danger-surface border-danger-border'; }
          return (
            <div key={result.scenario_id} className={`rounded-xl p-5 border-2 ${cardClass}`}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-ink truncate mr-2">{result.scenario_name}</h3>
                {isError ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-warning-surface text-warning-ink">ERROR</span>
                ) : isExempt ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-info-surface text-info-ink flex items-center">
                    <Shield size={12} className="mr-1" /> EXEMPT
                  </span>
                ) : isPassing ? (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-success-surface text-success-ink flex items-center">
                    <CheckCircle size={12} className="mr-1" /> PASS
                  </span>
                ) : (
                  <span className="flex-shrink-0 px-2 py-1 rounded-full text-xs font-bold bg-danger-surface text-danger-ink flex items-center">
                    <XCircle size={12} className="mr-1" /> FAIL
                  </span>
                )}
              </div>
              {isError ? (
                <p className="text-xs text-warning-ink">{result.test_message}</p>
              ) : isExempt ? (
                <p className="text-xs text-info-ink">Safe harbor — test not required</p>
              ) : (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">HCE Avg ADP</span>
                    <span className="font-medium text-ink">{formatPercent(result.hce_average_adp)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">NHCE Avg ADP</span>
                    <span className="font-medium text-ink">{formatPercent(result.nhce_average_adp)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink-muted">Threshold</span>
                    <span className="font-medium text-ink">{formatPercent(result.applied_threshold)}</span>
                  </div>
                  <div className={`flex justify-between text-sm border-t pt-2 ${isPassing ? 'border-success-border' : 'border-danger-border'}`}>
                    <span className="text-ink-muted">Margin</span>
                    <span className={`font-bold ${isPassing ? 'text-success-ink' : 'text-danger-ink'}`}>
                      {result.margin >= 0 ? '+' : ''}{formatPercent(result.margin)}
                    </span>
                  </div>
                  {isFailing && result.excess_hce_amount != null && (
                    <div className="flex justify-between text-sm text-danger-ink">
                      <span>Excess Amount</span>
                      <span className="font-bold">{formatCurrency(result.excess_hce_amount)}</span>
                    </div>
                  )}
                  <div className="flex justify-between text-xs text-ink-muted pt-1">
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
