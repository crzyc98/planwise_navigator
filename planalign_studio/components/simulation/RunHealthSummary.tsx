import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  FileQuestion,
  Loader2,
  ShieldX,
} from 'lucide-react';

import { getRunHealth, RunHealthFinding, RunHealthReport } from '../../services/api';

const SEVERITY_STYLES: Record<string, string> = {
  error: 'bg-danger-surface text-danger-ink',
  warning: 'bg-warning-surface text-warning-ink',
};

function severityPill(severity: string): React.ReactNode {
  const style = SEVERITY_STYLES[severity.toLowerCase()] ?? 'bg-surface-subtle text-ink-muted';
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium capitalize ${style}`}>
      {severity}
    </span>
  );
}

function CountBadge({ label, value, style }: Readonly<{
  label: string;
  value: number;
  style: string;
}>) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {value}&nbsp;{label}
    </span>
  );
}

function Counts({ report }: Readonly<{ report: RunHealthReport }>): React.ReactNode {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <CountBadge
        label="passed"
        value={report.counts.passed}
        style="border-success-border bg-success-surface text-success-ink"
      />
      <CountBadge
        label="warnings"
        value={report.counts.warning}
        style="border-warning-border bg-warning-surface text-warning-ink"
      />
      <CountBadge
        label="failed"
        value={report.counts.failed}
        style="border-danger-border bg-danger-surface text-danger-ink"
      />
    </div>
  );
}

function FindingsTable({ findings }: Readonly<{ findings: RunHealthFinding[] }>): React.ReactNode {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full divide-y divide-border text-sm">
        <thead className="bg-surface-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th className="px-3 py-2">Rule</th>
            <th className="px-3 py-2">Disposition</th>
            <th className="px-3 py-2">Year / Stage</th>
            <th className="px-3 py-2 text-right">Records</th>
            <th className="px-3 py-2">Summary</th>
          </tr>
        </thead>
        <tbody>
          {findings.map(finding => (
            <tr
              key={`${finding.simulation_year}-${finding.check_name}-${finding.severity}`}
              className="bg-surface-raised"
            >
              <td className="px-3 py-2 font-medium text-ink">{finding.check_name}</td>
              <td className="px-3 py-2">{severityPill(finding.severity)}</td>
              <td className="px-3 py-2 text-ink-muted">
                {finding.simulation_year} · {finding.stage}
              </td>
              <td className="px-3 py-2 text-right text-ink-muted">
                {finding.affected_record_count ?? '—'}
              </td>
              <td className="px-3 py-2 text-ink">{finding.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RunHealthSummary({
  scenarioId,
  runId,
  compact = false,
}: Readonly<{
  scenarioId: string;
  runId?: string;
  compact?: boolean;
}>) {
  const [report, setReport] = useState<RunHealthReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      try {
        setLoading(true);
        setFailed(false);
        const response = await getRunHealth(scenarioId, runId);
        if (!cancelled) setReport(response);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [scenarioId, runId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-surface-subtle px-3 py-2 text-sm text-ink-muted">
        <Loader2 size={15} className="animate-spin" />
        Loading run health...
      </div>
    );
  }

  if (failed || !report) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-surface-subtle px-3 py-2 text-sm text-ink-muted">
        <AlertCircle size={15} />
        Run health is not available right now.
      </div>
    );
  }

  if (compact) {
    const statusText = {
      clean: `All ${report.counts.total} validation checks passed`,
      warnings: `${report.counts.warning} validation warning${report.counts.warning === 1 ? '' : 's'}`,
      failed: `${report.counts.failed} validation failure${report.counts.failed === 1 ? '' : 's'}`,
      missing_provenance: 'No validation artifact archived for this run',
      unavailable: 'Validation evidence unavailable for this run',
    }[report.status];
    const StatusIcon = {
      clean: CheckCircle,
      warnings: AlertTriangle,
      failed: ShieldX,
      missing_provenance: FileQuestion,
      unavailable: AlertCircle,
    }[report.status];
    const iconStyle = {
      clean: 'text-success-ink',
      warnings: 'text-warning-ink',
      failed: 'text-danger-ink',
      missing_provenance: 'text-ink-muted',
      unavailable: 'text-warning-ink',
    }[report.status];
    return (
      <Link
        to={`/simulate/${scenarioId}`}
        data-run-health-status={report.status}
        className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
          report.status === 'failed'
            ? 'border-danger-border bg-danger-surface text-danger-ink hover:bg-surface-subtle'
            : report.status === 'warnings' || report.status === 'unavailable'
              ? 'border-warning-border bg-warning-surface text-warning-ink hover:bg-surface-subtle'
              : 'border-border bg-surface-subtle text-ink-muted hover:bg-surface-raised'
        }`}
      >
        <StatusIcon size={16} className={iconStyle} />
        <span className="font-medium">Run health:</span>
        <span>{statusText}</span>
        {(report.status === 'warnings' || report.status === 'failed') && <Counts report={report} />}
        <ArrowRight size={14} className="ml-auto" />
      </Link>
    );
  }

  return (
    <div
      data-run-health-status={report.status}
      className={`rounded-lg border p-4 ${
        report.status === 'clean'
          ? 'border-success-border bg-success-surface'
          : report.status === 'failed'
            ? 'border-danger-border bg-danger-surface'
            : 'border-warning-border bg-warning-surface'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h4 className="flex items-center gap-2 text-sm font-semibold text-ink">
          {report.status === 'clean' && <CheckCircle size={16} className="text-success-ink" />}
          {report.status === 'warnings' && <AlertTriangle size={16} className="text-warning-ink" />}
          {report.status === 'failed' && <ShieldX size={16} className="text-danger-ink" />}
          {report.status === 'missing_provenance' && <FileQuestion size={16} className="text-ink-muted" />}
          {report.status === 'unavailable' && <AlertCircle size={16} className="text-warning-ink" />}
          Validation Health
        </h4>
        {runId && (
          <Link
            to={`/simulate/${scenarioId}/runs/${runId}/provenance`}
            className="flex items-center gap-1 text-sm font-medium text-fidelity-green hover:underline"
          >
            View full audit report
            <ArrowRight size={14} />
          </Link>
        )}
      </div>

      {report.status === 'clean' && (
        <p className="mt-2 text-sm text-success-ink">
          All {report.counts.total} validation check{report.counts.total === 1 ? '' : 's'} passed for this run.
        </p>
      )}
      {report.status === 'missing_provenance' && (
        <p className="mt-2 text-sm text-ink-muted">
          No validation artifact was archived for this run, so its checks could not be reviewed. This is
          different from a clean run.
        </p>
      )}
      {report.status === 'unavailable' && (
        <p className="mt-2 text-sm text-warning-ink">
          Validation evidence was not captured for this run. Treat its results as unverified rather than clean.
        </p>
      )}

      {(report.status === 'warnings' || report.status === 'failed') && (
        <>
          <div className="mt-3"><Counts report={report} /></div>
          <div className="mt-3">
            <FindingsTable findings={report.findings} />
          </div>
        </>
      )}
    </div>
  );
}
