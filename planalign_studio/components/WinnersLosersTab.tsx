import React, { useState, useEffect } from 'react';
import { useSearchParams, useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import {
  Users, TrendingUp, TrendingDown, Minus,
  RefreshCw, AlertCircle, ChevronDown, Database, Loader2
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import {
  listScenarios,
  getWinnersLosersComparison,
  Scenario,
  WinnersLosersResponse,
  BandGroupResult,
  HeatmapCell,
} from '../services/api';

const EmptyState = ({ message, onRefresh }: { message: string; onRefresh: () => void }) => (
  <div className="flex flex-col items-center justify-center h-96 text-gray-400">
    <Database size={48} className="mb-4" />
    <h3 className="text-lg font-semibold text-gray-600 mb-2">No Data Available</h3>
    <p className="text-sm text-gray-500 mb-4 text-center max-w-md">{message}</p>
    <button
      onClick={onRefresh}
      className="flex items-center px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Refresh
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

const KPICard = ({ title, value, icon: Icon, color }: { title: string; value: string | number; icon: any; color: string }) => (
  <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-200 flex items-start justify-between">
    <div>
      <p className="text-sm font-medium text-gray-500">{title}</p>
      <h3 className="text-2xl font-bold text-gray-900 mt-1">{typeof value === 'number' ? value.toLocaleString() : value}</h3>
    </div>
    <div className={`p-2 rounded-lg bg-${color}-50 text-${color}-600`}>
      <Icon size={20} />
    </div>
  </div>
);

/**
 * Return a Tailwind background class for a heatmap cell based on net_pct.
 */
function heatmapColor(cell: HeatmapCell): string {
  if (cell.total === 0) return 'bg-gray-100';
  const pct = cell.net_pct;
  if (pct > 30) return 'bg-green-500 text-white';
  if (pct > 15) return 'bg-green-400 text-white';
  if (pct > 0) return 'bg-green-200';
  if (pct === 0) return 'bg-gray-100';
  if (pct > -15) return 'bg-red-200';
  if (pct > -30) return 'bg-red-400 text-white';
  return 'bg-red-500 text-white';
}

export default function WinnersLosersTab() {
  const { activeWorkspace } = useOutletContext<LayoutContextType>();
  const [searchParams, setSearchParams] = useSearchParams();

  // Scenario state
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [planA, setPlanA] = useState<string>('');
  const [planB, setPlanB] = useState<string>('');

  // Results state
  const [results, setResults] = useState<WinnersLosersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load scenarios when workspace changes
  useEffect(() => {
    if (activeWorkspace?.id) {
      fetchScenarios(activeWorkspace.id);
    } else {
      setScenarios([]);
      setPlanA('');
      setPlanB('');
      setResults(null);
    }
  }, [activeWorkspace?.id]);

  // Fetch comparison when plans change
  useEffect(() => {
    if (activeWorkspace?.id && planA && planB) {
      fetchComparison();
    } else {
      setResults(null);
    }
  }, [planA, planB, activeWorkspace?.id]);

  const fetchScenarios = async (workspaceId: string) => {
    setLoadingScenarios(true);
    try {
      const data = await listScenarios(workspaceId);
      setScenarios(data);
      const completed = data.filter(s => s.status === 'completed');

      // Restore from URL params or auto-select defaults
      const urlPlanA = searchParams.get('plan_a');
      const urlPlanB = searchParams.get('plan_b');

      if (urlPlanA && completed.find(s => s.id === urlPlanA)) {
        setPlanA(urlPlanA);
      } else if (completed.length > 0) {
        // Default Plan A: baseline scenario or first completed
        const baseline = completed.find(s => s.name.toLowerCase().includes('baseline'));
        setPlanA(baseline?.id || completed[0].id);
      }

      if (urlPlanB && completed.find(s => s.id === urlPlanB)) {
        setPlanB(urlPlanB);
      } else if (completed.length > 1) {
        // Default Plan B: first completed that isn't Plan A
        const selectedA = planA || (completed.find(s => s.name.toLowerCase().includes('baseline'))?.id || completed[0].id);
        const other = completed.find(s => s.id !== selectedA);
        setPlanB(other?.id || '');
      }
    } catch (err) {
      console.error('Failed to fetch scenarios:', err);
      setScenarios([]);
    } finally {
      setLoadingScenarios(false);
    }
  };

  const fetchComparison = async () => {
    if (!activeWorkspace?.id || !planA || !planB) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getWinnersLosersComparison(activeWorkspace.id, planA, planB);
      setResults(data);
      // Persist selections in URL
      setSearchParams({ plan_a: planA, plan_b: planB }, { replace: true });
    } catch (err: any) {
      console.error('Failed to fetch comparison:', err);
      setError(err.message || 'Failed to load comparison');
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  const completedScenarios = scenarios.filter(s => s.status === 'completed');

  // Band chart data transform
  const toBandChartData = (bands: BandGroupResult[]) =>
    bands.map(b => ({
      name: b.band_label,
      Winners: b.winners,
      Losers: b.losers,
      Neutral: b.neutral,
    }));

  // Tooltip formatter showing count and percentage
  const bandTooltipFormatter = (value: number, name: string, props: any) => {
    const total = (props.payload.Winners || 0) + (props.payload.Losers || 0) + (props.payload.Neutral || 0);
    const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
    return [`${value} (${pct}%)`, name];
  };

  // Extract unique bands for heatmap axes
  const ageBands = results ? [...new Set(results.heatmap.map(c => c.age_band))] : [];
  const tenureBands = results ? [...new Set(results.heatmap.map(c => c.tenure_band))] : [];

  const getHeatmapCell = (age: string, tenure: string): HeatmapCell | undefined =>
    results?.heatmap.find(c => c.age_band === age && c.tenure_band === tenure);

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Winners & Losers Analysis</h1>
          <p className="text-gray-500 mt-1">Compare plan designs by demographic impact.</p>
        </div>
        <div className="flex space-x-2">
          {/* Plan A Selector */}
          <div className="relative">
            <label className="absolute -top-5 left-0 text-xs font-medium text-gray-500">Plan A</label>
            <select
              value={planA}
              onChange={(e) => setPlanA(e.target.value)}
              disabled={loadingScenarios}
              className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[180px] disabled:bg-gray-50"
            >
              <option value="">{loadingScenarios ? 'Loading...' : 'Select Plan A'}</option>
              {completedScenarios.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
          </div>

          {/* Plan B Selector */}
          <div className="relative">
            <label className="absolute -top-5 left-0 text-xs font-medium text-gray-500">Plan B</label>
            <select
              value={planB}
              onChange={(e) => setPlanB(e.target.value)}
              disabled={loadingScenarios}
              className="appearance-none bg-white border border-gray-300 rounded-lg pl-3 pr-10 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm min-w-[180px] disabled:bg-gray-50"
            >
              <option value="">{loadingScenarios ? 'Loading...' : 'Select Plan B'}</option>
              {completedScenarios.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <ChevronDown size={16} className="absolute right-3 top-2.5 text-gray-400 pointer-events-none" />
          </div>

          <button
            onClick={fetchComparison}
            disabled={!planA || !planB || loading}
            className="flex items-center px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 text-gray-700 shadow-sm transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Content */}
      {completedScenarios.length < 2 ? (
        <EmptyState
          message="At least two completed scenarios are required to compare winners and losers."
          onRefresh={() => activeWorkspace?.id && fetchScenarios(activeWorkspace.id)}
        />
      ) : loading ? (
        <div className="flex items-center justify-center h-96">
          <Loader2 size={48} className="animate-spin text-fidelity-green" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={fetchComparison} />
      ) : !results ? (
        <EmptyState
          message="Select two completed scenarios above to compare winners and losers."
          onRefresh={() => activeWorkspace?.id && fetchScenarios(activeWorkspace.id)}
        />
      ) : (
        <>
          {/* Summary KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <KPICard title="Total Compared" value={results.total_compared} icon={Users} color="blue" />
            <KPICard title="Winners" value={results.total_winners} icon={TrendingUp} color="green" />
            <KPICard title="Losers" value={results.total_losers} icon={TrendingDown} color="red" />
            <KPICard title="Neutral" value={results.total_neutral} icon={Minus} color="gray" />
          </div>

          {/* Excluded employees note */}
          {results.total_excluded > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
              {results.total_excluded} employee(s) were excluded from comparison because they exist in only one scenario.
            </div>
          )}

          {/* Charts Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Age Band Chart */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Winners & Losers by Age Band</h3>
              <div className="h-80">
                {results.age_band_results.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={toBandChartData(results.age_band_results)} barSize={28}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="name" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" />
                      <Tooltip
                        cursor={{ fill: '#F3F4F6' }}
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                        formatter={bandTooltipFormatter}
                      />
                      <Legend verticalAlign="top" height={36} />
                      <Bar dataKey="Winners" fill="#22c55e" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Losers" fill="#ef4444" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Neutral" fill="#9ca3af" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No age band data available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Tenure Band Chart */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Winners & Losers by Tenure Band</h3>
              <div className="h-80">
                {results.tenure_band_results.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={toBandChartData(results.tenure_band_results)} barSize={28}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                      <XAxis dataKey="name" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" />
                      <Tooltip
                        cursor={{ fill: '#F3F4F6' }}
                        contentStyle={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                        formatter={bandTooltipFormatter}
                      />
                      <Legend verticalAlign="top" height={36} />
                      <Bar dataKey="Winners" fill="#22c55e" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Losers" fill="#ef4444" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Neutral" fill="#9ca3af" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    <p>No tenure band data available</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Heatmap: Age × Tenure */}
          {ageBands.length > 0 && tenureBands.length > 0 && (
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800 mb-6">Age × Tenure Heatmap</h3>
              <div className="overflow-x-auto">
                <div
                  className="grid gap-1"
                  style={{
                    gridTemplateColumns: `120px repeat(${tenureBands.length}, 1fr)`,
                  }}
                >
                  {/* Header row */}
                  <div className="text-xs font-medium text-gray-500 p-2" />
                  {tenureBands.map(tb => (
                    <div key={tb} className="text-xs font-medium text-gray-500 p-2 text-center">
                      {tb}
                    </div>
                  ))}

                  {/* Data rows */}
                  {ageBands.map(ab => (
                    <React.Fragment key={ab}>
                      <div className="text-xs font-medium text-gray-500 p-2 flex items-center">
                        {ab}
                      </div>
                      {tenureBands.map(tb => {
                        const cell = getHeatmapCell(ab, tb);
                        const isEmpty = !cell || cell.total === 0;
                        return (
                          <div
                            key={`${ab}-${tb}`}
                            className={`relative group rounded-md p-3 text-center cursor-default transition-colors ${
                              cell ? heatmapColor(cell) : 'bg-gray-100'
                            }`}
                          >
                            <span className="text-sm font-semibold">
                              {isEmpty ? '—' : cell!.total}
                            </span>
                            {/* Tooltip */}
                            <div className="absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block">
                              <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2 whitespace-nowrap shadow-lg">
                                {isEmpty ? (
                                  'No employees in this group'
                                ) : (
                                  <>
                                    {cell!.winners} Winners / {cell!.losers} Losers ({cell!.total} total)
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </React.Fragment>
                  ))}
                </div>
              </div>

              {/* Legend */}
              <div className="flex items-center justify-center gap-4 mt-4 text-xs text-gray-500">
                <div className="flex items-center gap-1">
                  <div className="w-4 h-4 rounded bg-green-400" /> Net Winners
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-4 h-4 rounded bg-gray-100 border border-gray-200" /> Neutral / Empty
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-4 h-4 rounded bg-red-400" /> Net Losers
                </div>
              </div>
            </div>
          )}

          {/* Consistency check */}
          {(() => {
            const ageTotal = results.age_band_results.reduce((s, b) => s + b.total, 0);
            const tenureTotal = results.tenure_band_results.reduce((s, b) => s + b.total, 0);
            const summaryTotal = results.total_winners + results.total_losers + results.total_neutral;
            if (ageTotal !== tenureTotal || ageTotal !== summaryTotal) {
              return (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                  Warning: Totals are inconsistent — age bands ({ageTotal}), tenure bands ({tenureTotal}), summary ({summaryTotal}).
                </div>
              );
            }
            return null;
          })()}
        </>
      )}
    </div>
  );
}
