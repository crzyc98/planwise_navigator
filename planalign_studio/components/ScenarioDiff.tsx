import React, { useEffect, useMemo, useState } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
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
  getScenarioConfigDiff,
  listScenarios,
  WorkforceMetrics,
} from '../services/api';
import { useWorkspaceNavigate } from '../hooks/useWorkspaceNavigation';
import { LayoutContextType } from './Layout';

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
  { key: 'avg-compensation', label: 'Average Compensation', format: 'currency', source: 'workforce', select: m => m.avg_compensation },
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

function ConfigDeltaRow({ delta }: Readonly<{ delta: ConfigDelta }>) {
  const statusLabel = {
    changed: 'Changed',
    only_a: 'Only in A',
    only_b: 'Only in B',
  }[delta.status];
  return (
    <tr className="border-t border-border align-top">
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-ink">{friendlyLabel(delta.path)}</span>
          <span className="rounded-full bg-info-surface px-2 py-0.5 text-xs font-medium text-info-ink">{statusLabel}</span>
        </div>
        <code className="text-xs text-ink-muted">{delta.path}</code>
      </td>
      <td className="px-4 py-3 text-sm text-ink-muted">{displayConfigValue(delta.a)}</td>
      <td className="px-4 py-3 text-sm text-ink-muted">{displayConfigValue(delta.b)}</td>
    </tr>
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

  const queryError = useMemo(() => {
    if (!scenarioA || !scenarioB) return 'Select exactly two completed scenarios to open a diff.';
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
        const scenarios = await listScenarios(activeWorkspace.id);
        const selected = [scenarioA, scenarioB].map(id => scenarios.find(item => item.id === id));
        if (selected.some(item => !item)) throw new Error('Both scenarios must belong to the active workspace.');
        if (selected.some(item => item?.status !== 'completed')) throw new Error('Both scenarios must be completed before comparison.');
        const [metricResponse, configResponse] = await Promise.all([
          compareScenarios(activeWorkspace.id, [scenarioA, scenarioB], scenarioA),
          getScenarioConfigDiff(activeWorkspace.id, scenarioA, scenarioB),
        ]);
        if (!cancelled) {
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

  if (loading) return <div className="flex h-96 items-center justify-center"><Loader2 className="animate-spin text-fidelity-green" size={44} /></div>;
  if (error || !comparison || !configDiff) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-center">
        <AlertCircle className="mb-3 text-danger-ink" size={44} />
        <h1 className="text-xl font-semibold text-ink">Unable to open scenario diff</h1>
        <p className="mt-2 max-w-xl text-ink-muted">{error ?? 'Comparison data is unavailable.'}</p>
        <button onClick={() => navigate('/scenarios')} className="mt-5 rounded-lg bg-fidelity-green px-4 py-2 font-medium text-ink-inverse">Choose scenarios</button>
      </div>
    );
  }

  const nameA = configDiff.scenario_names[scenarioA] ?? scenarioA;
  const nameB = configDiff.scenario_names[scenarioB] ?? scenarioB;
  const provenanceA = configDiff.provenance[scenarioA];
  const provenanceB = configDiff.provenance[scenarioB];

  return (
    <div className="space-y-6 pb-8">
      <header className="flex items-start gap-4">
        <button onClick={() => navigate(-1)} className="rounded-lg p-2 text-ink-muted hover:bg-surface-subtle"><ArrowLeft size={20} /></button>
        <div className="flex-1">
          <p className="text-sm font-medium uppercase tracking-wide text-fidelity-green">Scenario diff</p>
          <h1 className="text-2xl font-bold text-ink">{nameA} <span className="text-ink-subtle">vs</span> {nameB}</h1>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            {[provenanceA, provenanceB].map((item, index) => (
              <span key={index} className="rounded-full bg-surface-subtle px-3 py-1 text-ink-muted">
                {index === 0 ? nameA : nameB}: {item?.available ? `seed ${item.random_seed ?? 'unknown'} · ${item.config_fingerprint ?? 'unknown'} · ${item.run_timestamp ? new Date(item.run_timestamp).toLocaleString() : 'time unknown'}` : 'provenance unavailable'}
              </span>
            ))}
          </div>
        </div>
      </header>

      {configDiff.seeds_match === false && (
        <div className="flex gap-3 rounded-lg border border-warning-border bg-warning-surface p-4 text-warning-ink"><AlertTriangle className="shrink-0" /><span><strong>Seeds differ.</strong> Differences may include seed noise.</span></div>
      )}
      {configDiff.drift_warning && (
        <div className="flex gap-3 rounded-lg border border-danger-border bg-danger-surface p-4 text-danger-ink"><AlertTriangle className="shrink-0" /><span><strong>Provenance warning.</strong> Results may be mixed-generation or no longer match the displayed configuration.</span></div>
      )}
      {!configDiff.drift_warning && (provenanceA?.available === false || provenanceB?.available === false) && (
        <div className="flex gap-3 rounded-lg border border-warning-border bg-warning-surface p-4 text-warning-ink"><AlertTriangle className="shrink-0" /><span><strong>Provenance unavailable.</strong> At least one scenario predates run tracking, so drift cannot be verified — results may still be mixed-generation.</span></div>
      )}

      <section className="overflow-hidden rounded-xl border border-border bg-surface-raised shadow-sm">
        <div className="flex items-center justify-between px-5 py-4">
          <div><h2 className="font-semibold text-ink">Configuration changes</h2><p className="text-sm text-ink-muted">Effective settings used by the workspace and scenario overrides</p></div>
          <span className="rounded-full bg-surface-subtle px-3 py-1 text-sm text-ink-muted">{configDiff.differences.length} changed</span>
        </div>
        {configDiff.differences.length === 0 ? (
          <div className="flex items-center gap-2 border-t border-border px-5 py-5 text-ink-muted"><CheckCircle className="text-success-ink" />No effective settings differ.</div>
        ) : (
          <div className="overflow-x-auto"><table className="min-w-full"><thead className="bg-surface-subtle text-left text-xs uppercase text-ink-muted"><tr><th className="px-4 py-3">Setting</th><th className="px-4 py-3">{nameA}</th><th className="px-4 py-3">{nameB}</th></tr></thead><tbody>{configDiff.differences.map(delta => <ConfigDeltaRow key={delta.path} delta={delta} />)}</tbody></table></div>
        )}
        <div className="border-t border-border px-5 py-3 text-sm text-ink-muted">
          {configDiff.unchanged_count} unchanged settings omitted
        </div>
      </section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {METRICS.map(metric => <MetricPanel key={metric.key} comparison={comparison} metric={metric} scenarioA={scenarioA} scenarioB={scenarioB} nameA={nameA} nameB={nameB} />)}
      </div>
    </div>
  );
}
