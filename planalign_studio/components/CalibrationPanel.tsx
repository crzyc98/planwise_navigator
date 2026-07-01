import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { SlidersHorizontal, Play, AlertCircle, Loader2, Database } from 'lucide-react';
import {
  runCalibration,
  CalibrationRunRequest,
  PerYearCompensationResult,
  ApiError,
  getWorkspace,
  analyzeCompensation,
  Workspace,
} from '../services/api';
import { extractCensusPath } from './config/ConfigContext';

interface CalibrationOutletContext {
  activeWorkspace: Workspace | null;
}

interface JobRange {
  level: number;
  name: string;
  min_compensation: number;
  max_compensation: number;
}

/**
 * Fast Compensation Calibration panel (Feature 105, US3).
 *
 * Sliders for the four headline levers (target growth, COLA, merit, new-hire
 * mix) trigger a comp-only calibration run and render per-year average-comp and
 * growth-vs-target charts. Values match the `planalign calibrate` CLI for the
 * same parameters.
 */

interface SliderConfig {
  key: 'target_growth_pct' | 'cola_rate' | 'merit_budget' | 'new_hire_mix_senior';
  label: string;
  min: number;
  max: number;
  step: number;
}

const SLIDERS: SliderConfig[] = [
  { key: 'target_growth_pct', label: 'Target Growth', min: 0, max: 0.1, step: 0.005 },
  { key: 'cola_rate', label: 'COLA', min: 0, max: 0.1, step: 0.005 },
  { key: 'merit_budget', label: 'Merit', min: 0, max: 0.1, step: 0.005 },
  { key: 'new_hire_mix_senior', label: 'New-Hire Senior Mix', min: 0, max: 1, step: 0.05 },
];

const pct = (v: number): string => `${(v * 100).toFixed(1)}%`;
const money = (v: number | null): string =>
  v === null ? '—' : `$${Math.round(v).toLocaleString()}`;
const growthPct = (v: number | null): string =>
  v === null ? '—' : `${v.toFixed(1)}%`;
const compactMoney = (v: number | null): string => {
  if (v === null) return '—';
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${Math.round(v).toLocaleString()}`;
};

/** Coerce any error (incl. FastAPI 422 detail arrays) to a display string. */
function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as unknown;
    if (Array.isArray(d)) {
      return d
        .map((item: any) =>
          item?.msg
            ? `${(item.loc ?? []).join('.')}: ${item.msg}`.replace(/^: /, '')
            : JSON.stringify(item)
        )
        .join('; ');
    }
    if (d && typeof d === 'object') return JSON.stringify(d);
    return (d as string) ?? `${e.status} ${e.statusText}`;
  }
  return e instanceof Error ? e.message : String(e);
}

export default function CalibrationPanel() {
  const [startYear, setStartYear] = useState(2025);
  const [endYear, setEndYear] = useState(2029);
  const [databasePath, setDatabasePath] = useState('');
  const [values, setValues] = useState<Record<string, number>>({
    target_growth_pct: 0.035,
    cola_rate: 0.02,
    merit_budget: 0.035,
    new_hire_mix_senior: 0.2,
  });
  const [results, setResults] = useState<PerYearCompensationResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The calibration page operates on the workspace you're already in -- it uses
  // the workspace's census for Match Census. No scenario needed (calibration
  // does not touch DC/scenario-specific behavior).
  const { activeWorkspace } = useOutletContext<CalibrationOutletContext>();
  const [censusPath, setCensusPath] = useState('');

  // Job Level Compensation Ranges via "Match Census" x scale (Feature 105) --
  // identical to the Workforce Parameters page, so the scale transfers to the
  // real simulation.
  const [lookbackYears, setLookbackYears] = useState(4);
  const [scaleFactor, setScaleFactor] = useState(1.8);
  const [jobRanges, setJobRanges] = useState<JobRange[]>([]);
  const [matchLoading, setMatchLoading] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);

  const setValue = (key: string, v: number) =>
    setValues((prev) => ({ ...prev, [key]: v }));

  // Resolve the active workspace's census path (fresh base_config).
  useEffect(() => {
    if (!activeWorkspace?.id) {
      setCensusPath('');
      return;
    }
    getWorkspace(activeWorkspace.id)
      .then((ws) => setCensusPath(extractCensusPath(ws.base_config) ?? ''))
      .catch(() => setCensusPath(extractCensusPath(activeWorkspace.base_config) ?? ''));
  }, [activeWorkspace?.id]);

  const handleMatchCensus = async () => {
    if (!activeWorkspace?.id || !censusPath) {
      setMatchError('This workspace has no census file uploaded yet.');
      return;
    }
    setMatchLoading(true);
    setMatchError(null);
    try {
      const result = await analyzeCompensation(activeWorkspace.id, censusPath, lookbackYears);
      const rows = result.has_level_data ? result.levels : result.suggested_levels;
      if (!rows || rows.length === 0) {
        setMatchError('Census analysis returned no per-level data.');
        return;
      }
      // Apply the scale exactly as the Workforce Parameters page does.
      const ranges: JobRange[] = rows.map((r: any) => ({
        level: r.level,
        name: r.name,
        min_compensation: Math.round((r.min_compensation ?? r.suggested_min) * scaleFactor),
        max_compensation: Math.round((r.max_compensation ?? r.suggested_max) * scaleFactor),
      }));
      setJobRanges(ranges);
    } catch (e) {
      setMatchError(errorText(e));
    } finally {
      setMatchLoading(false);
    }
  };

  const runCalibrate = async () => {
    setLoading(true);
    setError(null);
    try {
      const request: CalibrationRunRequest = {
        start_year: startYear,
        end_year: endYear,
        database_path: databasePath.trim() || null,
        params: {
          target_growth_pct: values.target_growth_pct,
          cola_rate: values.cola_rate,
          merit_budget: values.merit_budget,
          // The senior-mix slider maps to a two-level new-hire weighting; the
          // backend normalizes weights, so we send relative shares.
          new_hire_mix: {
            '1': 1 - values.new_hire_mix_senior,
            '4': values.new_hire_mix_senior,
          },
          job_level_compensation: jobRanges.length > 0 ? jobRanges : null,
        },
      };
      const response = await runCalibration(request);
      setResults(response.results);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  };

  const targetLine =
    results.length > 0 && results[0].target_growth_pct !== null
      ? results[0].target_growth_pct
      : null;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-2">
        <SlidersHorizontal className="text-fidelity-green" size={24} />
        <h1 className="text-2xl font-bold text-gray-900">Compensation Calibration</h1>
      </div>
      <p className="text-gray-600">
        Tune compensation policy and read per-year growth in minutes — exact vs. a
        full simulation, without rebuilding the retirement-plan stack.
      </p>

      {/* Controls */}
      <div className="bg-white rounded-lg shadow p-6 space-y-5">
        {/* Active workspace + its census (no selection needed) */}
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <Database size={16} className="text-gray-400" />
          <span>
            Workspace: <span className="font-medium text-gray-800">{activeWorkspace?.name ?? '—'}</span>
          </span>
          <span className="text-gray-300">|</span>
          <span>
            Census:{' '}
            {censusPath ? (
              <span className="font-mono text-xs text-gray-700">{censusPath}</span>
            ) : (
              <span className="text-amber-600">none uploaded</span>
            )}
          </span>
        </div>

        {/* Job Level Compensation Ranges: ratio + lookback + Match Census */}
        <div className="rounded-md border border-gray-200 p-4">
          <div className="text-sm font-medium text-gray-700 mb-2">
            Job Level Compensation Ranges
            <span className="ml-2 text-xs font-normal text-gray-500">
              (same Match Census × scale as Workforce Parameters — transfers to the real sim)
            </span>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <label className="block">
              <span className="text-xs text-gray-600">Scale (×)</span>
              <input
                type="number" step="0.1" min={0.1} max={3.0} value={scaleFactor}
                onChange={(e) => setScaleFactor(Number(e.target.value))}
                className="mt-1 w-24 rounded border-gray-300 shadow-sm"
              />
            </label>
            <label className="block">
              <span className="text-xs text-gray-600">Lookback (years)</span>
              <input
                type="number" min={0} max={20} value={lookbackYears}
                onChange={(e) => setLookbackYears(Number(e.target.value))}
                className="mt-1 w-28 rounded border-gray-300 shadow-sm"
              />
            </label>
            <button
              onClick={handleMatchCensus}
              disabled={matchLoading || !censusPath}
              className="inline-flex items-center gap-2 rounded bg-gray-700 px-3 py-2 text-white text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
            >
              {matchLoading ? <Loader2 className="animate-spin" size={16} /> : <Database size={16} />}
              Match Census
            </button>
          </div>
          {matchError && (
            <p className="mt-2 text-xs text-red-600">{matchError}</p>
          )}
          {jobRanges.length > 0 && (
            <table className="mt-3 text-xs w-full max-w-md">
              <thead className="text-gray-500">
                <tr><th className="text-left">Level</th><th className="text-right">Min</th><th className="text-right">Max</th></tr>
              </thead>
              <tbody>
                {jobRanges.map((r) => (
                  <tr key={r.level} className="border-t">
                    <td>{r.level} {r.name}</td>
                    <td className="text-right">{money(r.min_compensation)}</td>
                    <td className="text-right">{money(r.max_compensation)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {jobRanges.length === 0 && (
            <p className="mt-2 text-xs text-gray-500">
              No ranges set — calibration uses the scenario/config's existing ranges.
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Start Year</span>
            <input
              type="number"
              value={startYear}
              onChange={(e) => setStartYear(Number(e.target.value))}
              className="mt-1 w-full rounded border-gray-300 shadow-sm"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">End Year</span>
            <input
              type="number"
              value={endYear}
              onChange={(e) => setEndYear(Number(e.target.value))}
              className="mt-1 w-full rounded border-gray-300 shadow-sm"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Database (optional)</span>
            <input
              type="text"
              value={databasePath}
              placeholder="blank = copy of shared dev DB"
              onChange={(e) => setDatabasePath(e.target.value)}
              className="mt-1 w-full rounded border-gray-300 shadow-sm"
            />
            <span className="mt-1 block text-xs text-gray-500">
              Leave blank to calibrate an isolated copy of the shared dev database,
              or enter a path to a database that has had one full simulation.
            </span>
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {SLIDERS.map((s) => (
            <div key={s.key}>
              <div className="flex justify-between text-sm font-medium text-gray-700">
                <span>{s.label}</span>
                <span className="text-fidelity-green">{pct(values[s.key])}</span>
              </div>
              <input
                type="range"
                min={s.min}
                max={s.max}
                step={s.step}
                value={values[s.key]}
                onChange={(e) => setValue(s.key, Number(e.target.value))}
                className="w-full accent-fidelity-green"
              />
            </div>
          ))}
        </div>

        <button
          onClick={runCalibrate}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded bg-fidelity-green px-4 py-2 text-white font-medium hover:bg-fidelity-dark disabled:opacity-50"
        >
          {loading ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
          {loading ? 'Calibrating…' : 'Run Calibration'}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded bg-red-50 p-4 text-red-700">
          <AlertCircle size={20} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {results.length > 0 && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="font-semibold text-gray-800 mb-2">Average Compensation</h2>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={results}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="simulation_year" />
                  <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} />
                  <Tooltip formatter={(v: number) => money(v)} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="avg_compensation"
                    name="Avg Comp"
                    stroke="#00853F"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="font-semibold text-gray-800 mb-2">YoY Growth vs. Target</h2>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={results}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="simulation_year" />
                  <YAxis tickFormatter={(v) => `${v}%`} />
                  <Tooltip formatter={(v: number) => `${v?.toFixed(2)}%`} />
                  <Legend />
                  {targetLine !== null && (
                    <ReferenceLine
                      y={targetLine}
                      stroke="#d97706"
                      strokeDasharray="4 4"
                      label={{ value: `Target ${targetLine.toFixed(1)}%`, position: 'right' }}
                    />
                  )}
                  <Bar dataKey="yoy_growth_pct" name="YoY Growth" fill="#4CAF50" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Per-year table */}
          <div className="bg-white rounded-lg shadow overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-4 py-2 text-left">Year</th>
                  <th className="px-4 py-2 text-right">Avg Comp</th>
                  <th className="px-4 py-2 text-right">Avg Growth</th>
                  <th className="px-4 py-2 text-right">Δ vs Target</th>
                  <th className="px-4 py-2 text-right">Headcount</th>
                  <th className="px-4 py-2 text-right">HC Growth</th>
                  <th className="px-4 py-2 text-right">Total Comp</th>
                  <th className="px-4 py-2 text-right">Total Growth</th>
                  <th className="px-4 py-2 text-right">New-Hire Gap</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.simulation_year} className="border-t">
                    <td className="px-4 py-2">{r.simulation_year}</td>
                    <td className="px-4 py-2 text-right">{money(r.avg_compensation)}</td>
                    <td className="px-4 py-2 text-right">{growthPct(r.yoy_growth_pct)}</td>
                    <td className="px-4 py-2 text-right">
                      {r.growth_delta_pct === null
                        ? '—'
                        : `${r.growth_delta_pct >= 0 ? '+' : ''}${r.growth_delta_pct.toFixed(1)}%`}
                    </td>
                    <td className="px-4 py-2 text-right">{r.headcount.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right">{growthPct(r.headcount_growth_pct)}</td>
                    <td className="px-4 py-2 text-right">{compactMoney(r.total_compensation)}</td>
                    <td className="px-4 py-2 text-right">{growthPct(r.total_comp_growth_pct)}</td>
                    <td className="px-4 py-2 text-right">{money(r.new_hire_gap)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
