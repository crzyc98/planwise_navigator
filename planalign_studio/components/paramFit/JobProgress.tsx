import { useState } from 'react';
import { AlertTriangle, Loader2, Square } from 'lucide-react';
import { cancelParamFit, ParamFitJob } from '../../services/api';
import { isTerminal, progressLabel } from './paramFitHelpers';
import { errorText } from './paramFitUi';

interface JobProgressProps {
  readonly workspaceId: string;
  readonly job: ParamFitJob;
  readonly onChanged: (job: ParamFitJob) => void;
}

/** Live status of one job: stage / seed progress, cancel, and failure detail. */
export function JobProgress({ workspaceId, job, onChanged }: JobProgressProps) {
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const running = !isTerminal(job.status);
  const { progress } = job;
  const percent = progress.total && progress.index ? Math.round(((progress.index - 1) / progress.total) * 100) : null;

  async function cancel() {
    if (!window.confirm('Cancel this job? Its partial results will be discarded.')) return;
    setCancelling(true);
    setError(null);
    try {
      onChanged(await cancelParamFit(workspaceId, job.job_id));
    } catch (cancelError) {
      setError(errorText(cancelError));
    } finally {
      setCancelling(false);
    }
  }

  if (job.status === 'failed' && job.error) {
    const failedAt =
      job.error.failed_seed != null ? ` (seed ${job.error.failed_seed}, year ${job.error.failed_year ?? '?'})` : '';
    return (
      <div className="flex items-start gap-3 rounded-lg border border-danger-border bg-danger-surface p-4 text-sm text-danger-ink">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-medium">
            {job.mode === 'backtest' ? 'Backtest' : 'Fit'} failed{failedAt}
          </p>
          <p className="mt-1 whitespace-pre-wrap">{job.error.message}</p>
        </div>
      </div>
    );
  }

  if (job.status === 'cancelled') {
    return <div className="rounded-lg border border-border bg-surface-subtle p-4 text-sm text-ink-muted">This job was cancelled; nothing was kept.</div>;
  }

  if (!running) return null;

  return (
    <div className="space-y-3 rounded-lg border border-info-border bg-info-surface p-4 text-sm text-info-ink">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <Loader2 size={16} className="animate-spin" />
          {progressLabel(progress, job.status)}
        </div>
        <button
          type="button"
          onClick={() => void cancel()}
          disabled={cancelling}
          className="inline-flex items-center gap-1 rounded-lg border border-border-strong bg-surface-raised px-3 py-1.5 text-ink transition-colors hover:bg-surface-subtle disabled:cursor-not-allowed"
        >
          <Square size={14} /> {cancelling ? 'Cancelling…' : 'Cancel'}
        </button>
      </div>
      {percent !== null && (
        <div className="h-2 overflow-hidden rounded bg-surface-raised">
          <div className="h-full bg-fidelity-green transition-all" style={{ width: `${percent}%` }} />
        </div>
      )}
      <p className="text-xs">
        Studio stays usable while this runs{job.mode === 'backtest' ? ' — a backtest simulates every held-out year per seed and can take several minutes' : ''}.
      </p>
      {error && <p className="text-danger-ink">{error}</p>}
    </div>
  );
}
