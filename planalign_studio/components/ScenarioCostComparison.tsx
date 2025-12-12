/**
 * E104: Scenario Cost Comparison Page
 *
 * Side-by-side comparison of DC Plan costs between two scenarios:
 * - Baseline scenario vs Comparison scenario
 * - Year-by-year breakdown of key metrics
 * - Variance calculations with visual indicators
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Scale, RefreshCw, AlertCircle, ChevronDown, Database, Loader2,
  TrendingUp, TrendingDown, Minus, DollarSign, Users, Percent
} from 'lucide-react';
import {
  listWorkspaces,
  listScenarios,
  compareDCPlanAnalytics,
  Workspace,
  Scenario,
  DCPlanComparisonResponse,
  DCPlanAnalytics,
  ContributionYearSummary,
} from '../services/api';

// ============================================================================
// Utility Functions
// ============================================================================

const formatCurrency = (value: number): string => {
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(2)}M`;
  } else if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
};

const formatPercent = (value: number, decimals: number = 1): string => {
  return `${value.toFixed(decimals)}%`;
};

const formatDeferralRate = (value: number): string => {
  // Deferral rate comes as decimal (0.05 = 5%)
  return `${(value * 100).toFixed(2)}%`;
};

const calculateVariance = (baseline: number, comparison: number): { delta: number; deltaPct: number } => {
  const delta = comparison - baseline;
  const deltaPct = baseline !== 0 ? ((comparison - baseline) / baseline) * 100 : 0;
  return { delta, deltaPct };
};

// ============================================================================
// Sub-Components
// ============================================================================

const EmptyState = ({ onRefresh }: { onRefresh: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-gray-400">
    <Scale size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-gray-600 mb-2">Select Two Scenarios to Compare</h3>
    <p className="text-sm text-gray-500 mb-4 text-center max-w-md">
      Choose a baseline scenario and a comparison scenario from the dropdowns above to see
      a side-by-side analysis of DC Plan costs.
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
    <h3 className="text-lg font-semibold text-red-600 mb-2">Failed to Load Comparison</h3>
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

interface VarianceDisplayProps {
  delta: number;
  deltaPct: number;
  isCost?: boolean; // If true, positive = bad (red), negative = good (green)
  formatValue?: (val: number) => string;
}

const VarianceDisplay = ({ delta, deltaPct, isCost = false, formatValue }: VarianceDisplayProps) => {
  const isPositive = delta > 0;
  const isNegative = delta < 0;
  const isNeutral = delta === 0;

  // For costs: positive delta (increase) is red, negative (decrease) is green
  // For rates: positive delta (increase) is green, negative (decrease) is red
  let colorClass = 'text-gray-500';
  let Icon = Minus;

  if (!isNeutral) {
    if (isCost) {
      colorClass = isPositive ? 'text-red-600' : 'text-green-600';
    } else {
      colorClass = isPositive ? 'text-green-600' : 'text-red-600';
    }
    Icon = isPositive ? TrendingUp : TrendingDown;
  }

  const formattedDelta = formatValue ? formatValue(Math.abs(delta)) : Math.abs(delta).toFixed(2);
  const sign = isPositive ? '+' : isNegative ? '-' : '';

  return (
    <div className={`flex items-center ${colorClass}`}>
      <Icon size={16} className="mr-1" />
      <span className="font-medium">
        {sign}{formattedDelta} ({sign}{Math.abs(deltaPct).toFixed(1)}%)
      </span>
    </div>
  );
};

interface MetricCardProps {
  title: string;
  icon: React.ReactNode;
  baselineValue: string;
  comparisonValue: string;
  variance: { delta: number; deltaPct: number };
  isCost?: boolean;
  formatVariance?: (val: number) => string;
  loading?: boolean;
}

const MetricCard = ({
  title,
  icon,
  baselineValue,
  comparisonValue,
  variance,
  isCost = false,
  formatVariance,
  loading = false,
}: MetricCardProps) => (
  <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-200">
    <div className="flex items-center justify-between mb-3">
      <span className="text-sm font-medium text-gray-500">{title}</span>
      <div className="p-2 rounded-lg bg-gray-50 text-gray-600">
        {icon}
      </div>
    </div>
    {loading ? (
      <div className="space-y-2">
        <div className="h-6 w-24 bg-gray-200 rounded animate-pulse" />
        <div className="h-6 w-24 bg-gray-200 rounded animate-pulse" />
      </div>
    ) : (
      <>
        <div className="grid grid-cols-2 gap-4 mb-3">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide">Baseline</p>
            <p className="text-lg font-bold text-gray-900">{baselineValue}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide">Comparison</p>
            <p className="text-lg font-bold text-gray-900">{comparisonValue}</p>
          </div>
        </div>
        <div className="pt-3 border-t border-gray-100">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Variance</p>
          <VarianceDisplay
            delta={variance.delta}
            deltaPct={variance.deltaPct}
            isCost={isCost}
            formatValue={formatVariance}
          />
        </div>
      </>
    )}
  </div>
);

// ============================================================================
// Main Component
// ============================================================================

export default function ScenarioCostComparison() {
  // State for workspace/scenario selection
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('');
  const [baselineScenarioId, setBaselineScenarioId] = useState<string>('');
  const [comparisonScenarioId, setComparisonScenarioId] = useState<string>('');

  // State for results
  const [comparisonData, setComparisonData] = useState<DCPlanComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Derived data
  const baselineAnalytics = comparisonData?.analytics.find(a => a.scenario_id === baselineScenarioId);
  const comparisonAnalytics = comparisonData?.analytics.find(a => a.scenario_id === comparisonScenarioId);

  // Fetch workspaces on mount
  useEffect(() => {
    fetchWorkspaces();
  }, []);

  // Fetch scenarios when workspace changes
  useEffect(() => {
    if (selectedWorkspaceId) {
      fetchScenarios(selectedWorkspaceId);
    } else {
      setScenarios([]);
      setBaselineScenarioId('');
      setComparisonScenarioId('');
    }
  }, [selectedWorkspaceId]);

  // Fetch comparison when both scenarios are selected
  useEffect(() => {
    if (baselineScenarioId && comparisonScenarioId && baselineScenarioId !== comparisonScenarioId) {
      fetchComparison();
    } else {
      setComparisonData(null);
    }
  }, [baselineScenarioId, comparisonScenarioId, selectedWorkspaceId]);

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
      // Auto-select first two completed scenarios if available
      const completedScenarios = data.filter(s => s.status === 'completed');
      if (completedScenarios.length >= 2) {
        setBaselineScenarioId(completedScenarios[0].id);
        setComparisonScenarioId(completedScenarios[1].id);
      } else if (completedScenarios.length === 1) {
        setBaselineScenarioId(completedScenarios[0].id);
        setComparisonScenarioId('');
      } else {
        setBaselineScenarioId('');
        setComparisonScenarioId('');
      }
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const fetchComparison = async () => {
    if (!selectedWorkspaceId || !baselineScenarioId || !comparisonScenarioId) return;

    setLoading(true);
    setError(null);
    try {
      const data = await compareDCPlanAnalytics(
        selectedWorkspaceId,
        [baselineScenarioId, comparisonScenarioId]
      );
      setComparisonData(data);
    } catch (err) {
      console.error('Failed to fetch comparison:', err);
      setError(err instanceof Error ? err.message : 'Failed to load comparison data');
      setComparisonData(null);
    } finally {
      setLoading(false);
    }
  };

  const completedScenarios = scenarios.filter(s => s.status === 'completed');

  // Build year-by-year data
  const yearByYearData = React.useMemo(() => {
    if (!baselineAnalytics || !comparisonAnalytics) return [];

    const baselineByYear = new Map<number, ContributionYearSummary>();
    const comparisonByYear = new Map<number, ContributionYearSummary>();

    baselineAnalytics.contribution_by_year.forEach(y => baselineByYear.set(y.year, y));
    comparisonAnalytics.contribution_by_year.forEach(y => comparisonByYear.set(y.year, y));

    const allYears = new Set([...baselineByYear.keys(), ...comparisonByYear.keys()]);
    const sortedYears = Array.from(allYears).sort((a, b) => a - b);

    return sortedYears.map(year => {
      const baseline = baselineByYear.get(year);
      const comparison = comparisonByYear.get(year);

      return {
        year,
        baseline,
        comparison,
        metrics: {
          participationRate: {
            baseline: baseline?.participation_rate ?? 0,
            comparison: comparison?.participation_rate ?? 0,
          },
          avgDeferralRate: {
            baseline: baseline?.average_deferral_rate ?? 0,
            comparison: comparison?.average_deferral_rate ?? 0,
          },
          employerMatch: {
            baseline: baseline?.total_employer_match ?? 0,
            comparison: comparison?.total_employer_match ?? 0,
          },
          employerCore: {
            baseline: baseline?.total_employer_core ?? 0,
            comparison: comparison?.total_employer_core ?? 0,
          },
          totalEmployerCost: {
            baseline: baseline?.total_employer_cost ?? 0,
            comparison: comparison?.total_employer_cost ?? 0,
          },
        },
      };
    });
  }, [baselineAnalytics, comparisonAnalytics]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Compare DC Plan Costs</h1>
          <p className="text-gray-500 mt-1">
            Side-by-side analysis of retirement plan costs between scenarios
          </p>
        </div>
        <button
          onClick={fetchComparison}
          disabled={!baselineScenarioId || !comparisonScenarioId || loading}
          className="flex items-center px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <Loader2 size={16} className="mr-2 animate-spin" />
          ) : (
            <RefreshCw size={16} className="mr-2" />
          )}
          Refresh
        </button>
      </div>

      {/* Workspace & Scenario Selection */}
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Workspace Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Workspace</label>
            <div className="relative">
              <select
                value={selectedWorkspaceId}
                onChange={(e) => setSelectedWorkspaceId(e.target.value)}
                className="w-full pl-4 pr-10 py-2.5 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm focus:ring-2 focus:ring-fidelity-green focus:border-fidelity-green appearance-none"
              >
                <option value="">Select workspace...</option>
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>{ws.name}</option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Baseline Scenario Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              <span className="inline-flex items-center">
                <span className="w-3 h-3 bg-blue-500 rounded-full mr-2"></span>
                Baseline Scenario
              </span>
            </label>
            <div className="relative">
              <select
                value={baselineScenarioId}
                onChange={(e) => setBaselineScenarioId(e.target.value)}
                disabled={loadingScenarios || completedScenarios.length === 0}
                className="w-full pl-4 pr-10 py-2.5 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm focus:ring-2 focus:ring-fidelity-green focus:border-fidelity-green appearance-none disabled:bg-gray-50 disabled:text-gray-500"
              >
                <option value="">Select baseline...</option>
                {completedScenarios.map((s) => (
                  <option key={s.id} value={s.id} disabled={s.id === comparisonScenarioId}>
                    {s.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Comparison Scenario Selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              <span className="inline-flex items-center">
                <span className="w-3 h-3 bg-orange-500 rounded-full mr-2"></span>
                Comparison Scenario
              </span>
            </label>
            <div className="relative">
              <select
                value={comparisonScenarioId}
                onChange={(e) => setComparisonScenarioId(e.target.value)}
                disabled={loadingScenarios || completedScenarios.length === 0}
                className="w-full pl-4 pr-10 py-2.5 border border-gray-300 rounded-lg bg-white text-gray-900 text-sm focus:ring-2 focus:ring-fidelity-green focus:border-fidelity-green appearance-none disabled:bg-gray-50 disabled:text-gray-500"
              >
                <option value="">Select comparison...</option>
                {completedScenarios.map((s) => (
                  <option key={s.id} value={s.id} disabled={s.id === baselineScenarioId}>
                    {s.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>
        </div>

        {loadingScenarios && (
          <div className="flex items-center justify-center mt-4 text-gray-500">
            <Loader2 size={16} className="animate-spin mr-2" />
            Loading scenarios...
          </div>
        )}

        {!loadingScenarios && completedScenarios.length === 0 && selectedWorkspaceId && (
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-700 text-sm">
            No completed scenarios found in this workspace. Run a simulation first to compare results.
          </div>
        )}
      </div>

      {/* Content Area */}
      {error && <ErrorState message={error} onRetry={fetchComparison} />}

      {!error && !baselineAnalytics && !comparisonAnalytics && !loading && (
        <EmptyState onRefresh={fetchWorkspaces} />
      )}

      {(loading || (baselineAnalytics && comparisonAnalytics)) && (
        <>
          {/* Summary KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <MetricCard
              title="Participation Rate"
              icon={<Users size={20} />}
              baselineValue={formatPercent(baselineAnalytics?.participation_rate ?? 0)}
              comparisonValue={formatPercent(comparisonAnalytics?.participation_rate ?? 0)}
              variance={calculateVariance(
                baselineAnalytics?.participation_rate ?? 0,
                comparisonAnalytics?.participation_rate ?? 0
              )}
              formatVariance={(v) => formatPercent(v)}
              loading={loading}
            />

            <MetricCard
              title="Average Deferral Rate"
              icon={<Percent size={20} />}
              baselineValue={formatDeferralRate(baselineAnalytics?.average_deferral_rate ?? 0)}
              comparisonValue={formatDeferralRate(comparisonAnalytics?.average_deferral_rate ?? 0)}
              variance={calculateVariance(
                (baselineAnalytics?.average_deferral_rate ?? 0) * 100,
                (comparisonAnalytics?.average_deferral_rate ?? 0) * 100
              )}
              formatVariance={(v) => `${v.toFixed(2)}%`}
              loading={loading}
            />

            <MetricCard
              title="Total Employer Match"
              icon={<DollarSign size={20} />}
              baselineValue={formatCurrency(baselineAnalytics?.total_employer_match ?? 0)}
              comparisonValue={formatCurrency(comparisonAnalytics?.total_employer_match ?? 0)}
              variance={calculateVariance(
                baselineAnalytics?.total_employer_match ?? 0,
                comparisonAnalytics?.total_employer_match ?? 0
              )}
              isCost={true}
              formatVariance={formatCurrency}
              loading={loading}
            />

            <MetricCard
              title="Total Employer Core"
              icon={<DollarSign size={20} />}
              baselineValue={formatCurrency(baselineAnalytics?.total_employer_core ?? 0)}
              comparisonValue={formatCurrency(comparisonAnalytics?.total_employer_core ?? 0)}
              variance={calculateVariance(
                baselineAnalytics?.total_employer_core ?? 0,
                comparisonAnalytics?.total_employer_core ?? 0
              )}
              isCost={true}
              formatVariance={formatCurrency}
              loading={loading}
            />

            <MetricCard
              title="Total Employer Cost"
              icon={<DollarSign size={20} />}
              baselineValue={formatCurrency(baselineAnalytics?.total_employer_cost ?? 0)}
              comparisonValue={formatCurrency(comparisonAnalytics?.total_employer_cost ?? 0)}
              variance={calculateVariance(
                baselineAnalytics?.total_employer_cost ?? 0,
                comparisonAnalytics?.total_employer_cost ?? 0
              )}
              isCost={true}
              formatVariance={formatCurrency}
              loading={loading}
            />
          </div>

          {/* Year-by-Year Breakdown Table */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Year-by-Year Breakdown</h2>
              <p className="text-sm text-gray-500 mt-1">
                Detailed comparison of metrics for each simulation year
              </p>
            </div>

            {loading ? (
              <div className="p-8 flex items-center justify-center">
                <Loader2 size={24} className="animate-spin text-gray-400" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Year</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Metric</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        <span className="inline-flex items-center">
                          <span className="w-2 h-2 bg-blue-500 rounded-full mr-2"></span>
                          Baseline
                        </span>
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        <span className="inline-flex items-center">
                          <span className="w-2 h-2 bg-orange-500 rounded-full mr-2"></span>
                          Comparison
                        </span>
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Variance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {yearByYearData.map((yearData, yearIdx) => {
                      const metrics = [
                        {
                          name: 'Participation Rate',
                          baseline: yearData.metrics.participationRate.baseline,
                          comparison: yearData.metrics.participationRate.comparison,
                          format: formatPercent,
                          isCost: false,
                        },
                        {
                          name: 'Avg Deferral Rate',
                          baseline: yearData.metrics.avgDeferralRate.baseline,
                          comparison: yearData.metrics.avgDeferralRate.comparison,
                          format: formatDeferralRate,
                          isCost: false,
                          rawMultiplier: 100, // For variance calc
                        },
                        {
                          name: 'Employer Match',
                          baseline: yearData.metrics.employerMatch.baseline,
                          comparison: yearData.metrics.employerMatch.comparison,
                          format: formatCurrency,
                          isCost: true,
                        },
                        {
                          name: 'Employer Core',
                          baseline: yearData.metrics.employerCore.baseline,
                          comparison: yearData.metrics.employerCore.comparison,
                          format: formatCurrency,
                          isCost: true,
                        },
                        {
                          name: 'Total Employer Cost',
                          baseline: yearData.metrics.totalEmployerCost.baseline,
                          comparison: yearData.metrics.totalEmployerCost.comparison,
                          format: formatCurrency,
                          isCost: true,
                        },
                      ];

                      return metrics.map((metric, metricIdx) => {
                        const variance = calculateVariance(
                          metric.rawMultiplier ? metric.baseline * metric.rawMultiplier : metric.baseline,
                          metric.rawMultiplier ? metric.comparison * metric.rawMultiplier : metric.comparison
                        );

                        return (
                          <tr
                            key={`${yearData.year}-${metric.name}`}
                            className={yearIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}
                          >
                            {metricIdx === 0 && (
                              <td
                                rowSpan={metrics.length}
                                className="px-6 py-3 text-sm font-semibold text-gray-900 border-r border-gray-200"
                              >
                                {yearData.year}
                              </td>
                            )}
                            <td className="px-6 py-3 text-sm text-gray-700">{metric.name}</td>
                            <td className="px-6 py-3 text-sm text-gray-900 text-right font-medium">
                              {metric.format(metric.baseline)}
                            </td>
                            <td className="px-6 py-3 text-sm text-gray-900 text-right font-medium">
                              {metric.format(metric.comparison)}
                            </td>
                            <td className="px-6 py-3 text-right">
                              <VarianceDisplay
                                delta={variance.delta}
                                deltaPct={variance.deltaPct}
                                isCost={metric.isCost}
                                formatValue={metric.isCost ? formatCurrency : (v) => `${v.toFixed(2)}%`}
                              />
                            </td>
                          </tr>
                        );
                      });
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Grand Totals */}
          {!loading && baselineAnalytics && comparisonAnalytics && (
            <div className="bg-gradient-to-r from-fidelity-green to-fidelity-dark rounded-xl shadow-sm p-6 text-white">
              <h2 className="text-lg font-semibold mb-4">Grand Totals Summary</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white/10 rounded-lg p-4">
                  <p className="text-sm text-white/80 mb-1">Total Employer Match</p>
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-bold">
                      {formatCurrency(comparisonAnalytics.total_employer_match)}
                    </span>
                    <span className="text-sm text-white/70">
                      vs {formatCurrency(baselineAnalytics.total_employer_match)}
                    </span>
                  </div>
                </div>
                <div className="bg-white/10 rounded-lg p-4">
                  <p className="text-sm text-white/80 mb-1">Total Employer Core</p>
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-bold">
                      {formatCurrency(comparisonAnalytics.total_employer_core)}
                    </span>
                    <span className="text-sm text-white/70">
                      vs {formatCurrency(baselineAnalytics.total_employer_core)}
                    </span>
                  </div>
                </div>
                <div className="bg-white/10 rounded-lg p-4">
                  <p className="text-sm text-white/80 mb-1">Total Employer Cost</p>
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-bold">
                      {formatCurrency(comparisonAnalytics.total_employer_cost)}
                    </span>
                    <span className="text-sm text-white/70">
                      vs {formatCurrency(baselineAnalytics.total_employer_cost)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
