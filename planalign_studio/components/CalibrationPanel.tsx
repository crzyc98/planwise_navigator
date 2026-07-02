import React, { useState, useEffect, useMemo } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { SlidersHorizontal, Loader2, Database, Sparkles, Plus, X, Check } from 'lucide-react';
import {
  optimizeCalibration,
  AutoCalibrationOutcome,
  PerYearCompensationResult,
  ApiError,
  getWorkspace,
  updateWorkspace,
  analyzeCompensation,
  analyzeAgeDistribution,
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
  { key: 'target_growth_pct', label: 'Target Salary Growth', hint: 'the goal calibration solves for', min: 0, max: 0.1, step: 0.005 },
  { key: 'workforce_growth_rate', label: 'Workforce Growth', hint: 'deterministic headcount driver — sizes hiring', min: -0.05, max: 0.1, step: 0.005 },
  { key: 'cola_rate', label: 'COLA', min: 0, max: 0.1, step: 0.005 },
  { key: 'merit_budget', label: 'Merit', min: 0, max: 0.1, step: 0.005 },
];

const GROWTH_KEYS = new Set<SliderConfig['key']>(['target_growth_pct', 'workforce_growth_rate']);
const POLICY_KEYS = new Set<SliderConfig['key']>(['cola_rate', 'merit_budget']);

type SolveMode = 'new_hire_scale' | 'levers';

/**
 * The top-level calibration decision (Step 2): which lever we solve to hit the
 * growth target. The chosen mode is held in `searchMode`; the other lever is
 * held fixed, and controls that only apply to the other mode are hidden.
 */
const SOLVE_MODES: { key: SolveMode; title: string; description: string }[] = [
  {
    key: 'new_hire_scale',
    title: 'New-hire salary ranges',
    description:
      'Scale new-hire pay so hiring absorbs your compensation-growth target, holding COLA & merit fixed. Recommended.',
  },
  {
    key: 'levers',
    title: 'COLA & merit',
    description:
      'Adjust the annual COLA and merit budget to hit your target, holding new-hire salary ranges fixed.',
  },
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

// Rolling 5-year default window: current year through current year + 5.
const DEFAULT_START_YEAR = new Date().getFullYear();
const DEFAULT_END_YEAR = DEFAULT_START_YEAR + 5;

/** Numbered step heading with a short instruction line for the analyst. */
function StepHeader({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-fidelity-green text-sm font-semibold text-white">
        {n}
      </span>
      <div>
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        <p className="text-sm text-gray-500">{children}</p>
      </div>
    </div>
  );
}

/** A single labeled percentage slider used across steps. */
function SliderRow({
  s,
  value,
  onChange,
}: {
  s: SliderConfig;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex justify-between text-sm font-medium text-gray-700">
        <span>
          {s.label}
          {s.hint && <span className="ml-2 text-xs font-normal text-gray-400">{s.hint}</span>}
        </span>
        <span className="text-fidelity-green">{pct(value)}</span>
      </div>
      <input
        type="range"
        min={s.min}
        max={s.max}
        step={s.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-fidelity-green"
      />
    </div>
  );
}

export default function CalibrationPanel() {
  const [startYear, setStartYear] = useState(DEFAULT_START_YEAR);
  const [endYear, setEndYear] = useState(DEFAULT_END_YEAR);
  const [values, setValues] = useState<Record<string, number>>({
    target_growth_pct: 0.035,
    workforce_growth_rate: 0.03,
    cola_rate: 0.02,
    merit_budget: 0.035,
  });
  const [results, setResults] = useState<PerYearCompensationResult[]>([]);

  // New-hire age distribution (real lever: flows through the same
  // new_hire_age_distribution dbt var the full simulation consumes).
  // 'default' = scenario/seed defaults (no override sent), 'census' = derived
  // from the workspace census (same analyzer as the New Hire config page),
  // 'custom' = hand-edited weights.
  const [ageDistMode, setAgeDistMode] = useState<'default' | 'census' | 'custom'>('default');
  const [ageDist, setAgeDist] = useState<AgeRow[]>(DEFAULT_AGE_DIST);
  const [ageDistLoading, setAgeDistLoading] = useState(false);
  const [ageDistError, setAgeDistError] = useState<string | null>(null);
  const ageDistEnabled = ageDistMode !== 'default';

  // Auto-calibrate: iterated comp-only runs that SOLVE for COLA/merit given
  // the two targets (workforce growth is set exactly; comp growth is searched).
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoError, setAutoError] = useState<string | null>(null);
  const [autoOutcome, setAutoOutcome] = useState<AutoCalibrationOutcome | null>(null);
  const [tolerancePct, setTolerancePct] = useState(0.05);
  const [maxIterations, setMaxIterations] = useState(8);
  // 'new_hire_scale': solve the new-hire range scale so hiring dilution isn't
  // papered over with raises (COLA/merit stay as set). Needs Match Census.
  const [searchMode, setSearchMode] = useState<SolveMode>('new_hire_scale');
  const solvingNewHireRanges = searchMode === 'new_hire_scale';

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

  const setAgeRow = (idx: number, patch: Partial<AgeRow>) =>
    setAgeDist((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const handleAgeDistModeChange = async (mode: 'default' | 'census' | 'custom') => {
    setAgeDistMode(mode);
    setAgeDistError(null);
    if (mode !== 'census') return;
    if (!activeWorkspace?.id || !censusPath) {
      setAgeDistError('This workspace has no census file uploaded yet.');
      return;
    }
    setAgeDistLoading(true);
    try {
      const result = await analyzeAgeDistribution(activeWorkspace.id, censusPath);
      setAgeDist(result.distribution.map((d) => ({ age: d.age, weight: d.weight })));
    } catch (e) {
      setAgeDistError(errorText(e));
    } finally {
      setAgeDistLoading(false);
    }
  };

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
        database_path: null,
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

      {/* Step-by-step calibration workflow */}
      <div className="space-y-6">

        {/* ── Step 1: Growth targets & scope ────────────────────────── */}
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <StepHeader n={1} title="Set your growth targets and scope">
            Confirm the workspace and year range, then set the two growth drivers:
            Workforce Growth sizes hiring deterministically, and Target Salary Growth
            is the goal calibration ultimately solves for.
          </StepHeader>

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

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Start Year</span>
              <input
                type="number"
                value={startYear}
                onChange={(e) => setStartYear(Number(e.target.value))}
                className="mt-1 w-full rounded-md border border-gray-300 p-2 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">End Year</span>
              <input
                type="number"
                value={endYear}
                onChange={(e) => setEndYear(Number(e.target.value))}
                className="mt-1 w-full rounded-md border border-gray-300 p-2 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
              />
            </label>
          </div>
          <p className="text-xs text-gray-500">
            Calibration always runs against an isolated copy of the database — the shared dev database is never touched.
          </p>

          {/* The two growth drivers: workforce growth (deterministic) and the
              salary-growth target calibration solves for. */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-1">
            {SLIDERS.filter((s) => GROWTH_KEYS.has(s.key)).map((s) => (
              <SliderRow
                key={s.key}
                s={s}
                value={values[s.key]}
                onChange={(v) => setValue(s.key, v)}
              />
            ))}
          </div>
          <div className="rounded-md bg-fidelity-green/5 border border-fidelity-green/20 px-3 py-2 text-xs text-fidelity-dark">
            <span className="font-semibold">Target Salary Growth is the objective.</span>{' '}
            Calibration auto-tunes your chosen lever (Step 2) until per-year salary
            growth lands on this target.
          </div>
        </div>

        {/* ── Step 2: Choose what to solve for ──────────────────────── */}
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <StepHeader n={2} title="Choose what calibration solves for">
            Pick the lever calibration should adjust to hit your growth target. The
            other lever is held fixed at whatever you set below, and the options that
            don't apply are hidden.
          </StepHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SOLVE_MODES.map((m) => {
              const selected = searchMode === m.key;
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setSearchMode(m.key)}
                  className={`text-left rounded-lg border p-4 transition ${
                    selected
                      ? 'border-fidelity-green ring-2 ring-fidelity-green/30 bg-green-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-gray-900">{m.title}</span>
                    {selected && <Check size={16} className="text-fidelity-green shrink-0" />}
                  </div>
                  <p className="mt-1 text-xs text-gray-500">{m.description}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Step 3: Fixed inputs ──────────────────────────────────── */}
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <StepHeader n={3} title="Set the levers calibration holds fixed">
            Provide the inputs calibration keeps constant — new-hire age mix, and
            whichever of new-hire ranges / COLA &amp; merit you're not solving for.
            Whatever Step 2 is solving for is filled in automatically.
          </StepHeader>

          {/* Job Level Compensation Ranges. When calibration is solving these,
              the editor is collapsed to a label — the analyst shouldn't fill in
              something the solver derives. When held fixed, the full editor shows. */}
          {solvingNewHireRanges ? (
            <div className="rounded-md border border-dashed border-gray-300 bg-gray-50 p-4 flex items-start gap-2">
              <Sparkles size={16} className="mt-0.5 shrink-0 text-fidelity-green" />
              <div className="text-sm text-gray-600">
                <span className="font-medium text-gray-800">Job Level Compensation Ranges — solved automatically.</span>{' '}
                Calibration scales census-derived new-hire ranges to hit your target,
                so there's nothing to set here. Switch Step 2 to “COLA &amp; merit” if you'd
                rather set the ranges by hand.
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-gray-200 p-4">
              <div className="text-sm font-medium text-gray-700 mb-2 flex flex-wrap items-center gap-2">
                Job Level Compensation Ranges
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                  Held fixed
                </span>
                <span className="text-xs font-normal text-gray-500">
                  used as-is; set your starting point below
                </span>
              </div>
              <div className="flex flex-wrap items-end gap-4">
                <label className="block">
                  <span className="text-xs text-gray-600">Scale (×)</span>
                  <input
                    type="number" step="0.1" min={0.1} max={3.0} value={scaleFactor}
                    onChange={(e) => setScaleFactor(Number(e.target.value))}
                    className="mt-1 w-24 rounded-md border border-gray-300 p-1.5 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
                  />
                </label>
                <label className="block">
                  <span className="text-xs text-gray-600">Lookback (years)</span>
                  <input
                    type="number" min={0} max={20} value={lookbackYears}
                    onChange={(e) => setLookbackYears(Number(e.target.value))}
                    className="mt-1 w-28 rounded-md border border-gray-300 p-1.5 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
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
          )}

          {/* New-hire age distribution — flows through the same
              new_hire_age_distribution dbt var the full simulation uses. */}
          <div className="rounded-md border border-gray-200 p-4">
            <div className="text-sm font-medium text-gray-700 mb-2">New-Hire Age Distribution</div>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-1.5 text-sm text-gray-700">
                <input
                  type="radio"
                  name="ageDistMode"
                  checked={ageDistMode === 'default'}
                  onChange={() => handleAgeDistModeChange('default')}
                  className="accent-fidelity-green"
                />
                Scenario/seed defaults
              </label>
              <label className="flex items-center gap-1.5 text-sm text-gray-700">
                <input
                  type="radio"
                  name="ageDistMode"
                  checked={ageDistMode === 'census'}
                  onChange={() => handleAgeDistModeChange('census')}
                  disabled={!censusPath}
                  className="accent-fidelity-green"
                />
                Match census
                {ageDistLoading && ageDistMode === 'census' && (
                  <Loader2 className="animate-spin text-gray-400" size={14} />
                )}
              </label>
              <label className="flex items-center gap-1.5 text-sm text-gray-700">
                <input
                  type="radio"
                  name="ageDistMode"
                  checked={ageDistMode === 'custom'}
                  onChange={() => handleAgeDistModeChange('custom')}
                  className="accent-fidelity-green"
                />
                Custom
              </label>
            </div>
            {!censusPath && (
              <p className="mt-1 text-xs text-gray-500">
                Upload a census to this workspace to enable "Match census".
              </p>
            )}
            {ageDistError && <p className="mt-2 text-xs text-red-600">{ageDistError}</p>}
            {ageDistEnabled && (
              <div className="mt-3 space-y-2">
                {ageDist.map((row, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <label className="flex items-center gap-1 text-xs text-gray-600">
                      Age
                      <input
                        type="number" min={16} max={80} value={row.age}
                        onChange={(e) => setAgeRow(idx, { age: Number(e.target.value) })}
                        className="w-16 rounded-md border border-gray-300 p-1 text-xs shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
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

          {/* COLA & merit: a fixed policy input when calibration is solving
              new-hire ranges; collapsed to a label when they're the chosen lever. */}
          {solvingNewHireRanges ? (
            <div className="rounded-md border border-gray-200 p-4">
              <div className="text-sm font-medium text-gray-700 mb-2 flex flex-wrap items-center gap-2">
                COLA &amp; Merit
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                  Held fixed
                </span>
                <span className="text-xs font-normal text-gray-500">
                  the annual policy calibration keeps constant while it scales new-hire ranges
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {SLIDERS.filter((s) => POLICY_KEYS.has(s.key)).map((s) => (
                  <SliderRow
                    key={s.key}
                    s={s}
                    value={values[s.key]}
                    onChange={(v) => setValue(s.key, v)}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-gray-300 bg-gray-50 p-4 flex items-start gap-2">
              <Sparkles size={16} className="mt-0.5 shrink-0 text-fidelity-green" />
              <div className="text-sm text-gray-600">
                <span className="font-medium text-gray-800">COLA &amp; merit — solved automatically.</span>{' '}
                Calibration finds the COLA and merit budget that hit your Target Salary
                Growth, so there's nothing to set here.
              </div>
            </div>
          )}
        </div>

        {/* ── Step 4: Auto-calibrate, then apply ────────────────────── */}
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <StepHeader n={4} title="Auto-calibrate to your target, then apply">
            {solvingNewHireRanges
              ? 'Run the auto-calibration — it searches the new-hire salary scale across real comp-only simulations until per-year salary growth lands on your target. Then apply the result to the workspace.'
              : 'Run the auto-calibration — it searches COLA & merit across real comp-only simulations until per-year salary growth lands on your target. Then apply the result to the workspace.'}
          </StepHeader>

        {/* Auto-Calibrate: the single run action. Iterated comp-only runs that
            solve the chosen lever; workforce growth is deterministic. */}
        <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
          <div className="space-y-3">
            <p className="text-xs text-blue-900">
              Solving <span className="font-semibold">{solvingNewHireRanges ? 'new-hire salary ranges' : 'COLA & merit'}</span> to
              hit Target Salary Growth ({pct(values.target_growth_pct)}) at Workforce Growth
              ({pct(values.workforce_growth_rate)}) by running real comp-only simulations.
              Typically 3–6 runs (a few minutes).
            </p>
            {solvingNewHireRanges && baseRanges.length === 0 && (
              <p className="text-xs text-gray-600">
                {censusPath
                  ? 'Census ranges will be derived automatically (Match Census).'
                  : 'Needs a census — upload one to this workspace first.'}
              </p>
            )}
            <div className="flex flex-wrap items-end gap-4">
              <button
                onClick={runAutoCalibrate}
                disabled={autoLoading || endYear <= startYear}
                title={endYear <= startYear ? 'Needs a multi-year range to measure YoY growth' : undefined}
                className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {autoLoading ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
                {autoLoading ? 'Searching…' : 'Auto-Calibrate'}
              </button>
              <label className="block">
                <span className="text-xs font-medium text-blue-800">Tolerance (± pp)</span>
                <input
                  type="number" step="0.01" min={0.01} max={1} value={tolerancePct}
                  onChange={(e) => setTolerancePct(Number(e.target.value))}
                  className="mt-1 w-28 rounded-md border border-blue-300 p-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-blue-800">Max runs</span>
                <input
                  type="number" min={1} max={25} value={maxIterations}
                  onChange={(e) => setMaxIterations(Number(e.target.value))}
                  className="mt-1 w-24 rounded-md border border-blue-300 p-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
                />
              </label>
            </div>
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

          {/* Apply the calibrated levers to the workspace config the full sim reads. */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleApplyToWorkspace}
              disabled={applyStatus === 'applying' || !activeWorkspace?.id || results.length === 0}
              title={results.length === 0 ? 'Auto-calibrate first' : 'Write these levers to the workspace config the full simulation uses'}
              className="inline-flex items-center gap-2 rounded bg-fidelity-green px-4 py-2 text-white font-medium hover:bg-fidelity-dark disabled:opacity-50"
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
      </div>

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
