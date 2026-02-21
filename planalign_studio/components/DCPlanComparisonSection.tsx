import React, { useMemo } from 'react';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  Loader2, AlertCircle, DollarSign, TrendingUp, TrendingDown
} from 'lucide-react';
import { DCPlanComparisonResponse } from '../services/api';

// --- Props ---

interface DCPlanComparisonSectionProps {
  comparisonData: DCPlanComparisonResponse | null;
  loading: boolean;
  error: string | null;
  scenarioNames: string[];
  scenarioColors: Record<string, string>;
}

// --- Recharts Data Shapes ---

interface TrendDataPoint {
  year: number;
  [scenarioName: string]: number | undefined;
}

interface DistributionDataPoint {
  bucket: string;
  [scenarioName: string]: number | string | undefined;
}

interface ContributionBreakdownPoint {
  name: string;
  employee: number;
  match: number;
  core: number;
}

interface SummaryMetricRow {
  metric: string;
  unit: 'percent' | 'currency';
  favorableDirection: 'higher' | 'lower';
  values: Record<string, number>;
  deltas: Record<string, number>;
  deltaPcts: Record<string, number>;
}

// --- Formatting Utilities ---

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

// --- Contribution bar colors ---

const CONTRIBUTION_COLORS = {
  employee: '#0088FE',
  match: '#00C49F',
  core: '#FFBB28',
};

// --- Tooltip style ---

const tooltipStyle = {
  backgroundColor: '#fff',
  borderRadius: '8px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
};

// --- Component ---

export default function DCPlanComparisonSection({
  comparisonData,
  loading,
  error,
  scenarioNames,
  scenarioColors,
}: DCPlanComparisonSectionProps) {

  // --- Data Transformations ---

  const buildTrendData = (
    metricKey: string,
    multiplier: number = 1
  ): TrendDataPoint[] => {
    if (!comparisonData || comparisonData.analytics.length === 0) return [];

    const allYears = new Set<number>();
    comparisonData.analytics.forEach(a => {
      if (a.contribution_by_year) {
        a.contribution_by_year.forEach(c => allYears.add(c.year));
      }
    });

    return Array.from(allYears).sort().map(year => {
      const point: TrendDataPoint = { year };
      comparisonData.analytics.forEach(a => {
        const scenarioName = comparisonData.scenario_names[a.scenario_id] || a.scenario_id;
        const yearData = a.contribution_by_year?.find(c => c.year === year);
        if (yearData) {
          point[scenarioName] = (yearData as any)[metricKey] * multiplier;
        }
      });
      return point;
    });
  };

  const employerCostTrendData = useMemo(
    () => buildTrendData('employer_cost_rate'),
    [comparisonData]
  );

  const participationTrendData = useMemo(
    () => buildTrendData('participation_rate'),
    [comparisonData]
  );

  const deferralTrendData = useMemo(
    () => buildTrendData('average_deferral_rate', 100),
    [comparisonData]
  );

  // --- Deferral Distribution Chart Data ---

  const BUCKET_ORDER = ['0%', '1%', '2%', '3%', '4%', '5%', '6%', '7%', '8%', '9%', '10%+'];

  const availableDistributionYears = useMemo((): number[] => {
    if (!comparisonData || comparisonData.analytics.length === 0) return [];

    const yearSets = comparisonData.analytics.map(a => {
      if (a.deferral_distribution_by_year && a.deferral_distribution_by_year.length > 0) {
        return new Set(a.deferral_distribution_by_year.map(d => d.year));
      }
      return new Set<number>();
    });

    if (yearSets.every(s => s.size === 0)) return [];

    // Intersection of all non-empty year sets
    const nonEmpty = yearSets.filter(s => s.size > 0);
    if (nonEmpty.length === 0) return [];

    const common = [...nonEmpty[0]].filter(y => nonEmpty.every(s => s.has(y)));
    return common.sort();
  }, [comparisonData]);

  const [selectedDistributionYear, setSelectedDistributionYear] = React.useState<number | null>(null);

  // Default to final year when available years change
  React.useEffect(() => {
    if (availableDistributionYears.length > 0) {
      setSelectedDistributionYear(availableDistributionYears[availableDistributionYears.length - 1]);
    } else {
      setSelectedDistributionYear(null);
    }
  }, [availableDistributionYears.join(',')]);

  const distributionChartData = useMemo((): DistributionDataPoint[] => {
    if (!comparisonData || comparisonData.analytics.length === 0) return [];

    const useByYear = selectedDistributionYear !== null && availableDistributionYears.length > 0;

    return BUCKET_ORDER.map(bucket => {
      const point: DistributionDataPoint = { bucket };

      comparisonData.analytics.forEach(a => {
        const scenarioName = comparisonData.scenario_names[a.scenario_id] || a.scenario_id;

        let distribution = a.deferral_rate_distribution;
        if (useByYear && a.deferral_distribution_by_year && a.deferral_distribution_by_year.length > 0) {
          const yearData = a.deferral_distribution_by_year.find(d => d.year === selectedDistributionYear);
          if (yearData) {
            distribution = yearData.distribution;
          }
        }

        const bucketData = distribution?.find(b => b.bucket === bucket);
        point[scenarioName] = bucketData?.percentage ?? 0;
      });

      return point;
    });
  }, [comparisonData, selectedDistributionYear, availableDistributionYears]);

  const contributionBreakdownData = useMemo((): ContributionBreakdownPoint[] => {
    if (!comparisonData || comparisonData.analytics.length === 0) return [];

    return comparisonData.analytics
      .filter(a => a.contribution_by_year && a.contribution_by_year.length > 0)
      .map(a => {
        const finalYear = a.contribution_by_year[a.contribution_by_year.length - 1];
        const scenarioName = comparisonData.scenario_names[a.scenario_id] || a.scenario_id;
        return {
          name: scenarioName,
          employee: finalYear.total_employee_contributions || 0,
          match: finalYear.total_employer_match || 0,
          core: finalYear.total_employer_core || 0,
        };
      });
  }, [comparisonData]);

  const finalYear = useMemo((): number | null => {
    if (!comparisonData || comparisonData.analytics.length === 0) return null;
    const firstAnalytics = comparisonData.analytics[0];
    if (!firstAnalytics.contribution_by_year || firstAnalytics.contribution_by_year.length === 0) return null;
    return firstAnalytics.contribution_by_year[firstAnalytics.contribution_by_year.length - 1].year;
  }, [comparisonData]);

  const summaryRows = useMemo((): SummaryMetricRow[] => {
    if (!comparisonData || comparisonData.analytics.length === 0) return [];

    const metrics: Array<{
      metric: string;
      unit: 'percent' | 'currency';
      favorableDirection: 'higher' | 'lower';
      getValue: (a: typeof comparisonData.analytics[0]) => number;
    }> = [
      {
        metric: 'Participation Rate',
        unit: 'percent',
        favorableDirection: 'higher',
        getValue: a => a.participation_rate || 0,
      },
      {
        metric: 'Avg Deferral Rate',
        unit: 'percent',
        favorableDirection: 'higher',
        getValue: a => (a.average_deferral_rate || 0) * 100,
      },
      {
        metric: 'Employer Cost Rate',
        unit: 'percent',
        favorableDirection: 'lower',
        getValue: a => a.employer_cost_rate || 0,
      },
      {
        metric: 'Total Contributions',
        unit: 'currency',
        favorableDirection: 'lower',
        getValue: a => a.total_all_contributions || 0,
      },
    ];

    const baselineAnalytics = comparisonData.analytics[0];
    const baselineName = comparisonData.scenario_names[baselineAnalytics.scenario_id] || baselineAnalytics.scenario_id;

    return metrics.map(m => {
      const values: Record<string, number> = {};
      const deltas: Record<string, number> = {};
      const deltaPcts: Record<string, number> = {};

      const baselineValue = m.getValue(baselineAnalytics);

      comparisonData.analytics.forEach(a => {
        const name = comparisonData.scenario_names[a.scenario_id] || a.scenario_id;
        const value = m.getValue(a);
        values[name] = value;

        if (name !== baselineName) {
          deltas[name] = value - baselineValue;
          deltaPcts[name] = baselineValue !== 0
            ? ((value - baselineValue) / baselineValue) * 100
            : 0;
        }
      });

      return {
        metric: m.metric,
        unit: m.unit,
        favorableDirection: m.favorableDirection,
        values,
        deltas,
        deltaPcts,
      };
    });
  }, [comparisonData]);

  // --- Loading / Error / Empty States ---

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="text-center">
          <Loader2 size={32} className="animate-spin text-fidelity-green mx-auto mb-3" />
          <p className="text-gray-500 text-sm">Loading DC plan data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="text-center">
          <AlertCircle size={32} className="text-red-400 mx-auto mb-3" />
          <p className="text-red-600 text-sm font-medium">Failed to load DC plan data</p>
          <p className="text-gray-500 text-xs mt-1">{error}</p>
        </div>
      </div>
    );
  }

  if (!comparisonData || comparisonData.analytics.length === 0) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="text-center">
          <DollarSign size={32} className="text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">No DC plan data available</p>
        </div>
      </div>
    );
  }

  // --- Helpers ---

  const isFavorable = (row: SummaryMetricRow, delta: number): boolean => {
    if (row.favorableDirection === 'higher') return delta > 0;
    return delta < 0;
  };

  const formatDelta = (row: SummaryMetricRow, delta: number): string => {
    const sign = delta >= 0 ? '+' : '';
    if (row.unit === 'percent') {
      return `${sign}${delta.toFixed(1)}%`;
    }
    return `${sign}${formatCurrency(delta)}`;
  };

  const formatValue = (row: SummaryMetricRow, value: number): string => {
    if (row.unit === 'percent') {
      return formatPercent(value);
    }
    return formatCurrency(value);
  };

  const baselineName = scenarioNames[0];

  // --- Render ---

  return (
    <div className="space-y-6">
      {/* Employer Cost Rate Trends — Full Width */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-800">Employer Cost Rate Trends</h3>
        <p className="text-sm text-gray-500 mb-4">Employer cost as % of total compensation</p>
        <div className="h-80">
          {employerCostTrendData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={employerCostTrendData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis dataKey="year" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" tickFormatter={v => formatPercent(v)} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number) => [formatPercent(value, 2), '']}
                />
                <Legend verticalAlign="top" height={36} />
                {scenarioNames.map(name => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={scenarioColors[name]}
                    strokeWidth={3}
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400">
              <p>No employer cost data available</p>
            </div>
          )}
        </div>
      </div>

      {/* Participation & Deferral Rate Trends — Side by Side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Participation Rate */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-800">Participation Rate Trends</h3>
          <p className="text-sm text-gray-500 mb-4">Percentage of eligible employees enrolled</p>
          <div className="h-80">
            {participationTrendData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={participationTrendData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis dataKey="year" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" domain={[0, 100]} tickFormatter={v => formatPercent(v, 0)} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(value: number) => [formatPercent(value, 1), '']}
                  />
                  <Legend verticalAlign="top" height={36} />
                  {scenarioNames.map(name => (
                    <Line
                      key={name}
                      type="monotone"
                      dataKey={name}
                      stroke={scenarioColors[name]}
                      strokeWidth={3}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400">
                <p>No participation data available</p>
              </div>
            )}
          </div>
        </div>

        {/* Deferral Rate */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-800">Average Deferral Rate Trends</h3>
          <p className="text-sm text-gray-500 mb-4">Average employee deferral rate</p>
          <div className="h-80">
            {deferralTrendData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={deferralTrendData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis dataKey="year" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" tickFormatter={v => formatPercent(v)} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(value: number) => [formatPercent(value, 2), '']}
                  />
                  <Legend verticalAlign="top" height={36} />
                  {scenarioNames.map(name => (
                    <Line
                      key={name}
                      type="monotone"
                      dataKey={name}
                      stroke={scenarioColors[name]}
                      strokeWidth={3}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400">
                <p>No deferral rate data available</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Deferral Rate Distribution Comparison — Full Width */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-gray-800">Deferral Rate Distribution</h3>
            <p className="text-sm text-gray-500">
              Percentage of enrolled employees by deferral rate bucket
            </p>
          </div>
          {availableDistributionYears.length > 1 && (
            <select
              value={selectedDistributionYear ?? ''}
              onChange={e => setSelectedDistributionYear(Number(e.target.value))}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500"
            >
              {availableDistributionYears.map(y => (
                <option key={y} value={y}>
                  {y}{y === availableDistributionYears[availableDistributionYears.length - 1] ? ' (Final)' : ''}
                </option>
              ))}
            </select>
          )}
          {availableDistributionYears.length === 1 && selectedDistributionYear !== null && (
            <span className="text-sm text-gray-500">Year {selectedDistributionYear}</span>
          )}
        </div>
        <div className="h-80">
          {distributionChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distributionChartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis dataKey="bucket" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" tickFormatter={v => formatPercent(v, 0)} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number, name: string) => [formatPercent(value, 1), name]}
                />
                <Legend verticalAlign="top" height={36} />
                {scenarioNames.map(name => (
                  <Bar
                    key={name}
                    dataKey={name}
                    fill={scenarioColors[name]}
                    radius={[4, 4, 0, 0]}
                    barSize={scenarioNames.length > 4 ? 12 : scenarioNames.length > 2 ? 20 : 30}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400">
              <p>No deferral distribution data available</p>
            </div>
          )}
        </div>
      </div>

      {/* Contribution Breakdown — Full Width */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-800">Contribution Breakdown</h3>
        <p className="text-sm text-gray-500 mb-4">
          {finalYear ? `Final year (${finalYear})` : 'Final year'} — Employee, Employer Match, and Employer Core
        </p>
        <div className="h-80">
          {contributionBreakdownData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={contributionBreakdownData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                <XAxis dataKey="name" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" tickFormatter={v => formatCurrency(v)} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value: number) => [formatCurrency(value), '']}
                />
                <Legend verticalAlign="top" height={36} />
                <Bar
                  dataKey="employee"
                  name="Employee Contributions"
                  fill={CONTRIBUTION_COLORS.employee}
                  radius={[4, 4, 0, 0]}
                  barSize={scenarioNames.length > 4 ? 16 : 30}
                />
                <Bar
                  dataKey="match"
                  name="Employer Match"
                  fill={CONTRIBUTION_COLORS.match}
                  radius={[4, 4, 0, 0]}
                  barSize={scenarioNames.length > 4 ? 16 : 30}
                />
                <Bar
                  dataKey="core"
                  name="Employer Core"
                  fill={CONTRIBUTION_COLORS.core}
                  radius={[4, 4, 0, 0]}
                  barSize={scenarioNames.length > 4 ? 16 : 30}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400">
              <p>No contribution data available</p>
            </div>
          )}
        </div>
      </div>

      {/* Summary Comparison Table — Full Width */}
      {summaryRows.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">DC Plan Summary Comparison</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Metric
                  </th>
                  {scenarioNames.map((name, idx) => (
                    <th
                      key={name}
                      className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider"
                      style={{ color: scenarioColors[name] }}
                    >
                      {name}{idx === 0 ? ' (Baseline)' : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {summaryRows.map(row => (
                  <tr key={row.metric} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {row.metric}
                    </td>
                    {scenarioNames.map((name, idx) => {
                      const value = row.values[name];
                      const delta = row.deltas[name];
                      const isBaseline = idx === 0;

                      return (
                        <td key={name} className="px-4 py-3">
                          <div className="text-gray-800 font-semibold">
                            {formatValue(row, value)}
                          </div>
                          {!isBaseline && delta !== undefined && (
                            <span
                              className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${
                                isFavorable(row, delta)
                                  ? 'bg-green-50 text-green-700'
                                  : 'bg-red-50 text-red-700'
                              }`}
                            >
                              {formatDelta(row, delta)}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
