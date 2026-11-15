import { useState } from 'react';
import { FolderOpen, Loader2, Square } from 'lucide-react';
import { EnsembleJob, cancelEnsembleJob } from '../../services/api';
import { TONE_CLASSES, Tone, errorMessage, isActive, progressLabel, statusCopy, yearRange } from './ensembleJobHelpers';

const DETAIL_CLASSES: Record<Tone, string> = {
  success: 'text-ink-muted',
  neutral: 'text-ink-muted',
  info: 'text-info-ink',
  warning: 'text-warning-ink',
  danger: 'text-danger-ink',
};

interface EnsembleJobListProps {
  readonly workspaceId: string;
  readonly jobs: EnsembleJob[];
  readonly openedJobId: string | null;
  /** Per-job notices from this session, e.g. a job that started differently from its estimate. */
  readonly notices: Readonly<Record<string, string>>;
  readonly onOpen: (job: EnsembleJob) => void;
  readonly onChanged: (job: EnsembleJob) => void;
}

/** This workspace's ensembles, newest first: progress while running, Open once there are results. */
export function EnsembleJobList({ workspaceId, jobs, openedJobId, notices, onOpen, onChanged }: EnsembleJobListProps) {
  if (jobs.length === 0) {
    return <p className="text-sm text-ink-muted">No ensembles yet. Start one above; it will appear here.</p>;
  }
  return (
    <ul className="divide-y divide-border rounded-md border border-border">
      {jobs.map((job) => (
        <EnsembleJobRow
          key={job.job_id}
          workspaceId={workspaceId}
          job={job}
          opened={job.job_id === openedJobId}
          notice={notices[job.job_id] ?? null}
          onOpen={onOpen}
          onChanged={onChanged}
        />
      ))}
    </ul>
  );
}

interface EnsembleJobRowProps {
  readonly workspaceId: string;
  readonly job: EnsembleJob;
  readonly opened: boolean;
  readonly notice: string | null;
  readonly onOpen: (job: EnsembleJob) => void;
  readonly onChanged: (job: EnsembleJob) => void;
}

function EnsembleJobRow({ workspaceId, job, opened, notice, onOpen, onChanged }: EnsembleJobRowProps) {
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = statusCopy(job);
  const active = isActive(job.status);
  const { seeds_total: total, seeds_completed: done, seeds_failed: failed } = job.progress;
  const percent = total > 0 ? Math.round(((done + failed) / total) * 100) : 0;
  const years = yearRange(job.start_year, job.end_year);

  async function cancel() {
    if (!window.confirm('Cancel this ensemble? Seeds already run will be discarded.')) return;
    setCancelling(true);
    setError(null);
    try {
      onChanged(await cancelEnsembleJob(workspaceId, job.job_id));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <li className={`space-y-2 p-3 text-sm ${opened ? 'bg-surface-subtle' : ''}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="font-medium text-ink">{job.scenario_name}</span>
          <span className="ml-2 text-xs text-ink-muted">
            {job.seed_count} seeds · {years} · started {new Date(job.created_at).toLocaleString()}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold ${TONE_CLASSES[status.tone]}`}>
            {status.label}
          </span>
          {active && (
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={cancelling}
              className="inline-flex items-center gap-1 rounded-md border border-border-strong bg-surface-raised px-2.5 py-1 text-xs text-ink hover:bg-surface-subtle disabled:opacity-50"
            >
              <Square size={12} /> {cancelling ? 'Cancelling…' : 'Cancel'}
            </button>
          )}
          {job.output && (
            <button
              type="button"
              onClick={() => onOpen(job)}
              disabled={opened}
              className="inline-flex items-center gap-1 rounded-md bg-brand-green px-2.5 py-1 text-xs font-medium text-ink-inverse disabled:opacity-50"
            >
              <FolderOpen size={12} /> {opened ? 'Opened' : 'Open results'}
            </button>
          )}
        </div>
      </div>
      {active && (
        <div className="space-y-1 text-info-ink">
          <div className="flex items-center gap-2 text-xs">
            <Loader2 size={12} className="animate-spin" />
            {progressLabel(job)}
          </div>
          {job.status === 'running' && (
            <div className="h-1.5 overflow-hidden rounded bg-surface-subtle">
              <div className="h-full bg-brand-green transition-all" style={{ width: `${percent}%` }} />
            </div>
          )}
        </div>
      )}
      {!active && status.detail && <p className={`text-xs ${DETAIL_CLASSES[status.tone]}`}>{status.detail}</p>}
      {notice && <p className="text-xs text-warning-ink">{notice}</p>}
      {error && <p className="text-xs text-danger-ink">{error}</p>}
    </li>
  );
}
