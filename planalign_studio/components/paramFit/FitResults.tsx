import { useMemo, useState } from 'react';
import { AlertTriangle, FileText, Loader2 } from 'lucide-react';
import { getParamFitReport, ParamFitJob, ParamFitResult } from '../../services/api';
import { BacktestScorecard } from './BacktestScorecard';
import {
  diagnosticRows,
  formatNumber,
  formatPercent,
  scorecardView,
  shortHash,
  summaryView,
} from './paramFitHelpers';
import { errorText, Stat } from './paramFitUi';

interface FitResultsProps {
  readonly workspaceId: string;
  readonly job: ParamFitJob;
  readonly result: ParamFitResult;
  readonly onApply: () => void;
}

/** Everything a completed job produced: summary, diagnostics, provenance, scorecard. */
export function FitResults({ workspaceId, job, result, onApply }: FitResultsProps) {
  const summary = summaryView(result.summary);
  const scorecard = scorecardView(result.scorecard);
  const blockingStale = result.stale.filter((item) => item.reason !== 'base_scenario_changed');

  return (
    <div className="space-y-6">
      {result.stale.length > 0 && (
        <div className="space-y-1 rounded-lg border border-warning-border bg-warning-surface p-4 text-sm text-warning-ink">
          {result.stale.map((item) => (
            <p key={item.reason} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {item.message}
            </p>
          ))}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Snapshot years" value={summary.snapshotYears.join(', ') || '—'} />
        <Stat label="Employees linked" value={formatNumber(summary.linkedEmployees, 0)} />
        <Stat label="Parameters fitted" value={formatNumber(summary.fittedCount, 0)} />
        <Stat
          label="Thin / prior-backed"
          value={formatNumber(summary.thinCount, 0)}
          tone={summary.thinCount ? 'warning' : undefined}
        />
        <Stat label="Could not be fitted" value={result.unfittable.length} tone={result.unfittable.length ? 'warning' : undefined} />
      </div>
      {summary.promotionBasisLabel && (
        <p className="text-sm text-ink-muted">
          Promotion rate: <span className="font-medium text-ink">{summary.promotionBasisLabel}</span>
        </p>
      )}

      <Warnings result={result} />
      {scorecard && <BacktestScorecard scorecard={scorecard} current={result.scorecard_current} />}
      <DiagnosticsTable groups={result.diagnostics} />
      <Provenance result={result} />
      <ReportLinks workspaceId={workspaceId} jobId={job.job_id} hasFit={result.has_fit_report} hasScorecard={Boolean(scorecard)} />

      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
        <button
          type="button"
          onClick={onApply}
          disabled={blockingStale.length > 0}
          className="rounded-lg bg-fidelity-green px-4 py-2 font-medium text-ink-inverse transition-colors hover:bg-fidelity-dark disabled:cursor-not-allowed disabled:bg-surface-disabled"
        >
          Apply to a new scenario…
        </button>
        <span className="text-sm text-ink-muted">
          {blockingStale.length > 0
            ? 'This pack is stale and cannot be applied. Re-run the fit.'
            : 'Creates a new scenario after you review the changes. The source scenario is never modified.'}
        </span>
      </div>
    </div>
  );
}

function Warnings({ result }: { result: ParamFitResult }) {
  if (!result.warnings.length && !result.unfittable.length) return null;
  return (
    <div className="space-y-3 rounded-lg border border-warning-border bg-warning-surface p-4 text-sm text-warning-ink">
      {result.warnings.map((warning) => (
        <p key={warning}>⚠ {warning}</p>
      ))}
      {result.unfittable.length > 0 && (
        <div>
          <p className="font-medium">Kept at their current defaults (the data could not speak to them):</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {result.unfittable.map((item, index) => (
              <li key={`${String(item.name)}-${index}`}>
                <span className="font-medium">{String(item.name)}</span>
                {item.reason ? ` — ${String(item.reason)}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DiagnosticsTable({ groups }: { groups: ParamFitResult['diagnostics'] }) {
  const [thinOnly, setThinOnly] = useState(false);
  const rows = useMemo(() => diagnosticRows(groups), [groups]);
  const visible = thinOnly ? rows.filter((row) => row.thin) : rows;
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">Fitted values</h3>
        <label className="flex items-center gap-2 text-sm text-ink-muted">
          <input type="checkbox" checked={thinOnly} onChange={(event) => setThinOnly(event.target.checked)} />
          Thin cells only
        </label>
      </div>
      <div className="max-h-96 overflow-auto rounded-md border border-border">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-surface-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th className="px-3 py-2">Group</th>
              <th className="px-3 py-2">Parameter</th>
              <th className="px-3 py-2 text-right">Fitted</th>
              <th className="px-3 py-2 text-right">Prior</th>
              <th className="px-3 py-2 text-right">Change</th>
              <th className="px-3 py-2 text-right">Exposure</th>
              <th className="px-3 py-2 text-right">Events</th>
              <th className="px-3 py-2 text-right">Credibility</th>
              <th className="px-3 py-2">Basis</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {visible.map((row) => (
              <tr key={`${row.group}-${row.name}`} className={row.thin ? 'bg-warning-surface' : ''} title={row.note || undefined}>
                <td className="px-3 py-1.5 text-ink-muted">{row.group}</td>
                <td className="px-3 py-1.5 font-mono text-xs text-ink">{row.name}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink">{formatNumber(row.value)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink-muted">{formatNumber(row.prior)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink-muted">{formatPercent(row.movedPct, true)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink-muted">{formatNumber(row.exposure, 1)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink-muted">{formatNumber(row.events, 1)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink-muted">{formatNumber(row.credibility, 2)}</td>
                <td className={`px-3 py-1.5 ${row.thin ? 'font-medium text-warning-ink' : 'text-ink-muted'}`}>{row.basis}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Provenance({ result }: { result: ParamFitResult }) {
  const provenance = result.provenance as Record<string, unknown>;
  const text = (key: string) => (typeof provenance[key] === 'string' ? (provenance[key] as string) : '—');
  const verified = provenance.fingerprint_verified === true;
  return (
    <div className="rounded-lg border border-border p-4 text-sm">
      <h3 className="mb-2 font-semibold text-ink">Provenance</h3>
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-[max-content_1fr]">
        <dt className="text-ink-muted">Pack</dt>
        <dd className="text-ink">{text('pack_id')}</dd>
        <dt className="text-ink-muted">Fingerprint</dt>
        <dd className="font-mono text-xs text-ink" title={text('fingerprint')}>
          {shortHash(text('fingerprint'), 16)} {verified ? '(verified)' : <span className="text-danger-ink">(files edited after fitting)</span>}
        </dd>
        <dt className="text-ink-muted">Source digest</dt>
        <dd className="font-mono text-xs text-ink" title={text('source_digest')}>{shortHash(text('source_digest'), 16)}</dd>
        <dt className="text-ink-muted">Fitted</dt>
        <dd className="text-ink">{text('fit_date')}</dd>
        <dt className="text-ink-muted">Engine version</dt>
        <dd className="text-ink">{text('planalign_version')}</dd>
      </dl>
    </div>
  );
}

function ReportLinks(props: { workspaceId: string; jobId: string; hasFit: boolean; hasScorecard: boolean }) {
  const [report, setReport] = useState<{ kind: string; text: string } | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function open(kind: 'fit' | 'scorecard') {
    if (report?.kind === kind) {
      setReport(null);
      return;
    }
    setLoading(kind);
    setError(null);
    try {
      setReport({ kind, text: await getParamFitReport(props.workspaceId, props.jobId, kind) });
    } catch (loadError) {
      setError(errorText(loadError));
    } finally {
      setLoading(null);
    }
  }

  const button = (kind: 'fit' | 'scorecard', label: string) => (
    <button
      type="button"
      onClick={() => void open(kind)}
      className="inline-flex items-center gap-1 rounded-lg border border-border-strong px-3 py-1.5 text-sm text-ink hover:bg-surface-subtle"
    >
      {loading === kind ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
      {report?.kind === kind ? `Hide ${label}` : label}
    </button>
  );

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {props.hasFit && button('fit', 'Full fit report')}
        {props.hasScorecard && button('scorecard', 'Full scorecard')}
      </div>
      {error && <p className="text-sm text-danger-ink">{error}</p>}
      {report && (
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-surface-subtle p-3 text-xs text-ink">
          {report.text}
        </pre>
      )}
    </div>
  );
}
