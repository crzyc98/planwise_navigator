import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  ArrowLeft, Download, Users, TrendingUp, Calendar, DollarSign,
  AlertCircle, Loader2, LayoutGrid, ChevronDown, ChevronUp
} from 'lucide-react';
import {
  getSimulationResults,
  SimulationResults,
  Scenario,
  listScenarios,
  listWorkspaces,
  compareDCPlanAnalytics,
  DCPlanComparisonResponse,
} from '../services/api';
import { useChartTheme } from '../hooks/useChartTheme';
import DCPlanComparisonSection from './DCPlanComparisonSection';

interface ScenarioData {
  scenario: Scenario;
  results: SimulationResults | null;
  loading: boolean;
  error: string | null;
}

export default function ScenarioComparison() {
  const chartTheme = useChartTheme();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [scenarioData, setScenarioData] = useState<Map<string, ScenarioData>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedMetrics, setExpandedMetrics] = useState(true);
  const [expandedDCPlan, setExpandedDCPlan] = useState(true);
  const [dcPlanData, setDcPlanData] = useState<DCPlanComparisonResponse | null>(null);
  const [dcPlanLoading, setDcPlanLoading] = useState(false);
  const [dcPlanError, setDcPlanError] = useState<string | null>(null);

  // Get scenario IDs from URL params
  const scenarioIds = searchParams.get('scenarios')?.split(',').filter(Boolean) || [];

  useEffect(() => {
    const loadScenarios = async () => {
      if (scenarioIds.length === 0) {
        setError('No scenarios specified for comparison');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        // First, get all workspaces to find the scenarios
        const workspaces = await listWorkspaces();

        // Find scenarios across all workspaces
        const scenarioPromises = workspaces.map(async (ws) => {
          const scenarios = await listScenarios(ws.id);
          return scenarios.filter(s => scenarioIds.includes(s.id));
        });

        const scenarioArrays = await Promise.all(scenarioPromises);
        const allScenarios = scenarioArrays.flat();

        // Initialize scenario data map
        const dataMap = new Map<string, ScenarioData>();

        for (const scenario of allScenarios) {
          dataMap.set(scenario.id, {
            scenario,
            results: null,
            loading: true,
            error: null,
          });
        }

        setScenarioData(new Map(dataMap));

        // Load results for each scenario
        for (const scenario of allScenarios) {
          try {
            const results = await getSimulationResults(scenario.id);
            setScenarioData(prev => {
              const newMap = new Map(prev);
              const existing = newMap.get(scenario.id);
              if (existing) {
                newMap.set(scenario.id, { scenario: existing.scenario, results, loading: false, error: null });
              }
              return newMap;
            });
          } catch (err: any) {
            // Check if the scenario has any completed runs even if status shows failed
            const errorMessage = err.message || 'Failed to load results';
            const isMissingResults = errorMessage.includes('not completed') || errorMessage.includes('No results');

            setScenarioData(prev => {
              const newMap = new Map(prev);
              const existing = newMap.get(scenario.id);
              if (existing) {
                newMap.set(scenario.id, {
                  scenario: existing.scenario,
                  results: existing.results,
                  loading: false,
                  error: isMissingResults
                    ? `${scenario.name} has not been run yet or has no results`
                    : errorMessage,
                });
              }
              return newMap;
            });
          }
        }
      } catch (err: any) {
        setError(err.message || 'Failed to load scenarios');
      } finally {
        setLoading(false);
      }
    };

    loadScenarios();
  }, [scenarioIds.join(',')]);

  // Get all scenarios with results (explicitly typed for TypeScript)
  const scenariosWithResults: Array<ScenarioData & { results: SimulationResults }> = Array.from(scenarioData.values())
    .filter((d): d is ScenarioData & { results: SimulationResults } => d.results !== null);

  // Fetch DC plan comparison data when scenarios are loaded
  useEffect(() => {
    const fetchDCPlanData = async () => {
      if (scenariosWithResults.length < 2) return;

      // Derive workspace ID from the first scenario
      const workspaceId = scenariosWithResults[0].scenario.workspace_id;
      if (!workspaceId) return;

      const ids = scenariosWithResults.map(d => d.scenario.id);

      setDcPlanLoading(true);
      setDcPlanError(null);

      try {
        const data = await compareDCPlanAnalytics(workspaceId, ids);
        setDcPlanData(data);
      } catch (err: any) {
        console.error('Failed to fetch DC plan comparison:', err);
        setDcPlanError(err.message || 'Failed to load DC plan comparison data');
      } finally {
        setDcPlanLoading(false);
      }
    };

    fetchDCPlanData();
  }, [scenariosWithResults.map(d => d.scenario.id).join(',')]);

  // Build scenario color map (shared between workforce and DC plan charts)
  const scenarioColors: Record<string, string> = {};
  scenariosWithResults.forEach((d, idx) => {
    scenarioColors[d.scenario.name] = chartTheme.colorAt(idx);
  });

  // Build comparison data for charts
  const buildComparisonData = () => {
    if (scenariosWithResults.length === 0) return { workforce: [], events: [] };

    // Get all years across all scenarios
    const allYears = new Set<number>();
    scenariosWithResults.forEach(d => {
      d.results?.workforce_progression?.forEach(r => allYears.add(r.simulation_year));
    });

    const years = Array.from(allYears).sort((a, b) => a - b);

    // Build workforce comparison data
    const workforce = years.map(year => {
      const dataPoint: any = { year };
      scenariosWithResults.forEach(d => {
        const yearData = d.results?.workforce_progression?.find(r => r.simulation_year === year);
        dataPoint[d.scenario.name] = yearData?.headcount || 0;
      });
      return dataPoint;
    });

    // Build event comparison data
    const events = years.map(year => {
      const dataPoint: any = { year };
      scenariosWithResults.forEach((d, idx) => {
        const yearIndex = d.results?.workforce_progression?.findIndex(r => r.simulation_year === year) ?? -1;
        if (yearIndex >= 0 && d.results?.event_trends) {
          const hires = d.results.event_trends['hire']?.[yearIndex] || 0;
          const terminations = d.results.event_trends['termination']?.[yearIndex] || 0;
          dataPoint[`${d.scenario.name} Hires`] = hires;
          dataPoint[`${d.scenario.name} Terms`] = terminations;
        }
      });
      return dataPoint;
    });

    return { workforce, events };
  };

  const comparisonData = buildComparisonData();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <Loader2 size={48} className="animate-spin text-fidelity-green mx-auto mb-4" />
          <p className="text-ink-muted">Loading scenario data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <AlertCircle size={48} className="text-danger-ink mb-4" />
        <h3 className="text-lg font-semibold text-danger-ink mb-2">Error Loading Comparison</h3>
        <p className="text-sm text-ink-muted mb-4">{error}</p>
        <button
          onClick={() => navigate('/batch')}
          className="px-4 py-2 bg-surface-subtle text-ink-muted rounded-lg hover:bg-surface-disabled"
        >
          Back to Batches
        </button>
      </div>
    );
  }

  if (scenarioIds.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <LayoutGrid size={48} className="text-ink-subtle mb-4" />
        <h3 className="text-lg font-semibold text-ink-muted mb-2">No Scenarios to Compare</h3>
        <p className="text-sm text-ink-muted mb-4">Select scenarios from a batch to compare.</p>
        <button
          onClick={() => navigate('/batch')}
          className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-dark"
        >
          Go to Batches
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <button
            onClick={() => navigate(-1)}
            className="mr-4 p-2 text-ink-muted hover:text-ink-muted hover:bg-surface-subtle rounded-lg"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-ink">Scenario Comparison</h1>
            <p className="text-ink-muted mt-1">
              Comparing {scenariosWithResults.length} scenario{scenariosWithResults.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {scenarioIds.length === 2 && (
            <Link
              to={`/analytics/diff?a=${scenarioIds[0]}&b=${scenarioIds[1]}`}
              className="flex items-center px-4 py-2 bg-fidelity-green rounded-lg text-ink-inverse hover:bg-fidelity-dark"
            >
              Diff A vs B
            </Link>
          )}
          <Link
            to="/analytics"
            className="flex items-center px-4 py-2 bg-surface-raised border border-border-strong rounded-lg text-ink-muted hover:bg-surface-subtle"
          >
            <LayoutGrid size={16} className="mr-2" />
            Full Analytics
          </Link>
        </div>
      </div>

      {/* Scenario Legend */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-4">
        <div className="flex flex-wrap gap-4">
          {scenariosWithResults.map((d, idx) => (
            <div key={d.scenario.id} className="flex items-center">
              <div
                className="w-4 h-4 rounded mr-2"
                style={{ backgroundColor: chartTheme.colorAt(idx) }}
              />
              <span className="text-sm font-medium text-ink-muted">{d.scenario.name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Key Metrics Comparison Table */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border overflow-hidden">
        <button
          onClick={() => setExpandedMetrics(!expandedMetrics)}
          className="w-full px-6 py-4 flex items-center justify-between bg-surface-subtle border-b border-border hover:bg-surface-subtle transition-colors"
        >
          <h2 className="text-lg font-semibold text-ink flex items-center">
            <LayoutGrid size={20} className="mr-2 text-ink-muted" />
            Key Metrics Comparison
          </h2>
          {expandedMetrics ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </button>

        {expandedMetrics && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-surface-subtle">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">
                    Metric
                  </th>
                  {scenariosWithResults.map((d, idx) => (
                    <th
                      key={d.scenario.id}
                      className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider"
                      style={{ color: chartTheme.colorAt(idx) }}
                    >
                      {d.scenario.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bg-surface-raised divide-y divide-border">
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">
                    <div className="flex items-center">
                      <Users size={16} className="mr-2 text-ink-subtle" />
                      Final Headcount
                    </div>
                  </td>
                  {scenariosWithResults.map(d => (
                    <td key={d.scenario.id} className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted font-semibold">
                      {d.results?.final_headcount.toLocaleString() || '—'}
                    </td>
                  ))}
                </tr>
                <tr className="bg-surface-subtle">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">
                    <div className="flex items-center">
                      <TrendingUp size={16} className="mr-2 text-ink-subtle" />
                      Total Growth
                    </div>
                  </td>
                  {scenariosWithResults.map(d => {
                    const growthSign = d.results && d.results.total_growth_pct >= 0 ? '+' : '';
                    const growthDisplay = d.results ? `${growthSign}${d.results.total_growth_pct.toFixed(1)}%` : '\u2014';
                    return (
                    <td key={d.scenario.id} className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className={d.results && d.results.total_growth_pct >= 0 ? 'text-success-ink' : 'text-danger-ink'}>
                        {growthDisplay}
                      </span>
                    </td>
                    );
                  })}
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">
                    <div className="flex items-center">
                      <TrendingUp size={16} className="mr-2 text-ink-subtle" />
                      CAGR
                    </div>
                  </td>
                  {scenariosWithResults.map(d => (
                    <td key={d.scenario.id} className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted">
                      {d.results ? `${d.results.cagr.toFixed(2)}%` : '—'}
                    </td>
                  ))}
                </tr>
                <tr className="bg-surface-subtle">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">
                    <div className="flex items-center">
                      <Calendar size={16} className="mr-2 text-ink-subtle" />
                      Simulation Period
                    </div>
                  </td>
                  {scenariosWithResults.map(d => (
                    <td key={d.scenario.id} className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted">
                      {d.results ? `${d.results.start_year} - ${d.results.end_year}` : '—'}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-ink">
                    <div className="flex items-center">
                      <DollarSign size={16} className="mr-2 text-ink-subtle" />
                      Participation Rate
                    </div>
                  </td>
                  {scenariosWithResults.map(d => (
                    <td key={d.scenario.id} className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted">
                      {d.results ? `${(d.results.participation_rate * 100).toFixed(0)}%` : '—'}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Headcount Comparison Chart */}
        <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
          <h3 className="text-lg font-semibold text-ink mb-6">Headcount Over Time</h3>
          <div className="h-80">
            {comparisonData.workforce.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={comparisonData.workforce}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                  <XAxis dataKey="year" stroke={chartTheme.axis.line} />
                  <YAxis stroke={chartTheme.axis.line} />
                  <Tooltip
                    contentStyle={chartTheme.tooltip.contentStyle}
                    formatter={(value: number) => [value.toLocaleString(), '']}
                  />
                  <Legend verticalAlign="top" height={36} formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                  {scenariosWithResults.map((d, idx) => (
                    <Line
                      key={d.scenario.id}
                      type="monotone"
                      dataKey={d.scenario.name}
                      stroke={chartTheme.colorAt(idx)}
                      strokeWidth={3}
                      dot={{ r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-ink-subtle">
                <p>No workforce data available</p>
              </div>
            )}
          </div>
        </div>

        {/* Final Headcount Bar Chart */}
        <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
          <h3 className="text-lg font-semibold text-ink mb-6">Final Headcount Comparison</h3>
          <div className="h-80">
            {scenariosWithResults.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={scenariosWithResults.map((d, idx) => ({
                    name: d.scenario.name,
                    headcount: d.results?.final_headcount || 0,
                    fill: chartTheme.colorAt(idx),
                  }))}
                  layout="vertical"
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke={chartTheme.grid.line} />
                  <XAxis type="number" stroke={chartTheme.axis.line} />
                  <YAxis type="category" dataKey="name" stroke={chartTheme.axis.line} width={120} />
                  <Tooltip
                    contentStyle={chartTheme.tooltip.contentStyle}
                    formatter={(value: number) => [value.toLocaleString(), 'Headcount']}
                  />
                  <Bar dataKey="headcount" radius={[0, 4, 4, 0]}>
                    {scenariosWithResults.map((d, idx) => (
                      <rect
                        key={d.scenario.id}
                        fill={chartTheme.colorAt(idx)}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-ink-subtle">
                <p>No data available</p>
              </div>
            )}
          </div>
        </div>

        {/* Growth Rate Comparison */}
        <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
          <h3 className="text-lg font-semibold text-ink mb-6">Growth Rate Comparison</h3>
          <div className="h-80">
            {scenariosWithResults.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={scenariosWithResults.map((d, idx) => ({
                    name: d.scenario.name,
                    growth: d.results?.total_growth_pct || 0,
                    cagr: d.results?.cagr || 0,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                  <XAxis dataKey="name" stroke={chartTheme.axis.line} />
                  <YAxis stroke={chartTheme.axis.line} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={chartTheme.tooltip.contentStyle}
                    formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name === 'growth' ? 'Total Growth' : 'CAGR']}
                  />
                  <Legend verticalAlign="top" height={36} formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                  <Bar dataKey="growth" name="Total Growth" fill={chartTheme.semantic.primary} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="cagr" name="CAGR" fill={chartTheme.colorAt(2)} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-ink-subtle">
                <p>No data available</p>
              </div>
            )}
          </div>
        </div>

        {/* Participation Rate Comparison */}
        <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
          <h3 className="text-lg font-semibold text-ink mb-6">Plan Participation Rate</h3>
          <div className="h-80">
            {scenariosWithResults.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={scenariosWithResults.map((d, idx) => ({
                    name: d.scenario.name,
                    participation: (d.results?.participation_rate || 0) * 100,
                    fill: chartTheme.colorAt(idx),
                  }))}
                  layout="vertical"
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke={chartTheme.grid.line} />
                  <XAxis type="number" stroke={chartTheme.axis.line} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                  <YAxis type="category" dataKey="name" stroke={chartTheme.axis.line} width={120} />
                  <Tooltip
                    contentStyle={chartTheme.tooltip.contentStyle}
                    formatter={(value: number) => [`${value.toFixed(0)}%`, 'Participation']}
                  />
                  <Bar dataKey="participation" radius={[0, 4, 4, 0]}>
                    {scenariosWithResults.map((d, idx) => (
                      <rect
                        key={d.scenario.id}
                        fill={chartTheme.colorAt(idx)}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-ink-subtle">
                <p>No data available</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* DC Plan Comparison Section */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border overflow-hidden">
        <button
          onClick={() => setExpandedDCPlan(!expandedDCPlan)}
          className="w-full px-6 py-4 flex items-center justify-between bg-surface-subtle border-b border-border hover:bg-surface-subtle transition-colors"
        >
          <h2 className="text-lg font-semibold text-ink flex items-center">
            <DollarSign size={20} className="mr-2 text-ink-muted" />
            DC Plan Comparison
          </h2>
          {expandedDCPlan ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </button>

        {expandedDCPlan && (
          <div className="p-6">
            <DCPlanComparisonSection
              comparisonData={dcPlanData}
              loading={dcPlanLoading}
              error={dcPlanError}
              scenarioNames={scenariosWithResults.map(d => d.scenario.name)}
              scenarioColors={scenarioColors}
            />
          </div>
        )}
      </div>

      {/* Loading states for individual scenarios */}
      {Array.from(scenarioData.values()).some(d => d.loading) && (
        <div className="bg-warning-surface border border-warning-border rounded-lg p-4">
          <div className="flex items-center">
            <Loader2 size={16} className="animate-spin text-warning-ink mr-2" />
            <span className="text-warning-ink text-sm">Loading additional scenario data...</span>
          </div>
        </div>
      )}

      {/* Errors for individual scenarios */}
      {Array.from(scenarioData.values()).filter(d => d.error).length > 0 && (
        <div className="bg-danger-surface border border-danger-border rounded-lg p-4">
          <div className="flex items-start">
            <AlertCircle size={16} className="text-danger-ink mr-2 mt-0.5" />
            <div>
              <p className="text-danger-ink text-sm font-medium">Some scenarios failed to load:</p>
              <ul className="text-danger-ink text-sm mt-1">
                {Array.from(scenarioData.values())
                  .filter(d => d.error)
                  .map(d => (
                    <li key={d.scenario.id}>
                      {d.scenario.name}: {d.error}
                    </li>
                  ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
