import React, { useState } from 'react';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { SlidersHorizontal, Play, AlertCircle, Loader2 } from 'lucide-react';
import {
  runCalibration,
  CalibrationRunRequest,
  PerYearCompensationResult,
  ApiError,
} from '../services/api';

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

  const setValue = (key: string, v: number) =>
    setValues((prev) => ({ ...prev, [key]: v }));

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
        },
      };
      const response = await runCalibration(request);
      setResults(response.results);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.detail ?? `${e.status} ${e.statusText}`);
      } else {
        setError(String(e));
      }
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
              placeholder="isolated calibration DB"
              onChange={(e) => setDatabasePath(e.target.value)}
              className="mt-1 w-full rounded border-gray-300 shadow-sm"
            />
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
                  <th className="px-4 py-2 text-right">YoY Growth</th>
                  <th className="px-4 py-2 text-right">Δ vs Target</th>
                  <th className="px-4 py-2 text-right">Headcount</th>
                  <th className="px-4 py-2 text-right">New-Hire Gap</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.simulation_year} className="border-t">
                    <td className="px-4 py-2">{r.simulation_year}</td>
                    <td className="px-4 py-2 text-right">{money(r.avg_compensation)}</td>
                    <td className="px-4 py-2 text-right">
                      {r.yoy_growth_pct === null ? '—' : `${r.yoy_growth_pct.toFixed(1)}%`}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {r.growth_delta_pct === null
                        ? '—'
                        : `${r.growth_delta_pct >= 0 ? '+' : ''}${r.growth_delta_pct.toFixed(1)}%`}
                    </td>
                    <td className="px-4 py-2 text-right">{r.headcount.toLocaleString()}</td>
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
