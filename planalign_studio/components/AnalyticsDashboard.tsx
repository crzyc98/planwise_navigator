import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useOutletContext } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
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
  getResultsExportUrl,
  getRunDetails,
  Workspace,
  Scenario,
  SimulationResults
} from '../services/api';
import { COLORS } from '../constants';

interface LayoutContext {
  activeWorkspace: { id: string; name: string };
  lastRunScenarioId: string | null;
}

const KPICard = ({ title, value, subtext, trend, icon: Icon, color, loading }: any) => (
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
              {trend === 'up' ? <ArrowUpRight size={16} className="text-green-500 mr-1" /> : trend === 'down' ? <ArrowDownRight size={16} className="text-red-500 mr-1" /> : null}
              <span className={`text-xs font-medium ${trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-gray-500'}`}>
                {subtext}
              </span>
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
    <h3 className="text-lg font-semibold text-gray-600 mb-2">No Simulation Selected</h3>
    <p className="text-sm text-gray-500 mb-4 text-center max-w-md">
      Select a completed simulation from the dropdown above to view analytics and insights.
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
    <h3 className="text-lg font-semibold text-red-600 mb-2">Failed to Load Results</h3>
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

export default function AnalyticsDashboard() {
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

  // Fetch results when scenario changes
  useEffect(() => {
    if (selectedScenarioId) {
      fetchResults(selectedScenarioId);
    } else {
      setResults(null);
    }
  }, [selectedScenarioId]);

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
      const data = await getSimulationResults(scenarioId);
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
    window.open(url, '_blank');
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
  })) || [];

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
          <h1 className="text-2xl font-bold text-gray-900">Analytics & Insights</h1>
          <p className="text-gray-500 mt-1">View simulation results and trend analysis.</p>
        </div>
        <div className="flex space-x-2">
          {/* Workspace Selector */}
          <div className="relative">
            <select
              value={selectedWorkspaceId}
              onChange={(e) => setSelectedWorkspaceId(e.target.value)}
              className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[160px]"
            >
              <option value="">Select Workspace</option>
              {workspaces.map(ws => (
                <option key={ws.id} value={ws.id}>{ws.name}</option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
          </div>

          {/* Scenario Selector */}
          <div className="relative">
            <select
              value={selectedScenarioId}
              onChange={(e) => setSelectedScenarioId(e.target.value)}
              disabled={!selectedWorkspaceId || loadingScenarios}
              className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[200px] disabled:bg-gray-50 disabled:text-gray-400"
            >
              <option value="">
                {loadingScenarios ? 'Loading...' : completedScenarios.length === 0 ? 'No completed runs' : 'Select Simulation'}
              </option>
              {completedScenarios.map(scenario => (
                <option key={scenario.id} value={scenario.id}>
                  {scenario.name}
                </option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
          </div>

          <button
            className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 text-gray-700 shadow-sm transition-colors"
            disabled
          >
            <Calendar size={16} className="mr-2 text-gray-500" />
            {yearRange}
          </button>

          <button
            onClick={handleRefresh}
            className="flex items-center px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 text-gray-700 shadow-sm transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>

          <button
            onClick={() => handleExport('excel')}
            disabled={!selectedScenarioId || loading}
            className="flex items-center px-4 py-2 bg-fidelity-green text-white border border-transparent rounded-lg text-sm font-medium hover:bg-fidelity-dark shadow-sm transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            <Download size={16} className="mr-2" />
            Export Report
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
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-blue-900">{selectedScenario.name}</h3>
                <p className="text-sm text-blue-700">{selectedScenario.description || 'No description'}</p>
              </div>
              <div className="text-right text-sm text-blue-600">
                <p>Last run: {selectedScenario.last_run_at ? new Date(selectedScenario.last_run_at).toLocaleDateString() : 'Never'}</p>
              </div>
            </div>
          )}

          {/* Main Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Workforce Growth */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Workforce Headcount Over Time</h3>
              <div className="h-80">
                {workforceChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={workforceChartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="year" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                        formatter={(value: number, name: string) => [value.toLocaleString(), name === 'headcount' ? 'Headcount' : 'Avg Comp ($K)']}
                      />
                      <Legend verticalAlign="top" height={36}/>
                      <Line type="monotone" dataKey="headcount" name="Headcount" stroke={COLORS.primary} strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No workforce data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Event Distribution */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Event Distribution by Year</h3>
              <div className="h-80">
                {eventChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={eventChartData} barSize={40}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="year" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" />
                      <Tooltip
                        cursor={{ fill: '#F3F4F6' }}
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                      />
                      <Legend verticalAlign="top" height={36}/>
                      <Bar dataKey="Hires" stackId="a" fill={COLORS.secondary} radius={[0, 0, 4, 4]} />
                      <Bar dataKey="Promotions" stackId="a" fill={COLORS.accent} />
                      <Bar dataKey="Terminations" stackId="a" fill={COLORS.danger} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No event data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Average Compensation Trend - All Employees */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Average Compensation - All Employees ($K)</h3>
              <div className="h-80">
                {workforceChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={workforceChartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="year" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" tickFormatter={(value) => `$${value}K`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                        formatter={(value: number) => [`$${value}K`, 'Avg Compensation']}
                      />
                      <Legend verticalAlign="top" height={36}/>
                      <Line type="monotone" dataKey="avgCompensation" name="Avg Compensation" stroke={COLORS.accent} strokeWidth={3} dot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No compensation data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Event Type Breakdown */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Event Types (Total)</h3>
              <div className="h-80">
                {results.event_trends && Object.keys(results.event_trends).length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={Object.entries(results.event_trends).map(([name, values]) => ({
                          name,
                          value: values.reduce((a, b) => a + b, 0)
                        }))}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {Object.keys(results.event_trends).map((_, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS.charts[index % COLORS.charts.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend layout="vertical" verticalAlign="middle" align="right" />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No event breakdown available</p>
                  </div>
                )}
              </div>
            </div>

          </div>

          {/* Compensation by Detailed Status Code */}
          {results.compensation_by_status && results.compensation_by_status.length > 0 && (() => {
            // Helper to format status codes nicely
            const formatStatus = (status: string) => status
              ?.split('_')
              .map(word => word.charAt(0).toUpperCase() + word.slice(1))
              .join(' ') || status;

            // Status color mapping
            const statusColors: Record<string, string> = {
              'continuous_active': '#00C49F',    // Green
              'new_hire_active': '#0088FE',      // Blue
              'experienced_termination': '#FF8042', // Orange
              'new_hire_termination': '#FF6B6B'  // Red
            };

            const statusBadgeColors: Record<string, string> = {
              'continuous_active': 'bg-green-100 text-green-800',
              'new_hire_active': 'bg-blue-100 text-blue-800',
              'experienced_termination': 'bg-orange-100 text-orange-800',
              'new_hire_termination': 'bg-red-100 text-red-800'
            };

            return (
              <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-800 mb-6">Average Compensation by Detailed Status ($K)</h3>
                <div className="h-96">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={(() => {
                        // Transform data: group by year with status as keys
                        const years = [...new Set(results.compensation_by_status.map(r => r.simulation_year))].sort();
                        const statuses = [...new Set(results.compensation_by_status.map(r => r.employment_status))];
                        return years.map(year => {
                          const entry: Record<string, any> = { year };
                          statuses.forEach(status => {
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
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="year" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" tickFormatter={(value) => `$${value}K`} />
                      <Tooltip
                        cursor={{ fill: '#F3F4F6' }}
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                        formatter={(value: number, name: string, props: any) => {
                          const count = props.payload[`${name}_count`];
                          return [`$${value}K (n=${count})`, formatStatus(name)];
                        }}
                      />
                      <Legend
                        verticalAlign="top"
                        height={36}
                        formatter={(value) => formatStatus(value)}
                      />
                      {[...new Set(results.compensation_by_status.map(r => r.employment_status))].map((status) => (
                        <Bar
                          key={status}
                          dataKey={status}
                          name={status}
                          fill={statusColors[status] || COLORS.charts[0]}
                          radius={[4, 4, 0, 0]}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                {/* Summary table */}
                <div className="mt-6 overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Year</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Count</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Avg Comp</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {results.compensation_by_status.map((row, idx) => (
                        <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-900">{row.simulation_year}</td>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-900">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                              statusBadgeColors[row.employment_status] || 'bg-gray-100 text-gray-800'
                            }`}>
                              {formatStatus(row.employment_status)}
                            </span>
                          </td>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-900 text-right">{row.employee_count?.toLocaleString()}</td>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-900 text-right">${Math.round(row.avg_compensation / 1000)}K</td>
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
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">Growth Analysis Summary</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(results.growth_analysis).map(([key, value]) => (
                  <div key={key} className="bg-gray-50 p-4 rounded-lg">
                    <p className="text-sm text-gray-500 capitalize">{key.replace(/_/g, ' ')}</p>
                    <p className="text-xl font-bold text-gray-900">
                      {typeof value === 'number' ? (key.includes('pct') || key.includes('rate') ? `${value.toFixed(1)}%` : value.toLocaleString()) : value}
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
