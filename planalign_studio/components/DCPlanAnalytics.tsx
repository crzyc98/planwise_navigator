import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  Users, DollarSign, TrendingUp, PieChart as PieChartIcon,
  RefreshCw, AlertCircle, ChevronDown, Database, Loader2, ArrowUpRight
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import {
  listScenarios,
  getDCPlanAnalytics,
  compareDCPlanAnalytics,
  Scenario,
  DCPlanAnalytics as DCPlanAnalyticsData,
  DCPlanComparisonResponse,
} from '../services/api';
import { COLORS, MAX_SCENARIO_SELECTION } from '../constants';

const formatCurrency = (value: number): string => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
};

const KPICard = ({ title, value, subtext, icon: Icon, color, loading }: any) => (
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
              <span className="text-xs font-medium text-gray-500">{subtext}</span>
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
      Select a completed simulation from the dropdown above to view DC Plan analytics.
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
    <h3 className="text-lg font-semibold text-red-600 mb-2">Failed to Load Analytics</h3>
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

const PARTICIPATION_COLORS = ['#00853F', '#4CAF50', '#81C784'];
const CONTRIBUTION_COLORS = { employee: '#0088FE', match: '#00C49F', core: '#FFBB28' };

export default function DCPlanAnalytics() {
  // Workspace context from Layout (shared across all pages)
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  // State for scenario selection (page-local)
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);

  // State for results
  const [analytics, setAnalytics] = useState<DCPlanAnalyticsData | null>(null);
  const [comparisonData, setComparisonData] = useState<DCPlanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Comparison mode toggle
  const [comparisonMode, setComparisonMode] = useState(false);

  // Active-only toggle for participation metrics (default: all participants)
  const [activeOnly, setActiveOnly] = useState(false);

  // Fetch scenarios when workspace changes
  useEffect(() => {
    if (activeWorkspace?.id) {
      fetchScenarios(activeWorkspace.id);
      setSelectedScenarioIds([]);
      setAnalytics(null);
      setComparisonData(null);
      setError(null);
    } else {
      setScenarios([]);
      setSelectedScenarioIds([]);
      setAnalytics(null);
      setComparisonData(null);
    }
  }, [activeWorkspace?.id]);

  // Fetch analytics when scenario or active-only toggle changes
  useEffect(() => {
    if (!activeWorkspace?.id) return;
    if (selectedScenarioIds.length === 1 && !comparisonMode) {
      fetchAnalytics(selectedScenarioIds[0]);
    } else if (selectedScenarioIds.length >= 2 && comparisonMode) {
      fetchComparison(selectedScenarioIds);
    } else {
      setAnalytics(null);
      setComparisonData(null);
    }
  }, [selectedScenarioIds, comparisonMode, activeWorkspace?.id, activeOnly]);

  const fetchScenarios = async (workspaceId: string) => {
    setLoadingScenarios(true);
    try {
      const data = await listScenarios(workspaceId);
      setScenarios(data);
      const completedScenarios = data.filter(s => s.status === 'completed');
      if (completedScenarios.length > 0 && selectedScenarioIds.length === 0) {
        setSelectedScenarioIds([completedScenarios[0].id]);
      }
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const fetchAnalytics = async (scenarioId: string) => {
    if (!activeWorkspace?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getDCPlanAnalytics(activeWorkspace.id, scenarioId, activeOnly);
      setAnalytics(data);
      setComparisonData(null);
    } catch (err: any) {
      console.error('Failed to fetch analytics:', err);
      setError(err.message || 'Failed to load DC plan analytics');
      setAnalytics(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchComparison = async (scenarioIds: string[]) => {
    if (!activeWorkspace?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await compareDCPlanAnalytics(activeWorkspace.id, scenarioIds, activeOnly);
      setComparisonData(data);
      setAnalytics(null);
    } catch (err: any) {
      console.error('Failed to fetch comparison:', err);
      setError(err.message || 'Failed to load comparison data');
      setComparisonData(null);
    } finally {
      setLoading(false);
    }
  };

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

  const handleRefresh = () => {
    if (activeWorkspace?.id) {
      fetchScenarios(activeWorkspace.id);
    }
  };

  const completedScenarios = scenarios.filter(s => s.status === 'completed');

  // Prepare chart data
  const contributionChartData = analytics?.contribution_by_year.map(year => ({
    year: year.year,
    Employee: year.total_employee_contributions,
    Match: year.total_employer_match,
    Core: year.total_employer_core,
  })) || [];

  const deferralDistributionData = analytics?.deferral_rate_distribution.map(bucket => ({
    bucket: bucket.bucket,
    count: bucket.count,
    percentage: bucket.percentage,
  })) || [];

  const participationPieData = analytics ? [
    { name: 'Auto Enrolled', value: analytics.participation_by_method.auto_enrolled },
    { name: 'Voluntary', value: analytics.participation_by_method.voluntary_enrolled },
    { name: 'Census', value: analytics.participation_by_method.census_enrolled },
  ].filter(d => d.value > 0) : [];

  // Comparison chart data
  const comparisonContributionData = comparisonData?.analytics.map(a => ({
    scenario: a.scenario_name,
    Employee: a.total_employee_contributions,
    Match: a.total_employer_match,
    Core: a.total_employer_core,
  })) || [];

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">DC Plan Analytics</h1>
          <p className="text-gray-500 mt-1">Analyze retirement plan contributions and participation.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Scenario Selector */}
          <div className="relative">
            <select
              value={comparisonMode ? '' : selectedScenarioIds[0] || ''}
              onChange={(e) => handleScenarioToggle(e.target.value)}
              disabled={!activeWorkspace?.id || loadingScenarios || comparisonMode}
              className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[200px] disabled:bg-gray-50 disabled:text-gray-400"
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

          {/* Comparison Mode Toggle */}
          <button
            onClick={() => {
              setComparisonMode(!comparisonMode);
              if (!comparisonMode) {
                setSelectedScenarioIds([]);
              }
            }}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              comparisonMode
                ? 'bg-fidelity-green text-white'
                : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            Compare {comparisonMode && `(${selectedScenarioIds.length}/3)`}
          </button>

          {/* Active Employees Only Toggle */}
          <label className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm cursor-pointer hover:bg-gray-50 transition-colors">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
              className="w-4 h-4 text-fidelity-green rounded border-gray-300 focus:ring-fidelity-green"
            />
            <span className="font-medium text-gray-700 whitespace-nowrap">Active employees only</span>
          </label>

          <button
            onClick={handleRefresh}
            className="flex items-center px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 text-gray-700 shadow-sm transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Comparison Mode Scenario Selection */}
      {comparisonMode && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm font-medium text-blue-900 mb-2">
            Select 2-{MAX_SCENARIO_SELECTION} scenarios to compare (click to select/deselect):
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
          </div>
        </div>
      )}

      {/* Content Area */}
      {loading ? (
        <div className="flex items-center justify-center h-96">
          <Loader2 size={48} className="animate-spin text-fidelity-green" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={handleRefresh} />
      ) : !analytics && !comparisonData ? (
        <EmptyState onRefresh={handleRefresh} />
      ) : comparisonData ? (
        /* Comparison View */
        <>
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">Scenario Comparison</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 font-semibold text-gray-600">Metric</th>
                    {comparisonData.analytics.map(a => (
                      <th key={a.scenario_id} className="text-right py-3 px-4 font-semibold text-gray-600">
                        {a.scenario_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  <tr>
                    <td className="py-3 px-4 text-gray-700">Participation Rate</td>
                    {comparisonData.analytics.map(a => (
                      <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                        {a.participation_rate.toFixed(1)}%
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-gray-700">Total Employee Contributions</td>
                    {comparisonData.analytics.map(a => (
                      <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                        {formatCurrency(a.total_employee_contributions)}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-gray-700">Total Employer Match</td>
                    {comparisonData.analytics.map(a => (
                      <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                        {formatCurrency(a.total_employer_match)}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-gray-700">Total Employer Core</td>
                    {comparisonData.analytics.map(a => (
                      <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                        {formatCurrency(a.total_employer_core)}
                      </td>
                    ))}
                  </tr>
                  <tr className="bg-gray-50">
                    <td className="py-3 px-4 text-gray-900 font-semibold">Total All Contributions</td>
                    {comparisonData.analytics.map(a => (
                      <td key={a.scenario_id} className="py-3 px-4 text-right font-bold text-fidelity-green">
                        {formatCurrency(a.total_all_contributions)}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="py-3 px-4 text-gray-700">Employees at IRS Limit</td>
                    {comparisonData.analytics.map(a => (
                      <td key={a.scenario_id} className="py-3 px-4 text-right font-medium">
                        {a.irs_limit_metrics.employees_at_irs_limit.toLocaleString()} ({a.irs_limit_metrics.irs_limit_rate.toFixed(1)}%)
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Comparison Bar Chart */}
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
            <h3 className="text-lg font-semibold text-gray-800 mb-6">Contribution Totals by Scenario</h3>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={comparisonContributionData} barSize={60}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis dataKey="scenario" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" tickFormatter={(value) => formatCurrency(value)} />
                  <Tooltip
                    cursor={{ fill: '#F3F4F6' }}
                    contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                    formatter={(value: number) => [formatCurrency(value), '']}
                  />
                  <Legend verticalAlign="top" height={36} />
                  <Bar dataKey="Employee" stackId="a" fill={CONTRIBUTION_COLORS.employee} name="Employee" />
                  <Bar dataKey="Match" stackId="a" fill={CONTRIBUTION_COLORS.match} name="Employer Match" />
                  <Bar dataKey="Core" stackId="a" fill={CONTRIBUTION_COLORS.core} name="Employer Core" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      ) : analytics && (
        /* Single Scenario View */
        <>
          {/* KPI Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <KPICard
              title="Employee Deferrals"
              value={formatCurrency(analytics.total_employee_contributions)}
              subtext={`${analytics.total_enrolled.toLocaleString()} participants`}
              icon={DollarSign}
              color="blue"
              loading={loading}
            />
            <KPICard
              title="Employer Match"
              value={formatCurrency(analytics.total_employer_match)}
              subtext="Total employer match"
              icon={DollarSign}
              color="green"
              loading={loading}
            />
            <KPICard
              title="Employer Core"
              value={formatCurrency(analytics.total_employer_core)}
              subtext="Non-elective contributions"
              icon={DollarSign}
              color="orange"
              loading={loading}
            />
            <KPICard
              title="Participation Rate"
              value={`${analytics.participation_rate.toFixed(1)}%`}
              subtext={`${analytics.total_enrolled.toLocaleString()} of ${analytics.total_eligible.toLocaleString()} ${activeOnly ? 'active eligible' : 'eligible'}`}
              icon={Users}
              color="purple"
              loading={loading}
            />
          </div>

          {/* Scenario Info Banner */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-blue-900">{analytics.scenario_name}</h3>
              <p className="text-sm text-blue-700">
                Total All Contributions: {formatCurrency(analytics.total_all_contributions)}
              </p>
            </div>
            <div className="text-right text-sm text-blue-600">
              <p>{analytics.contribution_by_year.length} year(s) of data</p>
            </div>
          </div>

          {/* Main Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Contribution Stacked Bar Chart */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Contributions by Year</h3>
              <div className="h-80">
                {contributionChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={contributionChartData} barSize={50}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="year" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" tickFormatter={(value) => formatCurrency(value)} />
                      <Tooltip
                        cursor={{ fill: '#F3F4F6' }}
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                        formatter={(value: number) => [formatCurrency(value), '']}
                      />
                      <Legend verticalAlign="top" height={36} />
                      <Bar dataKey="Employee" stackId="a" fill={CONTRIBUTION_COLORS.employee} name="Employee" radius={[0, 0, 4, 4]} />
                      <Bar dataKey="Match" stackId="a" fill={CONTRIBUTION_COLORS.match} name="Employer Match" />
                      <Bar dataKey="Core" stackId="a" fill={CONTRIBUTION_COLORS.core} name="Employer Core" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No contribution data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Deferral Rate Distribution */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Deferral Rate Distribution</h3>
              <div className="h-80">
                {deferralDistributionData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={deferralDistributionData} layout="vertical" barSize={20}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E5E7EB" />
                      <XAxis type="number" stroke="#9CA3AF" />
                      <YAxis dataKey="bucket" type="category" stroke="#9CA3AF" width={50} />
                      <Tooltip
                        cursor={{ fill: '#F3F4F6' }}
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                        formatter={(value: number, name: string) => [
                          name === 'count' ? `${value} employees` : `${value.toFixed(1)}%`,
                          name === 'count' ? 'Count' : 'Percentage'
                        ]}
                      />
                      <Bar dataKey="count" fill={COLORS.primary} name="count" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No deferral data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Participation Breakdown Pie Chart */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Participation by Enrollment Method</h3>
              <div className="h-80">
                {participationPieData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={participationPieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={5}
                        dataKey="value"
                        label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                        labelLine={false}
                      >
                        {participationPieData.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={PARTICIPATION_COLORS[index % PARTICIPATION_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value: number) => [value.toLocaleString(), 'Employees']} />
                      <Legend layout="vertical" verticalAlign="middle" align="right" />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No participation data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Escalation Summary */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">Escalation Summary</h3>
              <div className="space-y-4">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <p className="text-sm text-gray-500">Employees with Escalations</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {analytics.escalation_metrics.employees_with_escalations.toLocaleString()}
                    <span className="text-sm font-normal text-gray-500 ml-2">
                      ({((analytics.escalation_metrics.employees_with_escalations / analytics.total_enrolled) * 100).toFixed(1)}% of enrolled)
                    </span>
                  </p>
                </div>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <p className="text-sm text-gray-500">Average Escalations per Employee</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {analytics.escalation_metrics.avg_escalation_count.toFixed(1)}
                  </p>
                </div>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <p className="text-sm text-gray-500">Total Rate Increase from Escalations</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {(analytics.escalation_metrics.total_escalation_amount * 100).toFixed(2)}%
                  </p>
                </div>
                <div className="bg-orange-50 p-4 rounded-lg border border-orange-200">
                  <p className="text-sm text-orange-700">Employees at IRS 402(g) Limit</p>
                  <p className="text-2xl font-bold text-orange-900">
                    {analytics.irs_limit_metrics.employees_at_irs_limit.toLocaleString()}
                    <span className="text-sm font-normal text-orange-700 ml-2">
                      ({analytics.irs_limit_metrics.irs_limit_rate.toFixed(1)}% of participants)
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
