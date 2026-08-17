/**
 * Annual forfeitures under one vesting schedule, across all simulation years,
 * for a selected set of scenarios (issue #489).
 *
 * This is a reporting view, not the current-vs-proposed comparison in
 * VestingAnalysis. It replaces the manual loop of one run per year per
 * scenario, transcribed into a spreadsheet by hand.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  AlertCircle, Download, Info, Loader2, RefreshCw,
} from 'lucide-react';
import {
  getForfeitureProjection,
  ForfeitureProjectionResponse,
  Scenario,
  VestingScheduleInfo,
  VestingScheduleType,
} from '../services/api';
import { MAX_SCENARIO_SELECTION } from '../constants';
import { useChartTheme } from '../hooks/useChartTheme';

const STORAGE_KEY_PREFIX = 'planalign_forfeiture_';

interface Props {
  readonly workspaceId: string;
  readonly completedScenarios: Scenario[];
  readonly schedules: VestingScheduleInfo[];
}

const formatCurrency = (value: number): string => {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

const formatExact = (value: number): string =>
  value.toLocaleString('en-US', { style: 'currency', currency: 'USD' });

function loadSelection(workspaceId: string): string[] | null {
  try {
    const stored = localStorage.getItem(`${STORAGE_KEY_PREFIX}${workspaceId}`);
    return stored ? JSON.parse(stored) : null;
  } catch (e) {
    console.warn('Failed to load forfeiture selection:', e);
    return null;
  }
}

function saveSelection(workspaceId: string, ids: string[]): void {
  try {
    localStorage.setItem(`${STORAGE_KEY_PREFIX}${workspaceId}`, JSON.stringify(ids));
  } catch (e) {
    console.warn('Failed to save forfeiture selection:', e);
  }
}

/** Rows for the chart: one entry per year, one field per scenario. */
function buildChartRows(
  data: ForfeitureProjectionResponse,
  cumulative: boolean
): Array<Record<string, number | null>> {
  const running: Record<string, number> = {};
  return data.years.map(year => {
    const row: Record<string, number | null> = { year };
    for (const series of data.scenarios) {
      const match = series.years.find(r => r.simulation_year === year);
      // A year the scenario does not cover, and a first year with no prior-year
      // contribution basis, are both gaps — never plotted as a $0 bar.
      if (!match || !match.has_prior_year_basis) {
        row[series.scenario_id] = null;
        continue;
      }
      running[series.scenario_id] =
        (running[series.scenario_id] ?? 0) + match.forfeited_amount;
      row[series.scenario_id] = cumulative
        ? running[series.scenario_id]
        : match.forfeited_amount;
    }
    return row;
  });
}

function toCsv(data: ForfeitureProjectionResponse, cumulative: boolean): string {
  const header = ['Year', ...data.scenarios.map(s => s.scenario_name)];
  const rows = buildChartRows(data, cumulative).map(row => [
    String(row.year),
    ...data.scenarios.map(s => {
      const value = row[s.scenario_id];
      return value === null ? 'no prior-year basis' : value.toFixed(2);
    }),
  ]);
  const totals = [
    'Total',
    ...data.scenarios.map(s => s.total_forfeited.toFixed(2)),
  ];
  return [header, ...rows, totals]
    .map(cells => cells.map(cell => `"${cell.replace(/"/g, '""')}"`).join(','))
    .join('\n');
}

export default function ForfeitureProjection({
  workspaceId,
  completedScenarios,
  schedules,
}: Props) {
  const chartTheme = useChartTheme();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [scheduleType, setScheduleType] = useState<VestingScheduleType>('graded_5_year');
  const [requireHoursCredit, setRequireHoursCredit] = useState(false);
  const [hoursThreshold, setHoursThreshold] = useState(1000);
  const [cumulative, setCumulative] = useState(false);
  const [data, setData] = useState<ForfeitureProjectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Restore persisted selection, dropping ids that are no longer completed.
  useEffect(() => {
    if (!workspaceId) return;
    const valid = new Set(completedScenarios.map(s => s.id));
    const saved = (loadSelection(workspaceId) ?? []).filter(id => valid.has(id));
    setSelectedIds(saved.length > 0 ? saved : completedScenarios.slice(0, 1).map(s => s.id));
    setData(null);
  }, [workspaceId, completedScenarios]);

  useEffect(() => {
    if (workspaceId && selectedIds.length > 0) saveSelection(workspaceId, selectedIds);
  }, [workspaceId, selectedIds]);

  // Colour follows the scenario, not its position, so deselecting one series
  // never repaints the others.
  const colorMap = useMemo(() => {
    const map: Record<string, string> = {};
    selectedIds.forEach((id, index) => {
      map[id] = chartTheme.colorAt(index);
    });
    return map;
  }, [selectedIds]);

  const runReport = useCallback(async () => {
    if (!workspaceId || selectedIds.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      setData(
        await getForfeitureProjection(workspaceId, {
          scenarioIds: selectedIds,
          scheduleType,
          requireHoursCredit,
          hoursThreshold,
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load forfeitures');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, selectedIds, scheduleType, requireHoursCredit, hoursThreshold]);

  const toggleScenario = (id: string) => {
    setSelectedIds(prev => {
      if (prev.includes(id)) return prev.filter(item => item !== id);
      if (prev.length >= MAX_SCENARIO_SELECTION) return prev;
      return [...prev, id];
    });
    setData(null);
  };

  const chartRows = useMemo(
    () => (data ? buildChartRows(data, cumulative) : []),
    [data, cumulative]
  );

  const downloadCsv = () => {
    if (!data) return;
    const blob = new Blob([toCsv(data, cumulative)], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `forfeitures_${scheduleType}_${cumulative ? 'cumulative' : 'annual'}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const atSelectionLimit = selectedIds.length >= MAX_SCENARIO_SELECTION;

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label htmlFor="forfeiture-schedule" className="block text-sm font-medium text-ink-muted mb-1">
              Vesting Schedule
            </label>
            <select
              id="forfeiture-schedule"
              value={scheduleType}
              onChange={e => {
                setScheduleType(e.target.value as VestingScheduleType);
                setData(null);
              }}
              className="w-full bg-surface-raised border border-border-strong rounded-lg px-3 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
            >
              {schedules.map(schedule => (
                <option key={schedule.schedule_type} value={schedule.schedule_type}>
                  {schedule.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="forfeiture-hours" className="block text-sm font-medium text-ink-muted mb-1">
              Hours Threshold
            </label>
            <input
              id="forfeiture-hours"
              type="number"
              min={0}
              max={2080}
              value={hoursThreshold}
              disabled={!requireHoursCredit}
              onChange={e => {
                setHoursThreshold(Number(e.target.value));
                setData(null);
              }}
              className="w-full bg-surface-raised border border-border-strong rounded-lg px-3 py-2 text-sm shadow-sm disabled:bg-surface-subtle disabled:text-ink-subtle"
            />
          </div>

          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm text-ink-muted pb-2">
              <input
                type="checkbox"
                checked={requireHoursCredit}
                onChange={e => {
                  setRequireHoursCredit(e.target.checked);
                  setData(null);
                }}
                className="rounded border-border-strong text-fidelity-green focus:ring-fidelity-green"
              />
              Require hours credit
            </label>
          </div>
        </div>

        {/* Scenario multi-select */}
        <fieldset>
          <legend className="block text-sm font-medium text-ink-muted mb-2">
            Scenarios{' '}
            <span className="font-normal text-ink-muted">
              ({selectedIds.length} of {MAX_SCENARIO_SELECTION} max)
            </span>
          </legend>
          {completedScenarios.length === 0 ? (
            <p className="text-sm text-ink-muted">No completed scenarios in this workspace.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {completedScenarios.map(scenario => {
                const checked = selectedIds.includes(scenario.id);
                return (
                  <label
                    key={scenario.id}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm cursor-pointer transition-colors ${
                      checked
                        ? 'border-border-strong bg-surface-subtle text-ink'
                        : 'border-border text-ink-muted hover:bg-surface-subtle'
                    } ${!checked && atSelectionLimit ? 'opacity-40 cursor-not-allowed' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!checked && atSelectionLimit}
                      onChange={() => toggleScenario(scenario.id)}
                      className="rounded border-border-strong text-fidelity-green focus:ring-fidelity-green"
                    />
                    {checked && (
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: colorMap[scenario.id] }}
                      />
                    )}
                    {scenario.name}
                  </label>
                );
              })}
            </div>
          )}
        </fieldset>

        <div className="flex items-center gap-3">
          <button
            onClick={runReport}
            disabled={loading || selectedIds.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark disabled:bg-surface-disabled transition-colors"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            {loading ? 'Running...' : 'Run Report'}
          </button>
          {data && (
            <button
              onClick={downloadCsv}
              className="flex items-center gap-2 px-4 py-2 bg-surface-raised border border-border-strong rounded-lg text-sm font-medium text-ink-muted hover:bg-surface-subtle transition-colors"
            >
              <Download size={16} />
              Export CSV
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 bg-danger-surface border border-danger-border rounded-lg text-sm text-danger-ink">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {data && data.skipped.length > 0 && (
        <div className="flex items-start gap-2 p-4 bg-warning-surface border border-warning-border rounded-lg text-sm text-warning-ink">
          <Info size={16} className="mt-0.5 shrink-0" />
          <div>
            {data.skipped.map(item => (
              <div key={item.scenario_id}>
                <span className="font-medium">{item.scenario_name}</span> excluded — {item.reason}
              </div>
            ))}
          </div>
        </div>
      )}

      {data && data.scenarios.length > 0 && (
        <>
          <div className="bg-surface-raised p-6 rounded-xl shadow-sm border border-border">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-ink">
                  {cumulative ? 'Cumulative' : 'Annual'} Forfeitures
                </h3>
                <p className="text-sm text-ink-muted">
                  Under {data.schedule.name}, by simulation year
                </p>
              </div>
              <div className="flex rounded-lg border border-border-strong overflow-hidden text-sm">
                {(['annual', 'cumulative'] as const).map(mode => (
                  <button
                    key={mode}
                    onClick={() => setCumulative(mode === 'cumulative')}
                    className={`px-3 py-1.5 capitalize transition-colors ${
                      (mode === 'cumulative') === cumulative
                        ? 'bg-fidelity-green text-ink-inverse'
                        : 'bg-surface-raised text-ink-muted hover:bg-surface-subtle'
                    }`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                {cumulative ? (
                  <AreaChart data={chartRows} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                    <XAxis dataKey="year" stroke={chartTheme.axis.line} fontSize={12} />
                    <YAxis stroke={chartTheme.axis.line} fontSize={12} tickFormatter={formatCurrency} />
                    <Tooltip contentStyle={chartTheme.tooltip.contentStyle} formatter={(value: number) => formatExact(value)} />
                    {/* Legend text wears text ink, not the series colour: the palette's
                        lighter slots don't clear 3:1 on white. The swatch carries identity. */}
                    <Legend formatter={(value: string) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                    {data.scenarios.map(series => (
                      <Area
                        key={series.scenario_id}
                        dataKey={series.scenario_id}
                        name={series.scenario_name}
                        stroke={colorMap[series.scenario_id]}
                        fill={colorMap[series.scenario_id]}
                        fillOpacity={0.15}
                        strokeWidth={2}
                        connectNulls={false}
                      />
                    ))}
                  </AreaChart>
                ) : (
                  <BarChart data={chartRows} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={chartTheme.grid.line} />
                    <XAxis dataKey="year" stroke={chartTheme.axis.line} fontSize={12} />
                    <YAxis stroke={chartTheme.axis.line} fontSize={12} tickFormatter={formatCurrency} />
                    <Tooltip contentStyle={chartTheme.tooltip.contentStyle} cursor={chartTheme.tooltip.cursorStyle} formatter={(value: number) => formatExact(value)} />
                    {/* Legend text wears text ink, not the series colour: the palette's
                        lighter slots don't clear 3:1 on white. The swatch carries identity. */}
                    <Legend formatter={(value: string) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                    {data.scenarios.map(series => (
                      <Bar
                        key={series.scenario_id}
                        dataKey={series.scenario_id}
                        name={series.scenario_name}
                        fill={colorMap[series.scenario_id]}
                        radius={[4, 4, 0, 0]}
                      />
                    ))}
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>

          {/* Years x scenarios table */}
          <div className="bg-surface-raised rounded-xl shadow-sm border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-surface-subtle border-b border-border">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-ink-muted">Year</th>
                    {data.scenarios.map(series => (
                      <th
                        key={series.scenario_id}
                        className="px-4 py-3 text-right font-medium text-ink-muted"
                      >
                        <span className="inline-flex items-center gap-2">
                          <span
                            className="w-2.5 h-2.5 rounded-full"
                            style={{ backgroundColor: colorMap[series.scenario_id] }}
                          />
                          {series.scenario_name}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {chartRows.map(row => (
                    <tr key={row.year} className="hover:bg-surface-subtle">
                      <td className="px-4 py-2.5 text-ink">{row.year}</td>
                      {data.scenarios.map(series => {
                        const value = row[series.scenario_id];
                        const covered = series.years.some(
                          r => r.simulation_year === row.year
                        );
                        return (
                          <td
                            key={series.scenario_id}
                            className="px-4 py-2.5 text-right tabular-nums text-ink-muted"
                          >
                            {value !== null && formatExact(value)}
                            {value === null && covered && (
                              <span className="text-ink-subtle italic text-xs">
                                no prior-year basis
                              </span>
                            )}
                            {value === null && !covered && (
                              <span className="text-ink-subtle">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-surface-subtle border-t border-border">
                  <tr>
                    <td className="px-4 py-3 font-medium text-ink">Total</td>
                    {data.scenarios.map(series => (
                      <td
                        key={series.scenario_id}
                        className="px-4 py-3 text-right font-medium tabular-nums text-ink"
                      >
                        {formatExact(series.total_forfeited)}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
            <p className="px-4 py-3 text-xs text-ink-muted border-t border-border">
              A scenario&apos;s first simulation year has no prior year to source employer
              contributions from, so it is reported as &ldquo;no prior-year basis&rdquo;
              rather than $0. A dash means the scenario does not cover that year.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
