import React, { useState, useEffect, useMemo } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { SlidersHorizontal, Play, AlertCircle, Loader2, Database, Sparkles, Plus, X } from 'lucide-react';
import {
  runCalibration,
  optimizeCalibration,
  CalibrationRunRequest,
  AutoCalibrationOutcome,
  PerYearCompensationResult,
  ApiError,
  getWorkspace,
  updateWorkspace,
  analyzeCompensation,
  solveCompensationGrowth,
  CompensationSolverResponse,
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
 * Tunes the REAL variables a production run uses: workforce growth
 * (simulation.target_growth_rate), COLA/merit (with the same solver as the
 * Compensation page's purple Calculate Settings button), the new-hire age
 * distribution (new_hire_age_distribution dbt var), and per-level comp ranges
 * via Match Census × scale (job_level_compensation dbt var). Every lever flows
 * through the exact config key / dbt var the full simulation consumes, so a
 * calibrated value transfers verbatim.
 */

interface SliderConfig {
  key: 'target_growth_pct' | 'workforce_growth_rate' | 'cola_rate' | 'merit_budget';
  label: string;
  hint?: string;
  min: number;
  max: number;
  step: number;
}

const SLIDERS: SliderConfig[] = [
  { key: 'target_growth_pct', label: 'Target Comp Growth', hint: 'avg-comp goal (delta column only)', min: 0, max: 0.1, step: 0.005 },
  { key: 'workforce_growth_rate', label: 'Workforce Growth', hint: 'headcount growth — sizes hiring, same as the real sim', min: -0.05, max: 0.1, step: 0.005 },
  { key: 'cola_rate', label: 'COLA', min: 0, max: 0.1, step: 0.005 },
  { key: 'merit_budget', label: 'Merit', min: 0, max: 0.1, step: 0.005 },
];

interface AgeRow {
  age: number;
  weight: number;
}

// Default seed distribution (dbt/seeds/config_new_hire_age_distribution.csv).
const DEFAULT_AGE_DIST: AgeRow[] = [
  { age: 22, weight: 0.05 },
  { age: 25, weight: 0.15 },
  { age: 28, weight: 0.2 },
  { age: 32, weight: 0.25 },
  { age: 35, weight: 0.15 },
  { age: 40, weight: 0.1 },
  { age: 45, weight: 0.08 },
  { age: 50, weight: 0.02 },
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
    workforce_growth_rate: 0.03,
    cola_rate: 0.02,
    merit_budget: 0.035,
  });
  const [results, setResults] = useState<PerYearCompensationResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New-hire age distribution override (real lever: flows through the same
  // new_hire_age_distribution dbt var the full simulation consumes).
  const [ageDistEnabled, setAgeDistEnabled] = useState(false);
  const [ageDist, setAgeDist] = useState<AgeRow[]>(DEFAULT_AGE_DIST);

  // "Purple button" solver: suggest COLA/merit for the target comp growth,
  // identical to the Compensation page's Calculate Settings.
  const [solverLoading, setSolverLoading] = useState(false);
  const [solverError, setSolverError] = useState<string | null>(null);
  const [solverResult, setSolverResult] = useState<CompensationSolverResponse | null>(null);

  // Auto-calibrate: iterated comp-only runs that SOLVE for COLA/merit given
  // the two targets (workforce growth is set exactly; comp growth is searched).
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoError, setAutoError] = useState<string | null>(null);
  const [autoOutcome, setAutoOutcome] = useState<AutoCalibrationOutcome | null>(null);
  const [tolerancePct, setTolerancePct] = useState(0.05);
  const [maxIterations, setMaxIterations] = useState(8);
  // 'new_hire_scale': solve the new-hire range scale so hiring dilution isn't
  // papered over with raises (COLA/merit stay as set). Needs Match Census.
  const [searchMode, setSearchMode] = useState<'new_hire_scale' | 'levers'>('new_hire_scale');

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
  // Unscaled (1.0×) census-derived ranges; the displayed/sent ranges are
  // derived from these × scale, so an auto-calibrated scale applies cleanly.
  const [baseRanges, setBaseRanges] = useState<JobRange[]>([]);
  const jobRanges = useMemo<JobRange[]>(
    () =>
      baseRanges.map((r) => ({
        ...r,
        min_compensation: Math.round(r.min_compensation * scaleFactor),
        max_compensation: Math.round(r.max_compensation * scaleFactor),
      })),
    [baseRanges, scaleFactor]
  );
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

  // Derive UNSCALED per-level ranges from the workspace census; the
  // displayed/sent ranges apply the Scale (×) input, exactly like the
  // Workforce Parameters page. Throws with a readable message on failure.
  const fetchBaseRanges = async (): Promise<JobRange[]> => {
    if (!activeWorkspace?.id || !censusPath) {
      throw new Error('This workspace has no census file uploaded yet.');
    }
    const result = await analyzeCompensation(activeWorkspace.id, censusPath, lookbackYears);
    const rows = result.has_level_data ? result.levels : result.suggested_levels;
    if (!rows || rows.length === 0) {
      throw new Error('Census analysis returned no per-level data.');
    }
    const ranges: JobRange[] = rows.map((r: any) => ({
      level: r.level,
      name: r.name,
      min_compensation: Math.round(r.min_compensation ?? r.suggested_min),
      max_compensation: Math.round(r.max_compensation ?? r.suggested_max),
    }));
    setBaseRanges(ranges);
    return ranges;
  };

  const handleMatchCensus = async () => {
    setMatchLoading(true);
    setMatchError(null);
    try {
      await fetchBaseRanges();
    } catch (e) {
      setMatchError(errorText(e));
    } finally {
      setMatchLoading(false);
    }
  };

  const handleSolveSettings = async () => {
    if (!activeWorkspace?.id) {
      setSolverError('No active workspace.');
      return;
    }
    setSolverLoading(true);
    setSolverError(null);
    try {
      const result = await solveCompensationGrowth(activeWorkspace.id, {
        file_path: censusPath || undefined,
        target_growth_rate: values.target_growth_pct,
        workforce_growth_rate: values.workforce_growth_rate,
        new_hire_comp_ratio: 0.85,
      });
      setSolverResult(result);
      // Solver returns percent units (e.g. 2.5); sliders are decimals.
      setValues((prev) => ({
        ...prev,
        cola_rate: result.cola_rate / 100,
        merit_budget: result.merit_budget / 100,
      }));
    } catch (e) {
      setSolverError(errorText(e));
    } finally {
      setSolverLoading(false);
    }
  };

  const setAgeRow = (idx: number, patch: Partial<AgeRow>) =>
    setAgeDist((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const runAutoCalibrate = async () => {
    setAutoLoading(true);
    setAutoError(null);
    setAutoOutcome(null);
    setApplyStatus('idle');
    try {
      // Scale mode NEVER silently falls back: derive the census ranges
      // automatically if Match Census hasn't been run, or fail clearly.
      let scaleBases = baseRanges;
      if (searchMode === 'new_hire_scale' && scaleBases.length === 0) {
        scaleBases = await fetchBaseRanges();
      }
      const response = await optimizeCalibration({
        start_year: startYear,
        end_year: endYear,
        database_path: databasePath.trim() || null,
        workspace_id: activeWorkspace?.id ?? null,
        settings: {
          target_workforce_growth: values.workforce_growth_rate,
          target_comp_growth: values.target_growth_pct,
          tolerance_pct: tolerancePct,
          max_iterations: maxIterations,
          search_mode: searchMode,
          ...(searchMode === 'new_hire_scale'
            ? {
                base_job_level_compensation: scaleBases,
                initial_scale: scaleFactor,
              }
            : {}),
        },
        params: {
          new_hire_age_distribution: ageDistEnabled ? ageDist : null,
          // In scale mode the optimizer injects the ranges itself.
          job_level_compensation:
            searchMode === 'levers' && jobRanges.length > 0 ? jobRanges : null,
        },
      });
      const outcome = response.outcome;
      setAutoOutcome(outcome);
      setResults(outcome.results);
      // Load the solved levers into the sliders so Apply to Workspace persists them.
      setValues((prev) => ({
        ...prev,
        cola_rate: outcome.best_params.cola_rate ?? prev.cola_rate,
        merit_budget: outcome.best_params.merit_budget ?? prev.merit_budget,
      }));
      // Apply the winning scale so the ranges table + Apply to Workspace match.
      if (outcome.best_scale !== null && outcome.best_scale !== undefined) {
        setScaleFactor(Number(outcome.best_scale.toFixed(2)));
      }
    } catch (e) {
      setAutoError(errorText(e));
    } finally {
      setAutoLoading(false);
    }
  };

  // Apply the calibrated levers to the workspace base config -- the same keys
  // the full simulation reads -- so "calibrate, apply, run the real sim" is one
  // click instead of re-entering values on the config pages.
  const [applyStatus, setApplyStatus] = useState<'idle' | 'applying' | 'applied' | 'error'>('idle');
  const [applyError, setApplyError] = useState<string | null>(null);

  const handleApplyToWorkspace = async () => {
    if (!activeWorkspace?.id) return;
    setApplyStatus('applying');
    setApplyError(null);
    try {
      const ws = await getWorkspace(activeWorkspace.id);
      const base = (ws.base_config ?? {}) as Record<string, any>;
      const merged = {
        ...base,
        simulation: {
          ...(base.simulation ?? {}),
          target_growth_rate: values.workforce_growth_rate,
        },
        compensation: {
          ...(base.compensation ?? {}),
          target_compensation_growth_percent: values.target_growth_pct * 100,
          // Write both forms: the loader prefers the bare decimal key when it
          // already exists, so updating only the _percent key could be ignored.
          cola_rate_percent: values.cola_rate * 100,
          cola_rate: values.cola_rate,
          merit_budget_percent: values.merit_budget * 100,
          merit_budget: values.merit_budget,
        },
        new_hire: {
          ...(base.new_hire ?? {}),
          ...(ageDistEnabled ? { age_distribution: ageDist } : {}),
          ...(jobRanges.length > 0 ? { job_level_compensation: jobRanges } : {}),
        },
      };
      await updateWorkspace(activeWorkspace.id, { base_config: merged });
      setApplyStatus('applied');
    } catch (e) {
      setApplyError(errorText(e));
      setApplyStatus('error');
    }
  };

  const runCalibrate = async () => {
    setLoading(true);
    setError(null);
    setApplyStatus('idle');
    try {
      const request: CalibrationRunRequest = {
        start_year: startYear,
        end_year: endYear,
        database_path: databasePath.trim() || null,
        workspace_id: activeWorkspace?.id ?? null,
        params: {
          target_growth_pct: values.target_growth_pct,
          workforce_growth_rate: values.workforce_growth_rate,
          cola_rate: values.cola_rate,
          merit_budget: values.merit_budget,
          new_hire_age_distribution: ageDistEnabled ? ageDist : null,
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
                <span>
                  {s.label}
                  {s.hint && (
                    <span className="ml-2 text-xs font-normal text-gray-400">{s.hint}</span>
                  )}
                </span>
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

        {/* Purple button: solve COLA/merit from the target comp growth, same
            solver as the Compensation page's Calculate Settings. */}
        <div className="rounded-md border border-purple-200 bg-purple-50 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleSolveSettings}
              disabled={solverLoading || !activeWorkspace?.id}
              className="inline-flex items-center gap-2 rounded bg-purple-600 px-3 py-2 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
            >
              {solverLoading ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
              Calculate COLA & Merit
            </button>
            <span className="text-xs text-purple-800">
              Solve for the COLA/merit that hit your Target Comp Growth ({pct(values.target_growth_pct)})
              given Workforce Growth ({pct(values.workforce_growth_rate)}) — then verify with a run.
            </span>
          </div>
          {solverError && <p className="mt-2 text-xs text-red-600">{solverError}</p>}
          {solverResult && !solverError && (
            <p className="mt-2 text-xs text-purple-900">
              Applied COLA {solverResult.cola_rate.toFixed(1)}% + merit {solverResult.merit_budget.toFixed(1)}%
              (est. net growth {solverResult.achieved_growth_rate.toFixed(1)}%
              {solverResult.recommended_scale_factor > 1.05 && (
                <> — solver suggests ~{solverResult.recommended_scale_factor.toFixed(1)}× census scale for new-hire ranges</>
              )}
              ). Sliders updated.
            </p>
          )}
        </div>

        {/* Auto-Calibrate: iterated comp-only runs that SOLVE for COLA/merit.
            Workforce growth is set exactly (deterministic solver); comp growth
            is searched until within tolerance. */}
        <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
          <div className="flex flex-wrap items-end gap-4">
            <button
              onClick={runAutoCalibrate}
              disabled={autoLoading || endYear <= startYear}
              title={endYear <= startYear ? 'Needs a multi-year range to measure YoY growth' : undefined}
              className="inline-flex items-center gap-2 rounded bg-blue-600 px-4 py-2 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {autoLoading ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
              {autoLoading ? 'Searching…' : 'Auto-Calibrate'}
            </button>
            <span className="text-xs text-blue-900 max-w-md">
              Hit Target Comp Growth ({pct(values.target_growth_pct)}) at Workforce Growth
              ({pct(values.workforce_growth_rate)}) by running real comp-only simulations.
              Typically 3–6 runs (a few minutes).
            </span>
            <label className="block">
              <span className="text-xs text-blue-800">Solve for</span>
              <select
                value={searchMode}
                onChange={(e) => setSearchMode(e.target.value as 'new_hire_scale' | 'levers')}
                className="mt-1 block rounded border-blue-300 text-xs"
              >
                <option value="new_hire_scale">New-hire ranges (keep COLA/merit)</option>
                <option value="levers">COLA/merit (keep ranges)</option>
              </select>
              {searchMode === 'new_hire_scale' && baseRanges.length === 0 && (
                <span className="mt-1 block text-xs text-gray-500">
                  {censusPath
                    ? 'Census ranges will be derived automatically (Match Census).'
                    : 'Needs a census — upload one to this workspace first.'}
                </span>
              )}
            </label>
            <label className="block">
              <span className="text-xs text-blue-800">Tolerance (± pp)</span>
              <input
                type="number" step="0.01" min={0.01} max={1} value={tolerancePct}
                onChange={(e) => setTolerancePct(Number(e.target.value))}
                className="mt-1 w-24 rounded border-blue-300 text-xs"
              />
            </label>
            <label className="block">
              <span className="text-xs text-blue-800">Max runs</span>
              <input
                type="number" min={1} max={25} value={maxIterations}
                onChange={(e) => setMaxIterations(Number(e.target.value))}
                className="mt-1 w-20 rounded border-blue-300 text-xs"
              />
            </label>
          </div>
          {autoError && <p className="mt-2 text-xs text-red-600">{autoError}</p>}
          {autoOutcome && (
            <div className="mt-3">
              <p className={`text-xs font-medium ${autoOutcome.converged ? 'text-green-700' : 'text-amber-700'}`}>
                {autoOutcome.message}
              </p>
              <p className="mt-1 text-xs text-blue-900">
                Best config: COLA {pct(autoOutcome.best_params.cola_rate ?? 0)}, merit{' '}
                {pct(autoOutcome.best_params.merit_budget ?? 0)}
                {autoOutcome.best_scale != null && (
                  <>, new-hire range scale {autoOutcome.best_scale.toFixed(2)}×</>
                )}{' '}
                — controls updated; use “Apply to Workspace” to persist, then run the
                full simulation.
              </p>
              <table className="mt-2 text-xs w-full max-w-lg">
                <thead className="text-blue-800">
                  <tr>
                    <th className="text-left">Run</th>
                    <th className="text-right">COLA</th>
                    <th className="text-right">Merit</th>
                    <th className="text-right">Scale</th>
                    <th className="text-right">Comp Growth</th>
                    <th className="text-right">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {autoOutcome.iterations.map((it) => (
                    <tr key={it.iteration} className="border-t border-blue-100">
                      <td>{it.iteration}</td>
                      <td className="text-right">{pct(it.cola_rate)}</td>
                      <td className="text-right">{pct(it.merit_budget)}</td>
                      <td className="text-right">{it.scale != null ? `${it.scale.toFixed(2)}×` : '—'}</td>
                      <td className="text-right">{it.achieved_growth_pct.toFixed(2)}%</td>
                      <td className="text-right">{it.error_pct >= 0 ? '+' : ''}{it.error_pct.toFixed(2)}pp</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* New-hire age distribution override — flows through the same
            new_hire_age_distribution dbt var the full simulation uses. */}
        <div className="rounded-md border border-gray-200 p-4">
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <input
              type="checkbox"
              checked={ageDistEnabled}
              onChange={(e) => setAgeDistEnabled(e.target.checked)}
              className="accent-fidelity-green"
            />
            Override New-Hire Age Distribution
            <span className="text-xs font-normal text-gray-500">
              (weights are normalized; unchecked = scenario/seed defaults)
            </span>
          </label>
          {ageDistEnabled && (
            <div className="mt-3 space-y-2">
              {ageDist.map((row, idx) => (
                <div key={idx} className="flex items-center gap-3">
                  <label className="flex items-center gap-1 text-xs text-gray-600">
                    Age
                    <input
                      type="number" min={16} max={80} value={row.age}
                      onChange={(e) => setAgeRow(idx, { age: Number(e.target.value) })}
                      className="w-16 rounded border-gray-300 text-xs"
                    />
                  </label>
                  <input
                    type="range" min={0} max={0.5} step={0.01} value={row.weight}
                    onChange={(e) => setAgeRow(idx, { weight: Number(e.target.value) })}
                    className="flex-1 accent-fidelity-green"
                  />
                  <span className="w-12 text-right text-xs text-gray-700">{pct(row.weight)}</span>
                  <button
                    onClick={() => setAgeDist((prev) => prev.filter((_, i) => i !== idx))}
                    disabled={ageDist.length <= 1}
                    className="text-gray-400 hover:text-red-500 disabled:opacity-30"
                    title="Remove age bucket"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
              <div className="flex items-center justify-between">
                <button
                  onClick={() =>
                    setAgeDist((prev) => [
                      ...prev,
                      { age: (prev[prev.length - 1]?.age ?? 30) + 5, weight: 0.05 },
                    ])
                  }
                  className="inline-flex items-center gap-1 text-xs text-fidelity-green hover:text-fidelity-dark"
                >
                  <Plus size={14} /> Add age bucket
                </button>
                <span className="text-xs text-gray-500">
                  Total weight: {pct(ageDist.reduce((s, r) => s + r.weight, 0))}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={runCalibrate}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded bg-fidelity-green px-4 py-2 text-white font-medium hover:bg-fidelity-dark disabled:opacity-50"
          >
            {loading ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
            {loading ? 'Calibrating…' : 'Run Calibration'}
          </button>
          <button
            onClick={handleApplyToWorkspace}
            disabled={applyStatus === 'applying' || !activeWorkspace?.id || results.length === 0}
            title={results.length === 0 ? 'Run a calibration first' : 'Write these levers to the workspace config the full simulation uses'}
            className="inline-flex items-center gap-2 rounded border border-fidelity-green px-4 py-2 text-fidelity-green font-medium hover:bg-green-50 disabled:opacity-50"
          >
            {applyStatus === 'applying' ? <Loader2 className="animate-spin" size={18} /> : <Database size={18} />}
            {applyStatus === 'applied' ? 'Applied ✓' : 'Apply to Workspace'}
          </button>
          {applyStatus === 'applied' && (
            <span className="text-xs text-gray-600">
              Workspace config updated — run the full simulation to make it official.
            </span>
          )}
          {applyStatus === 'error' && applyError && (
            <span className="text-xs text-red-600">{applyError}</span>
          )}
        </div>
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
                  <th className="px-4 py-2 text-right" title="New-hire vs existing average pay, on full-year-equivalent rates (not prorated)">NH Rate Gap</th>
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
