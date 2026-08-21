import React, { useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, Info } from 'lucide-react';
import { useChartTheme } from '../hooks/useChartTheme';

export interface EnsembleDistributionRow {
  ensemble_id: string;
  scenario_id: string;
  metric: string;
  simulation_year: number;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  n_seeds: number;
  n_seeds_requested: number;
  is_sufficient: boolean;
}

export interface EnsembleRiskStatement {
  metric: string;
  threshold_value: number;
  simulation_year: number | null;
  exceedance_probability: number | null;
  n_seeds: number;
  is_evaluable: boolean;
  reason?: string | null;
}

export interface EnsembleAttributionRow {
  metric: string;
  simulation_year: number;
  subsystem: string;
  variance_share: number | null;
  ci_low: number | null;
  ci_high: number | null;
  stochastic_status: 'stochastic' | 'not_stochastic';
}

export interface EnsembleAnalysisData {
  distributions: EnsembleDistributionRow[];
  riskStatements?: EnsembleRiskStatement[];
  attribution?: EnsembleAttributionRow[];
}

const METRIC_LABELS: Record<string, string> = {
  active_headcount: 'Active headcount',
  total_compensation: 'Total compensation',
  employer_match_cost: 'Employer match cost',
  total_employer_plan_cost: 'Total employer plan cost',
  participation_rate: 'Participation rate',
  avg_deferral_rate: 'Average deferral rate',
};

function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatValue(metric: string, value: number | null): string {
  if (value === null || !Number.isFinite(value)) return 'Unavailable';
  if (metric.endsWith('_rate')) return `${(value * 100).toFixed(1)}%`;
  if (metric.includes('cost') || metric.includes('compensation')) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
  }
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value);
}

function formatProbability(value: number | null): string {
  return value === null ? 'Unavailable' : `${(value * 100).toFixed(1)}%`;
}

function DistributionChart({ metric, rows }: Readonly<{ metric: string; rows: EnsembleDistributionRow[] }>) {
  const chartTheme = useChartTheme();
  const data = useMemo(() => rows.filter((row) => row.is_sufficient && row.p10 !== null && row.p50 !== null && row.p90 !== null).map((row) => ({
    ...row,
    band: (row.p90 ?? 0) - (row.p10 ?? 0),
  })), [rows]);

  return (
    <div className="h-72" aria-label={`${metricLabel(metric)} P10 P50 P90 chart`}>
      {data.length === 0 ? (
        <div className="flex h-full items-center justify-center rounded-lg bg-surface-subtle text-sm text-ink-muted">
          No seed-sufficient distribution is available for this metric.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 18, bottom: 4, left: 18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid.line} />
            <XAxis dataKey="simulation_year" stroke={chartTheme.axis.line} />
            <YAxis stroke={chartTheme.axis.line} tickFormatter={(value) => formatValue(metric, Number(value))} width={88} />
            <Tooltip
              contentStyle={chartTheme.tooltip.contentStyle}
              formatter={(value, name) => [formatValue(metric, Number(value)), String(name)]}
              labelFormatter={(label) => `Year ${label}`}
            />
            <Area dataKey="p10" stackId="percentile-band" stroke="none" fill="transparent" name="P10 baseline" />
            <Area dataKey="band" stackId="percentile-band" stroke="none" fill={chartTheme.colorAt(0)} fillOpacity={0.2} name="P10–P90 range" />
            <Line type="monotone" dataKey="p50" stroke={chartTheme.colorAt(0)} strokeWidth={3} dot={{ r: 3 }} name="P50" />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function RiskStatements({ statements }: Readonly<{ statements: EnsembleRiskStatement[] }>) {
  if (statements.length === 0) return null;
  return (
    <section className="mt-5 border-t border-border pt-4" aria-labelledby="ensemble-risk-heading">
      <h3 id="ensemble-risk-heading" className="flex items-center gap-2 text-sm font-semibold text-ink">
        <AlertTriangle size={16} className="text-warning-ink" /> Threshold-exceedance risk
      </h3>
      <div className="mt-3 space-y-2">
        {statements.map((statement, index) => (
          <p key={`${statement.metric}-${statement.simulation_year ?? 'unavailable'}-${index}`} className="text-sm text-ink-muted">
            {statement.is_evaluable && statement.simulation_year !== null
              ? `In ${statement.simulation_year}, P(${metricLabel(statement.metric).toLowerCase()} > ${formatValue(statement.metric, statement.threshold_value)}) = ${formatProbability(statement.exceedance_probability)} across ${statement.n_seeds} seeds.`
              : `${metricLabel(statement.metric)} risk is not evaluable: ${statement.reason ?? 'the metric is unavailable from this ensemble.'}`}
          </p>
        ))}
      </div>
    </section>
  );
}

function ExperimentalAttribution({ rows }: Readonly<{ rows: EnsembleAttributionRow[] }>) {
  if (rows.length === 0) return null;
  return (
    <section className="mt-8 rounded-xl border border-warning-border bg-warning-surface p-5" aria-labelledby="experimental-attribution-heading">
      <h2 id="experimental-attribution-heading" className="flex items-center gap-2 text-base font-semibold text-warning-ink">
        <Info size={17} /> [EXPERIMENTAL] Variance attribution
      </h2>
      <p className="mt-2 text-sm text-warning-ink">
        These are anchor-averaged conditional variance shares, not a ranked decomposition. Shares do not need to sum to 100%; interaction effects are not separated. This view is for analyst exploration and is not included in client-facing exports.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-warning-border text-xs uppercase tracking-wide text-warning-ink">
            <tr><th className="px-3 py-2">Metric / year</th><th className="px-3 py-2">Subsystem</th><th className="px-3 py-2">Share</th><th className="px-3 py-2">Bootstrap interval</th></tr>
          </thead>
          <tbody className="divide-y divide-warning-border">
            {rows.map((row) => (
              <tr key={`${row.metric}-${row.simulation_year}-${row.subsystem}`}>
                <td className="px-3 py-2 text-ink">{metricLabel(row.metric)} · {row.simulation_year}</td>
                <td className="px-3 py-2 capitalize text-ink">{row.subsystem.replaceAll('_', ' ')}</td>
                <td className="px-3 py-2 text-ink">{row.stochastic_status === 'not_stochastic' || row.variance_share === null ? 'Not stochastic' : formatProbability(row.variance_share)}</td>
                <td className="px-3 py-2 text-ink">{row.ci_low === null || row.ci_high === null ? 'Unavailable' : `${formatProbability(row.ci_low)}–${formatProbability(row.ci_high)}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function EnsembleAnalysisPanel({ data }: Readonly<{ data: EnsembleAnalysisData }>) {
  const grouped = useMemo(() => {
    const groups = new Map<string, EnsembleDistributionRow[]>();
    for (const row of data.distributions) groups.set(row.metric, [...(groups.get(row.metric) ?? []), row]);
    return [...groups.entries()].sort(([a], [b]) => metricLabel(a).localeCompare(metricLabel(b)));
  }, [data.distributions]);

  return (
    <div className="space-y-6" data-testid="ensemble-analysis-panel">
      <div>
        <h1 className="text-2xl font-bold text-ink">Ensemble analysis</h1>
        <p className="mt-1 text-sm text-ink-muted">P10/P50/P90 outcome bands from the selected ensemble aggregate database.</p>
      </div>
      {grouped.length === 0 ? <div className="rounded-xl border border-border bg-surface-raised p-8 text-center text-sm text-ink-muted">No ensemble distributions are available.</div> : grouped.map(([metric, rows]) => (
        <section key={metric} className="rounded-xl border border-border bg-surface-raised p-5 shadow-sm">
          <h2 className="text-base font-semibold text-ink">{metricLabel(metric)}</h2>
          <p className="mt-1 text-xs text-ink-muted">Percentile bands show seed variation by simulation year.</p>
          <DistributionChart metric={metric} rows={rows} />
          <RiskStatements statements={(data.riskStatements ?? []).filter((statement) => statement.metric === metric)} />
        </section>
      ))}
      <ExperimentalAttribution rows={data.attribution ?? []} />
    </div>
  );
}

export { formatValue, formatProbability, metricLabel };
