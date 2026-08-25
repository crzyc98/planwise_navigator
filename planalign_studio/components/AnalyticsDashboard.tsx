import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useOutletContext } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar, LabelList,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  Download, Filter, Calendar, Users, TrendingUp, DollarSign, PieChart as PieChartIcon,
  ArrowUpRight, ArrowDownRight, RefreshCw, AlertCircle, ChevronDown, Database, Loader2
} from 'lucide-react';
import {
  listWorkspaces,
  listScenarios,
  getSimulationResults,
  getResultsExportUrl, getScenarioReportUrl,
  getRunDetails,
  Workspace,
  Scenario,
  SimulationResults
} from '../services/api';
import { useChartTheme } from '../hooks/useChartTheme';
import RunHealthSummary from './simulation/RunHealthSummary';

interface LayoutContext {
  activeWorkspace: { id: string; name: string };
  lastRunScenarioId: string | null;
}

const trendIcons: Record<string, React.ReactNode> = {
  up: <ArrowUpRight size={16} className="text-success-ink mr-1" />,
  down: <ArrowDownRight size={16} className="text-danger-ink mr-1" />,
};

const trendColors: Record<string, string> = {
  up: 'text-success-ink',
  down: 'text-danger-ink',
};

const KPI_ICON_STYLES: Record<string, string> = {
  blue: 'bg-info-surface text-info-ink',
  green: 'bg-success-surface text-success-ink',
  red: 'bg-danger-surface text-danger-ink',
  gray: 'bg-surface-subtle text-ink-muted',
  purple: 'bg-info-surface text-info-ink',
  orange: 'bg-warning-surface text-warning-ink',
};

const titleCase = (value: string) => value
  .split('_')
  .map(word => word.charAt(0).toUpperCase() + word.slice(1))
  .join(' ');

/**
 * Detailed employment statuses take fixed slots on the categorical palette, so a
 * status keeps its colour whether or not the others appear in a run. The ad-hoc
 * hexes this replaces put the two termination series at ΔE 7.1 for NORMAL
 * vision — they were not reliably separable by anyone.
 */
interface EventTypeRow {
  name: string;
  value: number;
  share: number;
  /** Pre-rendered bar-tip label: LabelList only receives the value it is keyed to. */
  label: string;
}

/**
 * Event-type totals, largest first. A simulation emits ~9 event types, which is
 * more than any categorical palette should carry — as a ranked bar chart they
 * are named on the axis and sized by length, so every type keeps its own row
 * however many there are.
 */
const buildEventTypeRows = (eventTrends: Record<string, number[]>): EventTypeRow[] => {
  const totals = Object.entries(eventTrends)
    .map(([name, values]) => ({
      name: titleCase(name),
      value: values.reduce((a, b) => a + b, 0),
    }))
    .sort((a, b) => b.value - a.value);

  const sum = totals.reduce((acc, row) => acc + row.value, 0);
  return totals.map(row => {
    const share = sum > 0 ? (row.value / sum) * 100 : 0;
    return {
      ...row,
      share,
      label: `${row.value.toLocaleString()} (${share.toFixed(1)}%)`,
    };
  });
};

const KPICard = ({ title, value, subtext, trend, icon: Icon, color, loading }: any) => (
  <div className="bg-surface-raised p-5 rounded-xl shadow-sm border border-border flex items-start justify-between">
    <div>
      <p className="text-sm font-medium text-ink-muted">{title}</p>
      {loading ? (
        <div className="h-8 w-20 bg-surface-disabled rounded animate-pulse mt-1" />
      ) : (
        <>
          <h3 className="text-2xl font-bold text-ink mt-1">{value}</h3>
          {subtext && (
            <div className="flex items-center mt-1">
              {trendIcons[trend] || null}
              <span className={`text-xs font-medium ${trendColors[trend] || 'text-ink-muted'}`}>
                {subtext}
              </span>
            </div>
          )}
        </>
      )}
    </div>
    <div className={`p-2 rounded-lg ${KPI_ICON_STYLES[color] ?? KPI_ICON_STYLES.gray}`}>
      <Icon size={20} />
    </div>
  </div>
);

const EmptyState = ({ onRefresh }: { onRefresh: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-ink-subtle">
    <Database size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-ink-muted mb-2">No Simulation Selected</h3>
    <p className="text-sm text-ink-muted mb-4 text-center max-w-md">
      Select a completed simulation from the dropdown above to view analytics and insights.
    </p>
    <button
      onClick={onRefresh}
      className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Refresh Data
    </button>
  </div>
);

const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-danger-ink">
    <AlertCircle size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-danger-ink mb-2">Failed to Load Results</h3>
    <p className="text-sm text-ink-muted mb-4 text-center max-w-md">{message}</p>
    <button
      onClick={onRetry}
      className="flex items-center px-4 py-2 bg-danger-solid text-ink-inverse rounded-lg text-sm font-medium hover:bg-danger-solid-hover transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Retry
    </button>
  </div>
);

export default function AnalyticsDashboard() {
  const chartTheme = useChartTheme();
  const statusSeriesColors: Record<string, string> = {
    continuous_active: chartTheme.colorAt(0),
    new_hire_active: chartTheme.colorAt(1),
    experienced_termination: chartTheme.colorAt(2),
    new_hire_termination: chartTheme.colorAt(3),
  };
  const [searchParams] = useSearchParams();
  const { activeWorkspace: contextWorkspace, lastRunScenarioId } = useOutletContext<LayoutContext>();

  // Priority: URL param > context lastRun > default
  const scenarioIdFromUrl = searchParams.get('scenario') || lastRunScenarioId;

  // State for workspace/scenario selection
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('');
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('');
  const [initializedFromUrl, setInitializedFromUrl] = useState(false);

  // State for results
  const [results, setResults] = useState<SimulationResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Population filter toggle
  const [population, setPopulation] = useState<'all' | 'active' | 'terminated'>('all');

  // E060: Toggle between average and total compensation chart views
  const [compMetric, setCompMetric] = useState<'average' | 'total'>('average');

  // Initialize from URL parameter if present
  useEffect(() => {
    const initFromUrl = async () => {
      if (scenarioIdFromUrl && !initializedFromUrl) {
        try {
          // Get scenario details to find its workspace
          const details = await getRunDetails(scenarioIdFromUrl);
          if (details.workspace_id) {
            setSelectedWorkspaceId(details.workspace_id);
            setSelectedScenarioId(scenarioIdFromUrl);
            setInitializedFromUrl(true);
            // E103 FIX: Pass true to skip auto-selection since we already set workspace from URL
            fetchWorkspaces(true);
            return;
          }
        } catch (err) {
          console.error('Failed to load scenario from URL:', err);
        }
      }
      // Fall back to normal initialization
      fetchWorkspaces();
    };
    initFromUrl();
  }, [scenarioIdFromUrl]);

  // Fetch scenarios when workspace changes
  useEffect(() => {
    if (selectedWorkspaceId) {
      // Preserve selection if we came from URL
      fetchScenarios(selectedWorkspaceId, initializedFromUrl);
    } else {
      setScenarios([]);
      setSelectedScenarioId('');
    }
  }, [selectedWorkspaceId, initializedFromUrl]);

  // Fetch results when scenario or population changes
  useEffect(() => {
    if (selectedScenarioId) {
      fetchResults(selectedScenarioId);
    } else {
      setResults(null);
    }
  }, [selectedScenarioId, population]);

  // E103 FIX: Accept optional parameter to skip auto-selection when initialized from URL
  const fetchWorkspaces = async (skipAutoSelect = false) => {
    try {
      const data = await listWorkspaces();
      setWorkspaces(data);
      // Auto-select: prefer context workspace if available, else first
      // Skip auto-select if we already have a workspace from URL initialization
      if (data.length > 0 && !selectedWorkspaceId && !skipAutoSelect) {
        const preferredWorkspace = data.find(ws => ws.id === contextWorkspace?.id);
        setSelectedWorkspaceId(preferredWorkspace?.id || data[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch workspaces:', err);
    }
  };

  const fetchScenarios = async (workspaceId: string, preserveSelection = false) => {
    setLoadingScenarios(true);
    try {
      const data = await listScenarios(workspaceId);
      setScenarios(data);
      // Don't override selection if we're preserving (e.g., from URL parameter)
      if (!preserveSelection || !selectedScenarioId) {
        // Auto-select first completed scenario if available
        const completedScenarios = data.filter(s => s.status === 'completed');
        if (completedScenarios.length > 0) {
          setSelectedScenarioId(completedScenarios[0].id);
        } else {
          setSelectedScenarioId('');
        }
      }
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const fetchResults = async (scenarioId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSimulationResults(scenarioId, population);
      setResults(data);
    } catch (err: any) {
      console.error('Failed to fetch results:', err);
      setError(err.message || 'Failed to load simulation results');
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = useCallback((format: 'excel' | 'csv' = 'excel') => {
    // E087: Require both workspaceId and scenarioId for reliable export
    if (!selectedWorkspaceId || !selectedScenarioId) return;
    const url = getResultsExportUrl(selectedWorkspaceId, selectedScenarioId, format);
    window.open(url, '_blank', 'noopener,noreferrer');
  }, [selectedWorkspaceId, selectedScenarioId]);

  const handleRefresh = () => {
    fetchWorkspaces();
    if (selectedWorkspaceId) {
      fetchScenarios(selectedWorkspaceId);
    }
    if (selectedScenarioId) {
      fetchResults(selectedScenarioId);
    }
  };

  // Transform results for charts
  const workforceChartData = results?.workforce_progression?.map((row: any) => ({
    year: row.simulation_year,
    headcount: row.headcount,
    avgCompensation: Math.round(row.avg_compensation / 1000), // in $K
    totalCompensation: Math.round((row.total_compensation || 0) / 1_000_000 * 10) / 10, // in $M, 1 decimal
  })) || [];

  // E060: CAGR lookup from pre-computed cagr_metrics
  const compCagrMetric = results?.cagr_metrics?.find(
    (m) => m.metric === (compMetric === 'average' ? 'Average Compensation' : 'Total Compensation')
  );
  const compCagrDisplay = (() => {
    if (!compCagrMetric || compCagrMetric.years <= 0) return null;
    if (compCagrMetric.start_value === 0) return 'N/A';
    return `${compCagrMetric.cagr_pct >= 0 ? '+' : ''}${compCagrMetric.cagr_pct.toFixed(2)}%`;
  })();

  const eventChartData = results ? Object.keys(results.event_trends).length > 0
    ? Array.from(
        new Set(
          Object.values(results.event_trends).flatMap((_, i) =>
            results.workforce_progression?.map(r => r.simulation_year) || []
          )
        )
      ).map((year, idx) => ({
        year,
        Hires: results.event_trends['hire']?.[idx] || 0,
        Terminations: results.event_trends['termination']?.[idx] || 0,
        Promotions: results.event_trends['promotion']?.[idx] || 0,
      }))
    : []
  : [];

  const completedScenarios = scenarios.filter(s => s.status === 'completed');
  const selectedScenario = scenarios.find(s => s.id === selectedScenarioId);
  const yearRange = results
    ? `${results.start_year}-${results.end_year}`
    : selectedScenario?.config_overrides?.simulation?.start_year
      ? `${selectedScenario.config_overrides.simulation.start_year}-${selectedScenario.config_overrides.simulation.end_year || selectedScenario.config_overrides.simulation.start_year}`
      : '—';

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">Analytics & Insights</h1>
          <p className="text-ink-muted mt-1">View simulation results and trend analysis.</p>
        </div>
        <div className="flex space-x-2">
          {/* Workspace Selector */}
          <div className="relative">
            <select
              value={selectedWorkspaceId}
              onChange={(e) => setSelectedWorkspaceId(e.target.value)}
              className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[160px]"
            >
              <option value="">Select Workspace</option>
              {workspaces.map(ws => (
                <option key={ws.id} value={ws.id}>{ws.name}</option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
          </div>

          {/* Scenario Selector */}
          <div className="relative">
            <select
              value={selectedScenarioId}
              onChange={(e) => setSelectedScenarioId(e.target.value)}
              disabled={!selectedWorkspaceId || loadingScenarios}
              className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[200px] disabled:bg-surface-subtle disabled:text-ink-subtle"
            >
              <option value="">
                {(() => {
                  if (loadingScenarios) return 'Loading...';
                  if (completedScenarios.length === 0) return 'No completed runs';
                  return 'Select Simulation';
                })()}
              </option>
              {completedScenarios.map(scenario => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
          </div>

          {/* Population Filter Toggle */}
          <div className="flex rounded-lg border border-border-strong overflow-hidden shadow-sm">
            {(['all', 'active', 'terminated'] as const).map((opt) => (
              <button
                key={opt}
                onClick={() => setPopulation(opt)}
                className={`px-3 py-2 text-sm font-medium transition-colors ${population === opt ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised text-ink-muted hover:bg-surface-subtle'}`}
              >
                {{ all: 'All', active: 'Active', terminated: 'Terminated' }[opt]}
              </button>
            ))}
          </div>

          <button
            className="flex items-center px-4 py-2 bg-surface-raised border border-border-strong rounded-lg text-sm font-medium hover:bg-surface-subtle text-ink-muted shadow-sm transition-colors"
            disabled
          >
            <Calendar size={16} className="mr-2 text-ink-muted" />
            {yearRange}
          </button>

          <button
            onClick={handleRefresh}
            className="flex items-center px-3 py-2 bg-surface-raised border border-border-strong rounded-lg text-sm font-medium hover:bg-surface-subtle text-ink-muted shadow-sm transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>

          <button
            onClick={() => {
              if (selectedWorkspaceId && selectedScenarioId) window.open(getScenarioReportUrl(selectedWorkspaceId, selectedScenarioId, 'pdf'), '_blank', 'noopener,noreferrer');
            }}
            disabled={!selectedScenarioId || loading}
            className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse border border-transparent rounded-lg text-sm font-medium hover:bg-fidelity-dark shadow-sm transition-colors disabled:bg-surface-disabled disabled:cursor-not-allowed"
          >
            <Download size={16} className="mr-2" />
            Export report (PDF)
          </button>
        </div>
      </div>

      {/* Content Area */}
      {loading ? (
        <div className="flex items-center justify-center h-96">
          <Loader2 size={48} className="animate-spin text-fidelity-green" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={() => selectedScenarioId && fetchResults(selectedScenarioId)} />
      ) : !results ? (
        <EmptyState onRefresh={handleRefresh} />
      ) : (
        <>
          {/* Run Health Summary for the selected scenario's current result */}
          {selectedScenarioId && (
            <RunHealthSummary scenarioId={selectedScenarioId} compact />
          )}

          {/* KPI Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <KPICard
              title="Final Headcount"
              value={results.final_headcount.toLocaleString()}
              subtext={`${results.total_growth_pct >= 0 ? '+' : ''}${results.total_growth_pct.toFixed(1)}% Total Growth`}
              trend={results.total_growth_pct >= 0 ? 'up' : 'down'}
              icon={Users}
              color="blue"
              loading={loading}
            />
            <KPICard
              title="CAGR (Growth Rate)"
              value={`${results.cagr.toFixed(1)}%`}
              subtext="Compound Annual Growth"
              trend={results.cagr >= 0 ? 'up' : 'down'}
              icon={TrendingUp}
              color="green"
              loading={loading}
            />
            <KPICard
              title="Simulation Period"
              value={`${results.end_year - results.start_year + 1} Years`}
              subtext={`${results.start_year} - ${results.end_year}`}
              trend={null}
              icon={Calendar}
              color="purple"
              loading={loading}
            />
            <KPICard
              title="Plan Participation"
              value={`${(results.participation_rate * 100).toFixed(0)}%`}
              subtext="DC Plan Enrollment"
              trend="up"
              icon={PieChartIcon}
              color="orange"
              loading={loading}
            />
          </div>

          {/* Scenario Info Banner */}
          {selectedScenario && (
            <div className="bg-info-surface border border-info-border rounded-lg p-4 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-info-ink">{selectedScenario.name}</h3>
                <p className="text-sm text-info-ink">{selectedScenario.description || 'No description'}</p>
              </div>
              <div className="text-right text-sm text-info-ink">
                <p>Last run: {selectedScenario.last_run_at ? new Date(selectedScenario.last_run_at).toLocaleDateString() : 'Never'}</p>
              </div>
            </div>
          )}

          {/* CAGR Summary Table */}
          {results.cagr_metrics && results.cagr_metrics.length > 0 && (
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <div className="flex items-center mb-4">
                <TrendingUp size={20} className="text-fidelity-green mr-2" />
                <h3 className="text-lg font-semibold text-ink">Compound Annual Growth Rate (CAGR)</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-border">
                  <thead className="bg-surface-subtle">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Metric</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-ink-muted uppercase tracking-wider">Start Value</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-ink-muted uppercase tracking-wider">End Value</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-ink-muted uppercase tracking-wider">Years</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-ink-muted uppercase tracking-wider">CAGR</th>
                    </tr>
                  </thead>
                  <tbody className="bg-surface-raised divide-y divide-border">
                    {results.cagr_metrics.map((row, idx) => {
                      const isCompensation = row.metric.toLowerCase().includes('compensation');
                      const formatValue = (val: number) => {
                        if (isCompensation) {
                          return val >= 1_000_000
                            ? `$${(val / 1_000_000).toFixed(2)}M`
                            : `$${Math.round(val).toLocaleString()}`;
                        }
                        return val.toLocaleString();
                      };
                      const cagrSign = row.cagr_pct >= 0 ? '+' : '';
                      const cagrDisplay = row.years > 0
                        ? `${cagrSign}${row.cagr_pct.toFixed(2)}%`
                        : 'N/A';
                      const cagrColor = (() => {
                        if (row.years === 0) return 'text-ink-muted';
                        if (row.cagr_pct > 0) return 'text-success-ink';
                        if (row.cagr_pct < 0) return 'text-danger-ink';
                        return 'text-ink-muted';
                      })();

                      return (
                        <tr key={row.metric} className={idx % 2 === 0 ? 'bg-surface-raised' : 'bg-surface-subtle'}>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">{row.metric}</td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted text-right">{formatValue(row.start_value)}</td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted text-right">{formatValue(row.end_value)}</td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted text-right">{row.years}</td>
                          <td className={`px-6 py-4 whitespace-nowrap text-sm font-semibold text-right ${cagrColor}`}>{cagrDisplay}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {results.cagr_metrics[0]?.years === 0 && (
                <p className="mt-3 text-xs text-ink-subtle">CAGR requires more than one simulation year to calculate.</p>
              )}
            </div>
          )}

          {/* Main Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Workforce Growth */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <h3 className="text-lg font-semibold text-ink mb-6">Workforce Headcount Over Time</h3>
              <div className="h-80">
                {workforceChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={workforceChartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                      <YAxis stroke={chartTheme.axis.line} />
                      <Tooltip
                        contentStyle={chartTheme.tooltip.contentStyle}
                        formatter={(value: number, name: string) => [value.toLocaleString(), name === 'headcount' ? 'Headcount' : 'Avg Comp ($K)']}
                      />
                      <Legend verticalAlign="top" height={36} formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                      <Line type="monotone" dataKey="headcount" name="Headcount" stroke={chartTheme.semantic.primary} strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle">
                    <p>No workforce data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Event Distribution */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <h3 className="text-lg font-semibold text-ink mb-6">Event Distribution by Year</h3>
              <div className="h-80">
                {eventChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={eventChartData} barSize={40}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                      <YAxis stroke={chartTheme.axis.line} />
                      <Tooltip
                        cursor={chartTheme.tooltip.cursorStyle}
                        contentStyle={chartTheme.tooltip.contentStyle}
                      />
                      <Legend verticalAlign="top" height={36} formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                      <Bar dataKey="Hires" stackId="a" fill={chartTheme.colorAt(1)} radius={[0, 0, 4, 4]} />
                      <Bar dataKey="Promotions" stackId="a" fill={chartTheme.colorAt(2)} />
                      <Bar dataKey="Terminations" stackId="a" fill={chartTheme.semantic.negative} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle">
                    <p>No event data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Compensation Trend - All Employees (E060: Average/Total toggle with CAGR) */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-ink">
                  {compMetric === 'average'
                    ? 'Average Compensation - All Employees ($K)'
                    : 'Total Compensation - All Employees ($M)'}
                  {compCagrDisplay && (
                    <span className="text-sm font-normal text-ink-muted ml-2">
                      — CAGR: {compCagrDisplay}
                    </span>
                  )}
                </h3>
                <div className="flex rounded-lg border border-border-strong overflow-hidden">
                  <button
                    onClick={() => setCompMetric('average')}
                    className={`px-3 py-1 text-xs font-medium transition-colors ${compMetric === 'average' ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised text-ink-muted hover:bg-surface-subtle'}`}
                  >
                    Average
                  </button>
                  <button
                    onClick={() => setCompMetric('total')}
                    className={`px-3 py-1 text-xs font-medium transition-colors ${compMetric === 'total' ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised text-ink-muted hover:bg-surface-subtle'}`}
                  >
                    Total
                  </button>
                </div>
              </div>
              <div className="h-80">
                {workforceChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={workforceChartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                      <YAxis
                        stroke={chartTheme.axis.line}
                        tickFormatter={compMetric === 'average'
                          ? (value) => `$${value}K`
                          : (value) => `$${value}M`
                        }
                      />
                      <Tooltip
                        contentStyle={chartTheme.tooltip.contentStyle}
                        formatter={compMetric === 'average'
                          ? (value: number) => [`$${value}K`, 'Avg Compensation']
                          : (value: number) => [`$${value}M`, 'Total Compensation']
                        }
                      />
                      <Legend verticalAlign="top" height={36} formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                      <Line
                        type="monotone"
                        dataKey={compMetric === 'average' ? 'avgCompensation' : 'totalCompensation'}
                        name={compMetric === 'average' ? 'Avg Compensation' : 'Total Compensation'}
                        stroke={chartTheme.colorAt(2)}
                        strokeWidth={3}
                        dot={{ r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-ink-subtle">
                    <p>No compensation data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Event Type Breakdown */}
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <h3 className="text-lg font-semibold text-ink mb-6">Event Types (Total)</h3>
              {results.event_trends && Object.keys(results.event_trends).length > 0 ? (() => {
                const rows = buildEventTypeRows(results.event_trends);

                return (
                  <div style={{ height: Math.max(320, rows.length * 36 + 32) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={rows} layout="vertical" barSize={20} margin={{ right: 130, left: 0 }}>
                        {/* Every bar is directly labelled, so a value axis and its
                            gridlines would only restate what the labels already say. */}
                        <XAxis type="number" hide />
                        <YAxis dataKey="name" type="category" stroke={chartTheme.axis.line} width={150} fontSize={12} tick={{ fill: chartTheme.axis.tick }} />
                        <Tooltip
                          cursor={chartTheme.tooltip.cursorStyle}
                          contentStyle={chartTheme.tooltip.contentStyle}
                          formatter={(value: number, _name: string, props: any) => [
                            `${value.toLocaleString()} (${props.payload.share.toFixed(1)}%)`,
                            'Events',
                          ]}
                        />
                        {/* One measure, one hue: length carries the magnitude, so the
                            categorical palette stays reserved for identity. */}
                        <Bar dataKey="value" fill={chartTheme.semantic.primary} name="Events" radius={[0, 4, 4, 0]}>
                          <LabelList
                            dataKey="label"
                            position="right"
                            style={{ fill: chartTheme.axis.label, fontSize: 12 }}
                          />
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                );
              })() : (
                <div className="h-80 flex items-center justify-center text-ink-subtle">
                  <p>No event breakdown available</p>
                </div>
              )}
            </div>

          </div>

          {/* Compensation by Detailed Status Code */}
          {results.compensation_by_status && results.compensation_by_status.length > 0 && (() => {
            // Helper to format status codes nicely
            const formatStatus = (status: string) => status ? titleCase(status) : status;

            return (
              <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
                <h3 className="text-lg font-semibold text-ink mb-6">Average Compensation by Detailed Status ($K)</h3>
                <div className="h-96">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={(() => {
                        // Transform data: group by year with status as keys
                        const years = [...new Set(results.compensation_by_status.map(r => r.simulation_year))].sort((a, b) => a - b);
                        const statuses = [...new Set(results.compensation_by_status.map(r => r.employment_status))].sort((a, b) => a.localeCompare(b));
                        return years.map(year => {
                          const entry: Record<string, any> = { year };
                          statuses.forEach((status: string) => {
                            const match = results.compensation_by_status.find(
                              r => r.simulation_year === year && r.employment_status === status
                            );
                            entry[status] = match ? Math.round(match.avg_compensation / 1000) : 0;
                            entry[`${status}_count`] = match ? match.employee_count : 0;
                          });
                          return entry;
                        });
                      })()}
                      barSize={24}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                      <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                      <YAxis stroke={chartTheme.axis.line} tickFormatter={(value) => `$${value}K`} />
                      <Tooltip
                        cursor={chartTheme.tooltip.cursorStyle}
                        contentStyle={chartTheme.tooltip.contentStyle}
                        formatter={(value: number, name: string, props: any) => {
                          const count = props.payload[`${name}_count`];
                          return [`$${value}K (n=${count})`, formatStatus(name)];
                        }}
                      />
                      <Legend
                        verticalAlign="top"
                        height={36}
                        // Recharts tints legend text with the series colour; the palette's
                        // lighter slots don't clear 3:1 on white, so labels wear text ink
                        // and the swatch beside them carries the identity.
                        formatter={(value) => <span style={{ color: chartTheme.legendText }}>{formatStatus(value)}</span>}
                      />
                      {[...new Set(results.compensation_by_status.map(r => r.employment_status))].map((status: string) => (
                        <Bar
                          key={status}
                          dataKey={status}
                          name={status}
                          fill={statusSeriesColors[status] || chartTheme.colorAt(0)}
                          radius={[4, 4, 0, 0]}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                {/* Summary table */}
                <div className="mt-6 overflow-x-auto">
                  <table className="min-w-full divide-y divide-border">
                    <thead className="bg-surface-subtle">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Year</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Status</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-ink-muted uppercase tracking-wider">Count</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-ink-muted uppercase tracking-wider">Avg Comp</th>
                      </tr>
                    </thead>
                    <tbody className="bg-surface-raised divide-y divide-border">
                      {results.compensation_by_status.map((row, idx) => (
                        <tr key={`${row.simulation_year}-${row.employment_status}`} className={idx % 2 === 0 ? 'bg-surface-raised' : 'bg-surface-subtle'}>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-ink">{row.simulation_year}</td>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-ink">
                            {/* Swatch matches the bar fill, so this table doubles as the chart's legend. */}
                            <span className="inline-flex items-center gap-2">
                              <span
                                className="w-3 h-3 rounded-sm shrink-0"
                                style={{ backgroundColor: statusSeriesColors[row.employment_status] || chartTheme.colorAt(0) }}
                              />
                              {formatStatus(row.employment_status)}
                            </span>
                          </td>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-ink text-right">{row.employee_count?.toLocaleString()}</td>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-ink text-right">${Math.round(row.avg_compensation / 1000)}K</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}

          {/* Growth Analysis Summary */}
          {results.growth_analysis && Object.keys(results.growth_analysis).length > 0 && (
            <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
              <h3 className="text-lg font-semibold text-ink mb-4">Growth Analysis Summary</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(results.growth_analysis).map(([key, value]) => (
                  <div key={key} className="bg-surface-subtle p-4 rounded-lg">
                    <p className="text-sm text-ink-muted capitalize">{key.replace(/_/g, ' ')}</p>
                    <p className="text-xl font-bold text-ink">
                      {(() => {
                        if (typeof value !== 'number') return value;
                        if (key.includes('pct') || key.includes('rate')) return `${value.toFixed(1)}%`;
                        return value.toLocaleString();
                      })()}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
