import React, { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Plus, X, Loader2, Upload, AlertTriangle } from 'lucide-react';
import {
  validateOptimizerSpec,
  runOptimizer,
  ApiError,
  Workspace,
  Candidate,
  LeverKind,
  LeverSpec,
  LeverValue,
  ObjectiveTerm,
  ConstraintSpec,
  ConstraintOperator,
  ObjectiveDirection,
  OptimizerSpecPayload,
  OptimizerValidateResponse,
  OptimizerJob,
} from '../services/api';
import { useChartTheme } from '../hooks/useChartTheme';

interface OptimizerOutletContext {
  activeWorkspace: Workspace | null;
}

/**
 * Valid lever names (planalign_optimizer/design_space.py::LEVER_REGISTRY).
 * The registry maps a name to a config path only -- it does not encode
 * kind/bounds/choices, so this builder collects those generically per row
 * rather than assuming enum values (e.g. valid auto_enrollment.scope
 * strings) that aren't sourced from the backend.
 */
const LEVER_NAMES = [
  'employer_match.tier_1_rate',
  'employer_match.tier_2_rate',
  'employer_match.tier_3_rate',
  'employer_match.tier_1_cap',
  'employer_match.tier_2_cap',
  'employer_match.tier_3_cap',
  'employer_match.max_match_percentage',
  'employer_match.eligibility.minimum_tenure_years',
  'employer_match.eligibility.minimum_hours_annual',
  'auto_enrollment.enabled',
  'auto_enrollment.default_deferral_rate',
  'auto_enrollment.scope',
  'auto_escalation.enabled',
  'auto_escalation.annual_increase_rate',
  'auto_escalation.maximum_rate',
  'eligibility.waiting_period_days',
  'eligibility.minimum_age',
  'vesting_schedule',
] as const;

const MAX_LEVERS = 8;

/** planalign_optimizer/metrics.py::OBJECTIVE_METRICS (usable as objective or constraint). */
const OBJECTIVE_METRICS = [
  'active_headcount',
  'total_compensation',
  'employer_match_cost',
  'total_employer_plan_cost',
  'participation_rate',
  'avg_deferral_rate',
] as const;

/** SUPPORTED_METRICS = OBJECTIVE_METRICS + irs_compliance_pass (constraint-only). */
const CONSTRAINT_METRICS = [...OBJECTIVE_METRICS, 'irs_compliance_pass'] as const;

const CONSTRAINT_OPERATORS: ConstraintOperator[] = ['<=', '>=', '<', '>', '=='];

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

/** Numbered step heading with a short instruction line for the analyst. */
function StepHeader({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-fidelity-green text-sm font-semibold text-ink-inverse">
        {n}
      </span>
      <div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        <p className="text-sm text-ink-muted">{children}</p>
      </div>
    </div>
  );
}

function parseLeverValue(raw: string): LeverValue {
  const trimmed = raw.trim();
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (trimmed !== '' && !Number.isNaN(Number(trimmed))) return Number(trimmed);
  return raw;
}

let rowIdCounter = 0;
const nextRowId = () => rowIdCounter++;

interface LeverRow {
  id: number;
  name: string;
  kind: LeverKind;
  min: string;
  max: string;
  choices: LeverValue[];
  choiceDraft: string;
}

function newLeverRow(): LeverRow {
  return { id: nextRowId(), name: LEVER_NAMES[0], kind: 'continuous', min: '', max: '', choices: [], choiceDraft: '' };
}

interface ObjectiveRow {
  id: number;
  metric: string;
  direction: ObjectiveDirection;
}

interface ConstraintRow {
  id: number;
  metric: string;
  operator: ConstraintOperator;
  threshold: string;
  percentile: string;
}

function leverRowToSpec(row: LeverRow): LeverSpec {
  if (row.kind === 'continuous') {
    return { name: row.name, kind: 'continuous', bounds: [Number(row.min), Number(row.max)] };
  }
  return { name: row.name, kind: 'discrete', choices: row.choices };
}

export default function OptimizerPanel() {
  const chartTheme = useChartTheme();
  const { activeWorkspace } = useOutletContext<OptimizerOutletContext>();

  // Step 1 -- design space
  const [leverRows, setLeverRows] = useState<LeverRow[]>([newLeverRow()]);
  const [showImport, setShowImport] = useState(false);
  const [importYaml, setImportYaml] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  // Step 2 -- objective + constraints
  const [objectiveRows, setObjectiveRows] = useState<ObjectiveRow[]>([
    { id: nextRowId(), metric: OBJECTIVE_METRICS[0], direction: 'minimize' },
  ]);
  const [constraintRows, setConstraintRows] = useState<ConstraintRow[]>([]);

  // Step 3 -- baseline + run parameters
  const [configPath, setConfigPath] = useState('config/simulation_config.yaml');
  const [useWorkspaceBaseline, setUseWorkspaceBaseline] = useState(false);
  const [ensembleDatabase, setEnsembleDatabase] = useState('');
  const [maxRuns, setMaxRuns] = useState(20);
  const [searchSeed, setSearchSeed] = useState('');
  const [parallel, setParallel] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [databaseDir, setDatabaseDir] = useState('');
  const [outputDir, setOutputDir] = useState('');

  const [validateLoading, setValidateLoading] = useState(false);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [validation, setValidation] = useState<OptimizerValidateResponse | null>(null);

  // Step 4 -- run + results
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [job, setJob] = useState<OptimizerJob | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

  const percentileEnabled = ensembleDatabase.trim() !== '';

  const buildSpec = (): OptimizerSpecPayload => ({
    design_space: { levers: leverRows.map(leverRowToSpec) },
    objective: {
      objectives: objectiveRows.map(
        (r): ObjectiveTerm => ({ metric: r.metric, direction: r.direction })
      ),
      constraints: constraintRows.map(
        (r): ConstraintSpec => ({
          metric: r.metric,
          operator: r.operator,
          threshold: Number(r.threshold),
          percentile: r.percentile ? Number(r.percentile) : undefined,
        })
      ),
    },
    baseline: {
      config_path: configPath,
      ensemble_database: ensembleDatabase.trim() || undefined,
    },
  });

  const addLeverRow = () =>
    setLeverRows((prev) => (prev.length >= MAX_LEVERS ? prev : [...prev, newLeverRow()]));
  const removeLeverRow = (id: number) =>
    setLeverRows((prev) => prev.filter((r) => r.id !== id));
  const updateLeverRow = (id: number, patch: Partial<LeverRow>) =>
    setLeverRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const addObjectiveRow = () =>
    setObjectiveRows((prev) =>
      prev.length >= 2 ? prev : [...prev, { id: nextRowId(), metric: OBJECTIVE_METRICS[0], direction: 'minimize' }]
    );
  const removeObjectiveRow = (id: number) =>
    setObjectiveRows((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.id !== id)));
  const updateObjectiveRow = (id: number, patch: Partial<ObjectiveRow>) =>
    setObjectiveRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const addConstraintRow = () =>
    setConstraintRows((prev) => [
      ...prev,
      { id: nextRowId(), metric: CONSTRAINT_METRICS[0], operator: '>=', threshold: '', percentile: '' },
    ]);
  const removeConstraintRow = (id: number) =>
    setConstraintRows((prev) => prev.filter((r) => r.id !== id));
  const updateConstraintRow = (id: number, patch: Partial<ConstraintRow>) =>
    setConstraintRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const handleValidate = async () => {
    setValidateLoading(true);
    setValidateError(null);
    setValidation(null);
    try {
      const resp = await validateOptimizerSpec({ spec: buildSpec(), max_runs: maxRuns });
      setValidation(resp);
      if (!resp.valid) setValidateError(resp.error ?? 'Spec is invalid');
    } catch (e) {
      setValidateError(errorText(e));
    } finally {
      setValidateLoading(false);
    }
  };

  const handleImport = async () => {
    setImportLoading(true);
    setImportError(null);
    try {
      const resp = await validateOptimizerSpec({ spec_yaml: importYaml });
      if (!resp.valid || !resp.resolved_spec) {
        setImportError(resp.error ?? 'Could not parse spec');
        return;
      }
      const spec = resp.resolved_spec;
      setLeverRows(
        spec.design_space.levers.map((l): LeverRow => ({
          id: nextRowId(),
          name: l.name,
          kind: l.kind,
          min: l.bounds ? String(l.bounds[0]) : '',
          max: l.bounds ? String(l.bounds[1]) : '',
          choices: l.choices ?? [],
          choiceDraft: '',
        }))
      );
      setObjectiveRows(
        spec.objective.objectives.map((o): ObjectiveRow => ({
          id: nextRowId(),
          metric: o.metric,
          direction: o.direction,
        }))
      );
      setConstraintRows(
        spec.objective.constraints.map((c): ConstraintRow => ({
          id: nextRowId(),
          metric: c.metric,
          operator: c.operator,
          threshold: String(c.threshold),
          percentile: c.percentile != null ? String(c.percentile) : '',
        }))
      );
      setConfigPath(spec.baseline.config_path);
      setEnsembleDatabase(spec.baseline.ensemble_database ?? '');
      setShowImport(false);
      setImportYaml('');
    } catch (e) {
      setImportError(errorText(e));
    } finally {
      setImportLoading(false);
    }
  };

  const handleRun = async () => {
    setRunLoading(true);
    setRunError(null);
    setJob(null);
    setSelectedCandidateId(null);
    try {
      const completed = await runOptimizer({
        spec: buildSpec(),
        max_runs: maxRuns,
        search_seed: searchSeed ? Number(searchSeed) : undefined,
        parallel: parallel ? Number(parallel) : undefined,
        workspace_id: useWorkspaceBaseline ? activeWorkspace?.id ?? undefined : undefined,
        database_dir: databaseDir.trim() || undefined,
        output_dir: outputDir.trim() || undefined,
      });
      setJob(completed);
    } catch (e) {
      setRunError(errorText(e));
    } finally {
      setRunLoading(false);
    }
  };

  const run = job?.result ?? null;
  const isTwoObjective = objectiveRows.length === 2;
  const frontierMetrics = isTwoObjective ? [objectiveRows[0].metric, objectiveRows[1].metric] : null;

  const colorByCandidate = useMemo(() => {
    const map: Record<string, string> = {};
    (run?.candidates ?? []).forEach((c, i) => {
      map[c.candidate_id] = chartTheme.colorAt(i);
    });
    return map;
  }, [run]);

  const rankedOrder = useMemo(() => {
    if (!run) return new Map<string, number>();
    const map = new Map<string, number>();
    run.ranked_feasible.forEach((id, i) => map.set(id, i + 1));
    return map;
  }, [run]);

  const selectedCandidate: Candidate | null =
    run?.candidates.find((c) => c.candidate_id === selectedCandidateId) ?? null;

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-xl font-bold text-ink">Plan-Design Optimizer</h1>
        <p className="text-sm text-ink-muted">
          State objectives and constraints; PlanAlign searches match, auto-enrollment, escalation,
          eligibility, and vesting design and returns the best candidates found within your run budget.
        </p>
      </div>

      {/* Step 1: Design space */}
      <div className="bg-surface-raised rounded-lg shadow p-6 space-y-4">
        <StepHeader n={1} title="Declare the design space">
          Which levers can the search adjust? Up to {MAX_LEVERS} at a time.
        </StepHeader>

        <div className="space-y-3">
          {leverRows.map((row) => (
            <div key={row.id} className="flex flex-wrap items-center gap-2 rounded-md border border-border p-3">
              <select
                className="rounded-md border border-border-strong p-2 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
                value={row.name}
                onChange={(e) => updateLeverRow(row.id, { name: e.target.value })}
              >
                {LEVER_NAMES.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <div className="flex rounded-md border border-border-strong overflow-hidden text-sm">
                {(['continuous', 'discrete'] as LeverKind[]).map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => updateLeverRow(row.id, { kind })}
                    className={`px-3 py-2 ${row.kind === kind ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised text-ink-muted'}`}
                  >
                    {kind}
                  </button>
                ))}
              </div>
              {row.kind === 'continuous' ? (
                <>
                  <input
                    type="number"
                    placeholder="min"
                    className="w-24 rounded-md border border-border-strong p-2 text-sm shadow-sm"
                    value={row.min}
                    onChange={(e) => updateLeverRow(row.id, { min: e.target.value })}
                  />
                  <input
                    type="number"
                    placeholder="max"
                    className="w-24 rounded-md border border-border-strong p-2 text-sm shadow-sm"
                    value={row.max}
                    onChange={(e) => updateLeverRow(row.id, { max: e.target.value })}
                  />
                </>
              ) : (
                <div className="flex flex-1 flex-wrap items-center gap-1">
                  {row.choices.map((choice, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 rounded bg-surface-subtle px-2 py-1 text-xs"
                    >
                      {String(choice)}
                      <button
                        type="button"
                        onClick={() =>
                          updateLeverRow(row.id, {
                            choices: row.choices.filter((_, idx) => idx !== i),
                          })
                        }
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                  <input
                    type="text"
                    placeholder="add value, Enter"
                    className="w-32 rounded-md border border-border-strong p-1.5 text-xs shadow-sm"
                    value={row.choiceDraft}
                    onChange={(e) => updateLeverRow(row.id, { choiceDraft: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && row.choiceDraft.trim() !== '') {
                        e.preventDefault();
                        updateLeverRow(row.id, {
                          choices: [...row.choices, parseLeverValue(row.choiceDraft)],
                          choiceDraft: '',
                        });
                      }
                    }}
                  />
                </div>
              )}
              <button
                type="button"
                onClick={() => removeLeverRow(row.id)}
                className="ml-auto text-ink-subtle hover:text-danger-ink"
                aria-label="Remove lever"
              >
                <X size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addLeverRow}
            disabled={leverRows.length >= MAX_LEVERS}
            className="inline-flex items-center gap-1 text-sm font-medium text-fidelity-green disabled:text-ink-subtle"
          >
            <Plus size={16} /> Add lever
          </button>
        </div>

        <div className="border-t border-border pt-3">
          <button
            type="button"
            onClick={() => setShowImport((v) => !v)}
            className="inline-flex items-center gap-1 text-sm font-medium text-ink-muted hover:text-ink"
          >
            <Upload size={14} /> {showImport ? 'Hide' : 'Import from YAML'}
          </button>
          {showImport && (
            <div className="mt-2 space-y-2">
              <textarea
                className="w-full rounded-md border border-border-strong p-2 font-mono text-xs shadow-sm"
                rows={8}
                placeholder="Paste an existing spec.yaml, or upload one below."
                value={importYaml}
                onChange={(e) => setImportYaml(e.target.value)}
              />
              <div className="flex items-center gap-2">
                <input
                  type="file"
                  accept=".yaml,.yml"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    file.text().then(setImportYaml);
                  }}
                  className="text-xs"
                />
                <button
                  type="button"
                  onClick={handleImport}
                  disabled={importLoading || importYaml.trim() === ''}
                  className="rounded-md bg-surface-disabled px-3 py-1.5 text-sm font-medium text-ink-inverse disabled:bg-surface-disabled"
                >
                  {importLoading ? <Loader2 className="animate-spin" size={14} /> : 'Import'}
                </button>
              </div>
              {importError && <p className="text-sm text-danger-ink">{errorText(importError)}</p>}
            </div>
          )}
        </div>
      </div>

      {/* Step 2: Objective & constraints */}
      <div className="bg-surface-raised rounded-lg shadow p-6 space-y-4">
        <StepHeader n={2} title="Set the objective and constraints">
          1-2 objectives (a second one unlocks the Pareto frontier). Constraints are hard guardrails.
        </StepHeader>

        <div className="space-y-2">
          {objectiveRows.map((row) => (
            <div key={row.id} className="flex items-center gap-2">
              <select
                className="rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={row.metric}
                onChange={(e) => updateObjectiveRow(row.id, { metric: e.target.value })}
              >
                {OBJECTIVE_METRICS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <div className="flex rounded-md border border-border-strong overflow-hidden text-sm">
                {(['minimize', 'maximize'] as ObjectiveDirection[]).map((dir) => (
                  <button
                    key={dir}
                    type="button"
                    onClick={() => updateObjectiveRow(row.id, { direction: dir })}
                    className={`px-3 py-2 ${row.direction === dir ? 'bg-fidelity-green text-ink-inverse' : 'bg-surface-raised text-ink-muted'}`}
                  >
                    {dir}
                  </button>
                ))}
              </div>
              {objectiveRows.length > 1 && (
                <button type="button" onClick={() => removeObjectiveRow(row.id)} className="text-ink-subtle hover:text-danger-ink">
                  <X size={16} />
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            onClick={addObjectiveRow}
            disabled={objectiveRows.length >= 2}
            className="inline-flex items-center gap-1 text-sm font-medium text-fidelity-green disabled:text-ink-subtle"
          >
            <Plus size={16} /> Add objective (unlocks Pareto frontier)
          </button>
        </div>

        <div className="space-y-2 border-t border-border pt-3">
          {constraintRows.map((row) => (
            <div key={row.id} className="flex flex-wrap items-center gap-2">
              <select
                className="rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={row.metric}
                onChange={(e) => updateConstraintRow(row.id, { metric: e.target.value })}
              >
                {CONSTRAINT_METRICS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <select
                className="rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={row.operator}
                onChange={(e) => updateConstraintRow(row.id, { operator: e.target.value as ConstraintOperator })}
              >
                {CONSTRAINT_OPERATORS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
              <input
                type="number"
                placeholder="threshold"
                className="w-28 rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={row.threshold}
                onChange={(e) => updateConstraintRow(row.id, { threshold: e.target.value })}
              />
              <input
                type="number"
                placeholder="percentile"
                title={
                  percentileEnabled
                    ? '1-99; evaluated against the ensemble database'
                    : 'Set an ensemble database below to enable percentile evaluation -- otherwise this falls back to a point estimate'
                }
                disabled={!percentileEnabled}
                className="w-24 rounded-md border border-border-strong p-2 text-sm shadow-sm disabled:bg-surface-subtle disabled:text-ink-subtle"
                value={row.percentile}
                onChange={(e) => updateConstraintRow(row.id, { percentile: e.target.value })}
              />
              <button type="button" onClick={() => removeConstraintRow(row.id)} className="text-ink-subtle hover:text-danger-ink">
                <X size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addConstraintRow}
            className="inline-flex items-center gap-1 text-sm font-medium text-fidelity-green"
          >
            <Plus size={16} /> Add constraint
          </button>
        </div>
      </div>

      {/* Step 3: Baseline & run parameters */}
      <div className="bg-surface-raised rounded-lg shadow p-6 space-y-4">
        <StepHeader n={3} title="Baseline and run budget">
          Every candidate overlays your declared levers onto this baseline configuration.
        </StepHeader>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-sm text-ink-muted">
            <input
              type="checkbox"
              checked={useWorkspaceBaseline}
              disabled={!activeWorkspace}
              onChange={(e) => setUseWorkspaceBaseline(e.target.checked)}
            />
            Use active workspace's base config{activeWorkspace ? ` (${activeWorkspace.name})` : ''}
          </label>
          {!useWorkspaceBaseline && (
            <div>
              <label className="block text-sm font-medium text-ink-muted">Baseline config path</label>
              <input
                type="text"
                className="mt-1 w-full rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={configPath}
                onChange={(e) => setConfigPath(e.target.value)}
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-ink-muted">Ensemble database (optional)</label>
            <input
              type="text"
              placeholder="/path/to/ensemble.duckdb"
              className="mt-1 w-full rounded-md border border-border-strong p-2 text-sm shadow-sm"
              value={ensembleDatabase}
              onChange={(e) => setEnsembleDatabase(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink-muted">Max runs</label>
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded-md border border-border-strong p-2 text-sm shadow-sm"
              value={maxRuns}
              onChange={(e) => setMaxRuns(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink-muted">Search seed (optional)</label>
            <input
              type="number"
              className="mt-1 w-full rounded-md border border-border-strong p-2 text-sm shadow-sm"
              value={searchSeed}
              onChange={(e) => setSearchSeed(e.target.value)}
            />
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-sm font-medium text-ink-muted hover:text-ink-muted"
        >
          {showAdvanced ? 'Hide advanced options' : 'Show advanced options'}
        </button>
        {showAdvanced && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-sm font-medium text-ink-muted">Parallel workers</label>
              <input
                type="number"
                min={1}
                className="mt-1 w-full rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={parallel}
                onChange={(e) => setParallel(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-muted">Database dir override</label>
              <input
                type="text"
                className="mt-1 w-full rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={databaseDir}
                onChange={(e) => setDatabaseDir(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-muted">Output dir override</label>
              <input
                type="text"
                className="mt-1 w-full rounded-md border border-border-strong p-2 text-sm shadow-sm"
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
              />
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 border-t border-border pt-3">
          <button
            type="button"
            onClick={handleValidate}
            disabled={validateLoading}
            className="rounded-md border border-fidelity-green px-4 py-2 text-sm font-medium text-fidelity-green disabled:opacity-50"
          >
            {validateLoading ? <Loader2 className="animate-spin" size={14} /> : 'Validate'}
          </button>
          {validateError && <p className="text-sm text-danger-ink">{validateError}</p>}
          {validation?.valid && (
            <p className="text-sm text-success-ink">
              Spec is valid -- seed phase will try {validation.seed_phase_count} candidate(s).
            </p>
          )}
        </div>
      </div>

      {/* Step 4: Run + results */}
      <div className="bg-surface-raised rounded-lg shadow p-6 space-y-4">
        <StepHeader n={4} title="Run the search and review candidates">
          Each candidate is an isolated scenario simulation, so a search of {maxRuns} candidates can
          take several minutes.
        </StepHeader>

        <button
          type="button"
          onClick={handleRun}
          disabled={runLoading}
          className="rounded-md bg-fidelity-green px-4 py-2 text-sm font-medium text-ink-inverse disabled:opacity-50"
        >
          {runLoading ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="animate-spin" size={14} /> Running search…
            </span>
          ) : (
            'Start Optimizer Search'
          )}
        </button>
        {runError && <p className="text-sm text-danger-ink">{errorText(runError)}</p>}

        {run && (
          <div className="space-y-4">
            {run.binding_infeasible_constraints && run.binding_infeasible_constraints.length > 0 && (
              <div className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-surface p-3 text-sm text-warning-ink">
                <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                <span>
                  No feasible candidates -- every evaluated design failed:{' '}
                  <strong>{run.binding_infeasible_constraints.join(', ')}</strong>.
                </span>
              </div>
            )}

            {isTwoObjective && run.pareto_frontier !== null && frontierMetrics && (
              <div className="bg-surface-raised rounded-lg shadow p-4">
                <h3 className="mb-2 font-semibold text-ink">Pareto frontier</h3>
                <ResponsiveContainer width="100%" height={320}>
                  <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid.line} />
                    <XAxis type="number" dataKey="x" name={frontierMetrics[0]} stroke={chartTheme.axis.line} />
                    <YAxis type="number" dataKey="y" name={frontierMetrics[1]} stroke={chartTheme.axis.line} />
                    <ZAxis range={[80, 80]} />
                    <Tooltip
                      cursor={{ stroke: chartTheme.grid.cursor, strokeDasharray: '3 3' }}
                      contentStyle={chartTheme.tooltip.contentStyle}
                      formatter={(value: number) => value}
                      labelFormatter={() => ''}
                    />
                    <Legend formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
                    <Scatter
                      name="Candidates"
                      data={run.candidates
                        .filter((c) => c.status === 'feasible')
                        .map((c) => ({
                          x: c.objective_values[frontierMetrics[0]] ?? null,
                          y: c.objective_values[frontierMetrics[1]] ?? null,
                          candidate_id: c.candidate_id,
                          onFrontier: run.pareto_frontier?.includes(c.candidate_id) ?? false,
                        }))}
                      onClick={(d: any) => setSelectedCandidateId(d.candidate_id)}
                    >
                      {run.candidates
                        .filter((c) => c.status === 'feasible')
                        .map((c) => (
                          <Cell
                            key={c.candidate_id}
                            fill={colorByCandidate[c.candidate_id]}
                            stroke={run.pareto_frontier?.includes(c.candidate_id) ? chartTheme.semantic.frontierOutline : 'none'}
                            strokeWidth={run.pareto_frontier?.includes(c.candidate_id) ? 2 : 0}
                          />
                        ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
                <p className="mt-1 text-xs text-ink-subtle">
                  Outlined points are on the Pareto frontier ({run.pareto_frontier.length} candidate(s)).
                </p>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-border text-sm">
                <thead>
                  <tr className="text-left text-xs font-medium uppercase text-ink-muted">
                    {!isTwoObjective && <th className="px-3 py-2">Rank</th>}
                    <th className="px-3 py-2">Candidate</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Lever values</th>
                    <th className="px-3 py-2">Objective(s)</th>
                    <th className="px-3 py-2">Constraints</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {run.candidates.map((c) => (
                    <tr
                      key={c.candidate_id}
                      onClick={() => setSelectedCandidateId(c.candidate_id)}
                      className={`cursor-pointer hover:bg-surface-subtle ${selectedCandidateId === c.candidate_id ? 'bg-info-surface' : ''}`}
                    >
                      {!isTwoObjective && (
                        <td className="px-3 py-2 text-ink-muted">{rankedOrder.get(c.candidate_id) ?? '—'}</td>
                      )}
                      <td className="px-3 py-2 font-mono text-xs">
                        <span
                          className="mr-1 inline-block h-2 w-2 rounded-full align-middle"
                          style={{ backgroundColor: colorByCandidate[c.candidate_id] }}
                        />
                        {c.candidate_id}
                        {c.is_duplicate_of && (
                          <span className="ml-1 rounded bg-surface-subtle px-1 text-[10px] text-ink-muted">
                            dup of {c.is_duplicate_of}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-medium ${
                            c.status === 'feasible'
                              ? 'bg-success-surface text-success-ink'
                              : c.status === 'infeasible'
                              ? 'bg-danger-surface text-danger-ink'
                              : 'bg-surface-subtle text-ink-muted'
                          }`}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="max-w-xs truncate px-3 py-2 text-xs text-ink-muted">
                        {Object.entries(c.lever_values)
                          .map(([k, v]) => `${k}=${v}`)
                          .join(', ')}
                      </td>
                      <td className="px-3 py-2 text-xs text-ink-muted">
                        {Object.entries(c.objective_values)
                          .map(([k, v]) => `${k}=${v ?? '—'}`)
                          .join(', ')}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {c.constraint_results.length === 0
                          ? '—'
                          : c.constraint_results.map((r) => (
                              <span
                                key={r.metric}
                                className={`mr-1 ${r.satisfied ? 'text-success-ink' : 'text-danger-ink'}`}
                              >
                                {r.satisfied ? '✓' : '✗'} {r.metric}
                              </span>
                            ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selectedCandidate && (
              <div className="rounded-md border border-border bg-surface-subtle p-4 text-sm">
                <h4 className="mb-2 font-semibold text-ink">{selectedCandidate.candidate_id} detail</h4>
                <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-ink-muted">
                  {JSON.stringify(selectedCandidate, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
