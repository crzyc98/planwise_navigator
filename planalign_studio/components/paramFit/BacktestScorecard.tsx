import { ScorecardView, formatNumber, formatPercent, verdictTone, Tone } from './paramFitHelpers';
import { Badge } from './paramFitUi';

const STATUS_TONES: Record<string, Tone> = {
  pass: 'success',
  warn: 'warning',
  fail: 'danger',
};

/** Predicted vs actual for every held-out metric and period, with the verdict. */
export function BacktestScorecard({ scorecard, current }: { scorecard: ScorecardView; current: boolean }) {
  const tone = verdictTone(scorecard.verdict);
  const hasSpread = scorecard.comparisons.some((row) => row.spread !== null);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-ink">Backtest</h3>
        <Badge tone={tone}>{scorecard.verdict ?? 'no verdict'}</Badge>
        <span className="text-sm text-ink-muted">{scorecard.verdictSummary}</span>
      </div>
      <p className="text-sm text-ink-muted">
        Fitted on {scorecard.fitYears.join(', ')}, held out {scorecard.holdoutYears.join(', ')}, seeds {scorecard.seeds.join(', ')}
        {scorecard.seeds.length === 1 ? ' (one seed — no run-to-run spread computed)' : ''}.
        {scorecard.overriddenThresholds.length > 0 && (
          <span className="text-warning-ink"> Thresholds changed from defaults: {scorecard.overriddenThresholds.join(', ')}.</span>
        )}
      </p>
      {!current && (
        <p className="rounded-md border border-warning-border bg-warning-surface p-2 text-sm text-warning-ink">
          This scorecard no longer matches the pack's current files, so it does not count as a backtest.
        </p>
      )}
      <div className="max-h-96 overflow-auto rounded-md border border-border">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-surface-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th className="px-3 py-2">Metric</th>
              <th className="px-3 py-2">Period</th>
              <th className="px-3 py-2 text-right">Predicted</th>
              <th className="px-3 py-2 text-right">Actual</th>
              <th className="px-3 py-2 text-right">% error</th>
              {hasSpread && <th className="px-3 py-2 text-right">Seed range</th>}
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {scorecard.comparisons.map((row) => (
              <tr key={`${row.metric}-${row.period}`} title={row.note ?? undefined}>
                <td className="px-3 py-1.5 font-mono text-xs text-ink">{row.metric}</td>
                <td className="px-3 py-1.5 text-ink-muted">{row.period}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink">{formatNumber(row.predicted)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink">{formatNumber(row.actual)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-ink">{formatPercent(row.percentError, true)}</td>
                {hasSpread && (
                  <td
                    className={`px-3 py-1.5 text-right tabular-nums ${row.spread && !row.spread.actualWithin ? 'text-warning-ink' : 'text-ink-muted'}`}
                    title={row.spread && !row.spread.actualWithin ? 'Actual falls outside the range the seeds produced' : undefined}
                  >
                    {row.spread ? `${formatNumber(row.spread.minimum)} – ${formatNumber(row.spread.maximum)}` : '—'}
                    {row.spread && !row.spread.actualWithin ? ' ⚠' : ''}
                  </td>
                )}
                <td className="px-3 py-1.5">
                  <Badge tone={STATUS_TONES[row.status] ?? 'neutral'}>{row.status.replace('_', ' ')}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
