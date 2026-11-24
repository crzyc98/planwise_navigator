import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowLeftRight,
  CheckCircle,
  Loader2,
} from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { useChartTheme } from '../hooks/useChartTheme';
import {
  compareScenarios,
  ComparisonResponse,
  ConfigDelta,
  ConfigDiffResponse,
  DCPlanMetrics,
  getScenario,
  getScenarioConfigDiff,
  Scenario,
  updateScenario,
  WorkforceMetrics,
} from '../services/api';
import { applyDeltaToOverrides, canApplyDelta } from './applyConfigDelta';
import { useWorkspaceNavigate } from '../hooks/useWorkspaceNavigation';
import ComparisonIntegrityBanner from './ComparisonIntegrityBanner';
import CrossScenarioEvidencePanel from './CrossScenarioEvidencePanel';
import { unsetLabel } from './configDiff';
import { LayoutContextType } from './Layout';
import { loadDiffSelection } from './comparisonSelection';
import SelectedComparisonRuns from './SelectedComparisonRuns';

interface ChartPoint {
  year: number;
  a?: number;
  b?: number;
  delta?: number;
}

interface WorkforceMetricDefinition {
  key: string;
  label: string;
  format: 'integer' | 'currency' | 'percent';
  source: 'workforce';
  select: (metrics: WorkforceMetrics) => number | undefined;
}

interface DCPlanMetricDefinition {
  key: string;
  label: string;
  format: 'integer' | 'currency' | 'percent';
  source: 'dc';
  select: (metrics: DCPlanMetrics) => number | undefined;
}

type MetricDefinition = WorkforceMetricDefinition | DCPlanMetricDefinition;

const METRICS: MetricDefinition[] = [
  { key: 'headcount', label: 'Headcount', format: 'integer', source: 'workforce', select: m => m.headcount },
  { key: 'avg-compensation', label: 'Average Compensation', format: 'currency', source: 'workforce', select: m => m.avg_compensation ?? undefined },
  { key: 'participation', label: 'Participation Rate', format: 'percent', source: 'dc', select: m => m.participation_rate },
  { key: 'employer-match', label: 'Employer Match Cost', format: 'currency', source: 'dc', select: m => m.total_employer_match },
  { key: 'employer-cost', label: 'Total Employer Cost', format: 'currency', source: 'dc', select: m => m.total_employer_cost },
];

const FRIENDLY_LABELS: Record<string, string> = {
  'simulation.target_growth_rate': 'Target growth rate',
  'compensation.cola_rate': 'Cost-of-living adjustment',
  'compensation.merit_budget': 'Merit budget',
  'employer_match.active_formula': 'Employer match formula',
  'enrollment.auto_enrollment.enabled': 'Automatic enrollment',
  'plan_eligibility.minimum_age': 'Minimum eligibility age',
  'plan_eligibility.minimum_tenure_years': 'Eligibility service requirement',
};

function friendlyLabel(path: string): string {
  if (FRIENDLY_LABELS[path]) return FRIENDLY_LABELS[path];
  const segment = path.split('.').at(-1) ?? path;
  return segment.replaceAll('_', ' ').replace(/^./, value => value.toUpperCase());
}

function formatMetric(value: number, format: MetricDefinition['format']): string {
  if (format === 'currency') {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
  }
  if (format === 'percent') return `${value.toFixed(1)}%`;
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
}

function displayConfigValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function buildChartData(
  comparison: ComparisonResponse,
  metric: MetricDefinition,
  scenarioA: string,
  scenarioB: string,
): ChartPoint[] {
  if (metric.source === 'workforce') {
    return comparison.workforce_comparison.map(year => ({
      year: year.year,
      a: year.values[scenarioA] && metric.select(year.values[scenarioA]),
      b: year.values[scenarioB] && metric.select(year.values[scenarioB]),
      delta: year.deltas[scenarioB] && metric.select(year.deltas[scenarioB]),
    }));
  }
  return comparison.dc_plan_comparison.map(year => ({
    year: year.year,
    a: year.values[scenarioA] && metric.select(year.values[scenarioA]),
    b: year.values[scenarioB] && metric.select(year.values[scenarioB]),
    delta: year.deltas[scenarioB] && metric.select(year.deltas[scenarioB]),
  }));
}

function MetricPanel({
  comparison,
  metric,
  scenarioA,
  scenarioB,
  nameA,
  nameB,
}: Readonly<{
  comparison: ComparisonResponse;
  metric: MetricDefinition;
  scenarioA: string;
  scenarioB: string;
  nameA: string;
  nameB: string;
}>) {
  const chartTheme = useChartTheme();
  const data = buildChartData(comparison, metric, scenarioA, scenarioB);
  const finalDelta = [...data].reverse().find(point => point.delta !== undefined)?.delta;
  return (
    <section className="rounded-xl border border-border bg-surface-raised p-5 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-4">
        <h2 className="font-semibold text-ink">{metric.label}</h2>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${
          finalDelta === undefined || finalDelta === 0
            ? 'bg-surface-subtle text-ink-muted'
            : finalDelta > 0
              ? 'bg-success-surface text-success-ink'
              : 'bg-danger-surface text-danger-ink'
        }`}>
          Final Δ {finalDelta === undefined ? 'Unavailable' : formatMetric(finalDelta, metric.format)}
        </span>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid.line} />
            <XAxis dataKey="year" stroke={chartTheme.axis.line} />
            <YAxis stroke={chartTheme.axis.line} tickFormatter={value => formatMetric(Number(value), metric.format)} width={84} />
            <Tooltip contentStyle={chartTheme.tooltip.contentStyle} />
            <Legend formatter={(value) => <span style={{ color: chartTheme.legendText }}>{value}</span>} />
            <Line type="monotone" dataKey="a" name={nameA} stroke={chartTheme.colorAt(0)} strokeWidth={3} connectNulls={false} />
            <Line type="monotone" dataKey="b" name={nameB} stroke={chartTheme.colorAt(1)} strokeWidth={3} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

type Side = 'a' | 'b';

interface ApplyState {
  status: 'saving' | 'done' | 'error';
  to: Side;
  message?: string;
}

interface ConfigDeltaRowProps {
  delta: ConfigDelta;
  names: Record<Side, string>;
  apply?: ApplyState;
  /** Another copy is saving; one at a time so saves can't overwrite each other. */
  locked: boolean;
  onApply?: (delta: ConfigDelta, to: Side) => void;
}

function ApplyButton({ from, to, names, disabled, onClick }: Readonly<{
  from: Side;
  to: Side;
  names: Record<Side, string>;
  disabled: boolean;
  onClick: () => void;
}>) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={`Save ${names[from]}'s value into ${names[to]}. Rerun ${names[to]} to see the effect.`}
      className="mt-1 inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-xs font-medium text-brand-ink hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50"
    >
      {to === 'a' && '← '}Use in {names[to]}{to === 'b' && ' →'}
    </button>
  );
}

function ApplyStatus({ apply, names }: Readonly<{ apply: ApplyState; names: Record<Side, string> }>) {
  if (apply.status === 'saving') return <span className="text-xs text-ink-muted">Saving to {names[apply.to]}…</span>;
  if (apply.status === 'error') return <span className="text-xs text-danger-ink">{apply.message ?? 'Unable to save.'}</span>;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-success-surface px-2 py-0.5 text-xs font-medium text-success-ink">
      <ArrowLeftRight size={12} />Saved to {names[apply.to]} · rerun to see it
    </span>
  );
}

function ConfigDeltaRow({ delta, names, apply, locked, onApply }: Readonly<ConfigDeltaRowProps>) {
  const statusLabel = {
    changed: 'Changed',
    only_a: 'Only in A',
    only_b: 'Only in B',
  }[delta.status];
  const canCopy = onApply !== undefined && delta.status === 'changed' && canApplyDelta(delta.path);
  const valueCell = (side: Side) => {
    const other: Side = side === 'a' ? 'b' : 'a';
    return (
      <td className="px-4 py-3 text-sm text-ink-muted">
        <div>{unsetLabel(delta, side) ?? displayConfigValue(delta[side])}</div>
        {canCopy && (
          <ApplyButton from={side} to={other} names={names} disabled={locked} onClick={() => onApply(delta, other)} />
        )}
      </td>
    );
  };
  return (
    <tr className="border-t border-border align-top">
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-ink">{friendlyLabel(delta.path)}</span>
          <span className="rounded-full bg-info-surface px-2 py-0.5 text-xs font-medium text-info-ink">{statusLabel}</span>
          {apply && <ApplyStatus apply={apply} names={names} />}
        </div>
        <code className="text-xs text-ink-muted">{delta.path}</code>
      </td>
      {valueCell('a')}
      {valueCell('b')}
    </tr>
  );
}

/**
 * Seed and provenance warnings from the config diff. The like-for-like check
 * says all of this (and more), so they show only when that check fails.
 */
export function ProvenanceWarnings({ configDiff, scenarioA, scenarioB }: Readonly<{
  configDiff: ConfigDiffResponse;
  scenarioA: string;
  scenarioB: string;
}>) {
  const provenanceA = configDiff.provenance[scenarioA];
  const provenanceB = configDiff.provenance[scenarioB];
  return (
    <>
      {configDiff.seeds_match === false && (
        <div className="flex gap-3 rounded-lg border border-warning-border bg-warning-surface p-4 text-warning-ink"><AlertTriangle className="shrink-0" /><span><strong>Seeds differ.</strong> Differences may include seed noise.</span></div>
      )}
      {configDiff.drift_warning && (
        <div className="flex gap-3 rounded-lg border border-danger-border bg-danger-surface p-4 text-danger-ink"><AlertTriangle className="shrink-0" /><span><strong>Provenance warning.</strong> Results may be mixed-generation or no longer match the displayed configuration.</span></div>
      )}
      {!configDiff.drift_warning && (provenanceA?.available === false || provenanceB?.available === false) && (
        <div className="flex gap-3 rounded-lg border border-warning-border bg-warning-surface p-4 text-warning-ink"><AlertTriangle className="shrink-0" /><span><strong>Provenance unavailable.</strong> At least one scenario predates run tracking, so drift cannot be verified — results may still be mixed-generation.</span></div>
      )}
    </>
  );
}

export default function ScenarioDiff() {
  const navigate = useWorkspaceNavigate();
  const [searchParams] = useSearchParams();
  const { activeWorkspace } = useOutletContext<LayoutContextType>();
  const scenarioA = searchParams.get('a') ?? '';
  const scenarioB = searchParams.get('b') ?? '';
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [configDiff, setConfigDiff] = useState<ConfigDiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedScenarios, setSelectedScenarios] = useState<Scenario[]>([]);
  const [applyStates, setApplyStates] = useState<Record<string, ApplyState>>({});
  const pairKey = `${scenarioA}|${scenarioB}`;
  const currentPair = useRef(pairKey);
  useEffect(() => {
    currentPair.current = pairKey;
    setApplyStates({});
  }, [pairKey]);

  const queryError = useMemo(() => {
    if (!scenarioA || !scenarioB) return 'Select exactly two scenarios with successful results to open a diff.';
    if (scenarioA === scenarioB) return 'Select two distinct scenarios to open a diff.';
    return null;
  }, [scenarioA, scenarioB]);

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      if (queryError || !activeWorkspace?.id) {
        setError(queryError ?? 'Select a workspace before opening a scenario diff.');
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const selected = await loadDiffSelection(activeWorkspace.id, scenarioA, scenarioB);
        const [metricResponse, configResponse] = await Promise.all([
          compareScenarios(activeWorkspace.id, [scenarioA, scenarioB], scenarioA),
          getScenarioConfigDiff(activeWorkspace.id, scenarioA, scenarioB),
        ]);
        if (!cancelled) {
          setSelectedScenarios(selected);
          setComparison(metricResponse);
          setConfigDiff(configResponse);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'Unable to load scenario diff.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [activeWorkspace?.id, queryError, scenarioA, scenarioB]);

  if (loading) return <div className="flex h-96 items-center justify-center"><Loader2 className="animate-spin text-brand-ink" size={44} /></div>;
  if (error || !comparison || !configDiff) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-center">
        <AlertCircle className="mb-3 text-danger-ink" size={44} />
        <h1 className="text-xl font-semibold text-ink">Unable to open scenario diff</h1>
        <p className="mt-2 max-w-xl text-ink-muted">{error ?? 'Comparison data is unavailable.'}</p>
        <button onClick={() => navigate('/scenarios')} className="mt-5 rounded-lg bg-brand-green px-4 py-2 font-medium text-ink-inverse">Choose scenarios</button>
      </div>
    );
  }

  const nameA = configDiff.scenario_names[scenarioA] ?? scenarioA;
  const nameB = configDiff.scenario_names[scenarioB] ?? scenarioB;
  const names: Record<Side, string> = { a: nameA, b: nameB };
  const workspaceId = activeWorkspace.id;

  async function applyDelta(delta: ConfigDelta, to: Side): Promise<void> {
    const targetId = to === 'a' ? scenarioA : scenarioB;
    const value = to === 'a' ? delta.b : delta.a;
    const pair = pairKey;
    const setState = (state: ApplyState) => {
      // Drop results that land after the user moved to another pair.
      if (currentPair.current === pair) setApplyStates(prev => ({ ...prev, [delta.path]: state }));
    };
    setState({ status: 'saving', to });
    try {
      // Read the saved overrides fresh: they may have changed since the run.
      const target = await getScenario(workspaceId, targetId);
      if (target.status === 'running') throw new Error(`${names[to]} is running. Copy the setting after it finishes.`);
      const next = applyDeltaToOverrides(target.config_overrides ?? {}, delta.path, value);
      if (!next) throw new Error('This setting cannot be copied between scenarios.');
      await updateScenario(workspaceId, targetId, { config_overrides: next });
      setState({ status: 'done', to });
    } catch (caught) {
      setState({ status: 'error', to, message: caught instanceof Error ? caught.message : 'Unable to save.' });
    }
  }
  const saving = Object.values(applyStates).some(state => state.status === 'saving');
  const renderRow = (delta: ConfigDelta) => (
    <ConfigDeltaRow key={delta.path} delta={delta} names={names} apply={applyStates[delta.path]} locked={saving} onApply={(row, to) => { void applyDelta(row, to); }} />
  );
  const provenanceA = configDiff.provenance[scenarioA];
  const provenanceB = configDiff.provenance[scenarioB];

  return (
    <div className="space-y-6 pb-8">
      <header className="flex items-start gap-4">
        <button onClick={() => navigate(-1)} className="rounded-lg p-2 text-ink-muted hover:bg-surface-subtle"><ArrowLeft size={20} /></button>
        <div className="flex-1">
          <p className="text-sm font-medium uppercase tracking-wide text-brand-ink">Scenario diff</p>
          <h1 className="text-2xl font-bold text-ink">{nameA} <span className="text-ink-subtle">vs</span> {nameB}</h1>
          <button onClick={() => document.getElementById('explain-difference')?.scrollIntoView({ behavior: 'smooth' })} className="mt-1 text-sm font-medium text-brand-ink hover:underline">Explain the difference with a cited evidence pack ↓</button>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            {[provenanceA, provenanceB].map((item, index) => (
              <span key={index} className="rounded-full bg-surface-subtle px-3 py-1 text-ink-muted">
                {index === 0 ? nameA : nameB}: {item?.available ? `seed ${item.random_seed ?? 'unknown'} · ${item.config_fingerprint ?? 'unknown'} · ${item.run_timestamp ? new Date(item.run_timestamp).toLocaleString() : 'time unknown'}` : 'provenance unavailable'}
              </span>
            ))}
          </div>
        </div>
      </header>
      <SelectedComparisonRuns scenarios={selectedScenarios} />

      <ComparisonIntegrityBanner
        workspaceId={workspaceId}
        scenarioIds={[scenarioA, scenarioB]}
        anchorId={scenarioA}
        diffLinks={false}
        whenUnavailable={<ProvenanceWarnings configDiff={configDiff} scenarioA={scenarioA} scenarioB={scenarioB} />}
      />

      <section className="overflow-hidden rounded-xl border border-border bg-surface-raised shadow-sm">
        <div className="flex items-center justify-between px-5 py-4">
          <div><h2 className="font-semibold text-ink">Configuration changes</h2><p className="text-sm text-ink-muted">Settings each result ran with. Use the buttons to copy one setting to the other scenario; rerun it to see the effect.</p></div>
          <span className="rounded-full bg-surface-subtle px-3 py-1 text-sm text-ink-muted">{configDiff.differences.length} changed</span>
        </div>
        {configDiff.differences.length === 0 ? (
          <div className="flex items-center gap-2 border-t border-border px-5 py-5 text-ink-muted"><CheckCircle className="text-success-ink" />No effective settings differ.</div>
        ) : (
          <div className="overflow-x-auto"><table className="min-w-full"><thead className="bg-surface-subtle text-left text-xs uppercase text-ink-muted"><tr><th className="px-4 py-3">Setting</th><th className="px-4 py-3">{nameA}</th><th className="px-4 py-3">{nameB}</th></tr></thead><tbody>{configDiff.differences.map(renderRow)}</tbody></table></div>
        )}
        <div className="border-t border-border px-5 py-3 text-sm text-ink-muted">
          {configDiff.unchanged_count} unchanged settings omitted
        </div>
      </section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {METRICS.map(metric => <MetricPanel key={metric.key} comparison={comparison} metric={metric} scenarioA={scenarioA} scenarioB={scenarioB} nameA={nameA} nameB={nameB} />)}
      </div>

      <CrossScenarioEvidencePanel
        workspaceId={activeWorkspace.id}
        scenarioA={scenarioA}
        scenarioB={scenarioB}
        nameA={nameA}
        nameB={nameB}
        years={comparison.workforce_comparison.map(year => year.year)}
      />
    </div>
  );
}
