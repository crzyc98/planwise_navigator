import React, { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import {
  Users, DollarSign, TrendingUp, AlertTriangle, RefreshCw, Database, Loader2, ChevronDown,
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import { extractCensusPath } from './config/ConfigContext';
import { getWorkspace, analyzeCensus, CensusAnalysisResult, CensusSegmentMetrics } from '../services/api';
import { useChartTheme } from '../hooks/useChartTheme';

const formatCurrency = (value: number): string => {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
};

const formatPercent = (value: number | null): string =>
  value === null ? '—' : `${(value * 100).toFixed(1)}%`;

const DIMENSION_LABELS: Record<string, string> = {
  department: 'Department',
  job_level: 'Job Level',
  age_band: 'Age Band',
  tenure_band: 'Tenure Band',
  hce_status: 'HCE Status',
};

const KPI_ICON_STYLES: Record<string, string> = {
  blue: 'bg-info-surface text-info-ink',
  green: 'bg-success-surface text-success-ink',
  orange: 'bg-warning-surface text-warning-ink',
  gray: 'bg-surface-subtle text-ink-muted',
};

const KPICard = ({
  title, value, subtext, icon: Icon, color, loading,
}: {
  title: string;
  value: string;
  subtext?: string;
  icon: React.ComponentType<{ size?: number }>;
  color: string;
  loading?: boolean;
}) => (
  <div className="bg-surface-raised p-5 rounded-xl shadow-sm border border-border flex items-start justify-between">
    <div>
      <p className="text-sm font-medium text-ink-muted">{title}</p>
      {loading ? (
        <div className="h-8 w-20 bg-surface-disabled rounded animate-pulse mt-1" />
      ) : (
        <>
          <h3 className="text-2xl font-bold text-ink mt-1">{value}</h3>
          {subtext && <p className="text-xs font-medium text-ink-muted mt-1">{subtext}</p>}
        </>
      )}
    </div>
    <div className={`p-2 rounded-lg ${KPI_ICON_STYLES[color] ?? KPI_ICON_STYLES.gray}`}>
      <Icon size={20} />
    </div>
  </div>
);

const EmptyState = ({ message }: { message: string }) => (
  <div className="flex flex-col items-center justify-center h-64 text-ink-subtle">
    <Database size={40} className="mb-3" />
    <p className="text-sm text-ink-muted text-center max-w-md">{message}</p>
  </div>
);

const ErrorState = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center h-64 text-danger-ink">
    <AlertTriangle size={40} className="mb-3" />
    <p className="text-sm text-ink-muted mb-4 text-center max-w-md">{message}</p>
    <button
      onClick={onRetry}
      className="flex items-center px-4 py-2 bg-danger-solid text-ink-inverse rounded-lg text-sm font-medium hover:bg-danger-solid-hover transition-colors"
    >
      <RefreshCw size={16} className="mr-2" />
      Retry
    </button>
  </div>
);

const SegmentTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as CensusSegmentMetrics;
  return (
    <div className="bg-surface-raised border border-border rounded-lg shadow-lg px-4 py-3 min-w-[200px]">
      <p className="font-semibold text-ink mb-2 text-sm">{label}</p>
      <div className="space-y-1 text-sm text-ink-muted">
        <p>{row.employee_count.toLocaleString()} employees</p>
        <p>
          Participation: <span className="font-semibold text-fidelity-green">{formatPercent(row.participation_rate)}</span>
        </p>
        <p>
          Avg deferral: <span className="font-semibold text-ink">{formatPercent(row.average_deferral_rate)}</span>
        </p>
        <p>
          Employer cost: <span className="font-semibold text-ink">{formatCurrency(row.total_employer_cost)}</span>
        </p>
      </div>
    </div>
  );
};

function SegmentChart({
  title, metric, formatValue, data,
}: {
  title: string;
  metric: keyof CensusSegmentMetrics;
  formatValue: (v: number) => string;
  data: CensusSegmentMetrics[];
}) {
  const chartTheme = useChartTheme();
  const chartData = data.map(row => ({
    ...row,
    name: row.value,
    metricValue: (row[metric] as number | null) ?? 0,
  }));

  return (
    <div className="bg-surface-raised p-5 rounded-xl shadow-sm border border-border">
      <h3 className="text-sm font-semibold text-ink mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid.line} vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: chartTheme.axis.tick }} stroke={chartTheme.axis.line} interval={0} angle={-20} textAnchor="end" height={50} />
          <YAxis tick={{ fontSize: 11, fill: chartTheme.axis.tick }} stroke={chartTheme.axis.line} tickFormatter={formatValue} width={56} />
          <Tooltip cursor={chartTheme.tooltip.cursorStyle} content={<SegmentTooltip />} />
          <Bar dataKey="metricValue" radius={[4, 4, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={chartTheme.colorAt(i)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function CensusAnalysis() {
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  const [censusPath, setCensusPath] = useState('');
  const [asOfDate, setAsOfDate] = useState('');
  const [result, setResult] = useState<CensusAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dimension, setDimension] = useState<string>('');

  useEffect(() => {
    if (!activeWorkspace?.id) {
      setCensusPath('');
      return;
    }
    getWorkspace(activeWorkspace.id)
      .then(ws => setCensusPath(extractCensusPath(ws.base_config) ?? ''))
      .catch(() => setCensusPath(extractCensusPath(activeWorkspace.base_config) ?? ''));
  }, [activeWorkspace?.id]);

  const runAnalysis = async () => {
    if (!activeWorkspace?.id || !censusPath) {
      setError('This workspace has no census file uploaded yet.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeCensus(activeWorkspace.id, {
        file_path: censusPath,
        as_of_date: asOfDate || undefined,
      });
      setResult(data);
      setDimension(data.available_segment_dimensions[0] ?? '');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to analyze census.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (censusPath) void runAnalysis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [censusPath]);

  const segmentsForDimension = useMemo(
    () => (result?.segments ?? []).filter(s => s.dimension === dimension),
    [result, dimension]
  );

  const errorIssues = result?.data_quality_issues.filter(i => i.severity === 'error') ?? [];
  const warningIssues = result?.data_quality_issues.filter(i => i.severity === 'warning') ?? [];

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">Census Analysis</h1>
          <p className="text-ink-muted mt-1">
            Participation, savings rate, and cost metrics computed directly from the raw census — no simulation required.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label htmlFor="census-as-of-date" className="block text-xs font-medium text-ink-muted mb-1">As-of date</label>
            <input
              id="census-as-of-date"
              type="date"
              value={asOfDate}
              onChange={e => setAsOfDate(e.target.value)}
              className="bg-surface-raised border border-border-strong rounded-lg px-3 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
            />
          </div>
          <button
            onClick={runAnalysis}
            disabled={!censusPath || loading}
            className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark disabled:opacity-50 transition-colors"
          >
            {loading ? <Loader2 size={16} className="mr-2 animate-spin" /> : <RefreshCw size={16} className="mr-2" />}
            Analyze
          </button>
        </div>
      </div>

      {!censusPath && !loading && (
        <EmptyState message="This workspace has no census file uploaded yet. Upload one from Import Data to see census analysis." />
      )}

      {error && censusPath && <ErrorState message={error} onRetry={runAnalysis} />}

      {result && !error && (
        <>
          {result.message && (
            <div className="flex items-start gap-2 bg-info-surface text-info-ink text-sm rounded-lg px-4 py-3 border border-border">
              <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
              <span>{result.message}</span>
            </div>
          )}

          <p className="text-xs text-ink-subtle">
            As of {result.as_of_date} ({result.as_of_date_source}) · {result.active_employees.toLocaleString()} active of {result.total_employees.toLocaleString()} census rows
            {result.hce_compensation_threshold != null && ` · HCE threshold ${formatCurrency(result.hce_compensation_threshold)}`}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              title="Participation Rate"
              value={formatPercent(result.overall.participation_rate)}
              subtext={`${result.overall.enrolled_count.toLocaleString()} of ${result.overall.eligible_count.toLocaleString()} eligible`}
              icon={Users}
              color="blue"
              loading={loading}
            />
            <KPICard
              title="Avg Deferral Rate"
              value={formatPercent(result.overall.average_deferral_rate)}
              subtext={`Median ${formatPercent(result.overall.median_deferral_rate)}`}
              icon={TrendingUp}
              color="green"
              loading={loading}
            />
            <KPICard
              title="Employer Cost (as loaded)"
              value={formatCurrency(result.overall.total_employer_cost)}
              subtext={`Match ${formatCurrency(result.overall.total_employer_match)} · Core ${formatCurrency(result.overall.total_employer_core)}`}
              icon={DollarSign}
              color="orange"
              loading={loading}
            />
            <KPICard
              title="Zero-Deferral Employees"
              value={result.overall.zero_deferral_count.toLocaleString()}
              subtext={`${result.overall.hce_count.toLocaleString()} HCE among eligible`}
              icon={AlertTriangle}
              color="gray"
              loading={loading}
            />
          </div>

          {(errorIssues.length > 0 || warningIssues.length > 0) && (
            <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-5">
              <h3 className="text-sm font-semibold text-ink mb-3">Data Quality Flags</h3>
              <div className="space-y-2">
                {result.data_quality_issues.map((issue, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2 ${
                      issue.severity === 'error' ? 'bg-danger-surface text-danger-ink' : 'bg-warning-surface text-warning-ink'
                    }`}
                  >
                    <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                    <span>{issue.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {result.data_quality_issues.length === 0 && (
            <div className="flex items-center gap-2 text-sm text-success-ink bg-success-surface rounded-lg px-4 py-3 border border-border">
              No data quality issues detected in the census.
            </div>
          )}

          {result.available_segment_dimensions.length > 0 && (
            <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-ink">Segment Breakdown</h3>
                <div className="relative">
                  <select
                    value={dimension}
                    onChange={e => setDimension(e.target.value)}
                    className="appearance-none bg-surface-raised border border-border-strong rounded-lg pl-3 pr-9 py-2 text-sm focus:ring-fidelity-green focus:border-fidelity-green shadow-sm"
                  >
                    {result.available_segment_dimensions.map(d => (
                      <option key={d} value={d}>{DIMENSION_LABELS[d] ?? d}</option>
                    ))}
                  </select>
                  <ChevronDown size={16} className="absolute right-3 top-2.5 text-ink-subtle pointer-events-none" />
                </div>
              </div>

              {segmentsForDimension.length === 0 ? (
                <EmptyState message="No data available for this segment." />
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <SegmentChart
                    title="Participation Rate by Segment"
                    metric="participation_rate"
                    formatValue={v => `${(v * 100).toFixed(0)}%`}
                    data={segmentsForDimension}
                  />
                  <SegmentChart
                    title="Avg Deferral Rate by Segment"
                    metric="average_deferral_rate"
                    formatValue={v => `${(v * 100).toFixed(0)}%`}
                    data={segmentsForDimension}
                  />
                  <SegmentChart
                    title="Employer Cost by Segment"
                    metric="total_employer_cost"
                    formatValue={formatCurrency}
                    data={segmentsForDimension}
                  />
                  <SegmentChart
                    title="Headcount by Segment"
                    metric="employee_count"
                    formatValue={v => v.toLocaleString()}
                    data={segmentsForDimension}
                  />
                </div>
              )}

              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-ink-muted border-b border-border">
                      <th className="py-2 pr-4 font-medium">{DIMENSION_LABELS[dimension] ?? dimension}</th>
                      <th className="py-2 pr-4 font-medium">Employees</th>
                      <th className="py-2 pr-4 font-medium">Eligible</th>
                      <th className="py-2 pr-4 font-medium">Enrolled</th>
                      <th className="py-2 pr-4 font-medium">Participation</th>
                      <th className="py-2 pr-4 font-medium">Avg Deferral</th>
                      <th className="py-2 pr-4 font-medium">Employer Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {segmentsForDimension.map(row => (
                      <tr key={row.value} className="border-b border-border last:border-0">
                        <td className="py-2 pr-4 text-ink">{row.value}</td>
                        <td className="py-2 pr-4 text-ink-muted">{row.employee_count.toLocaleString()}</td>
                        <td className="py-2 pr-4 text-ink-muted">{row.eligible_count.toLocaleString()}</td>
                        <td className="py-2 pr-4 text-ink-muted">{row.enrolled_count.toLocaleString()}</td>
                        <td className="py-2 pr-4 text-ink-muted">{formatPercent(row.participation_rate)}</td>
                        <td className="py-2 pr-4 text-ink-muted">{formatPercent(row.average_deferral_rate)}</td>
                        <td className="py-2 pr-4 text-ink-muted">{formatCurrency(row.total_employer_cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
