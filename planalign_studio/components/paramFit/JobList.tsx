import { ParamFitJobSummary } from '../../services/api';
import { isTerminal, progressLabel, verdictTone } from './paramFitHelpers';
import { Badge } from './paramFitUi';

const STATUS_TONES = {
  completed: 'success',
  failed: 'danger',
  cancelled: 'neutral',
  running: 'neutral',
  queued: 'neutral',
} as const;

interface JobListProps {
  readonly jobs: ParamFitJobSummary[];
  readonly selectedId: string | null;
  readonly onSelect: (jobId: string) => void;
}

/** This workspace's fit & backtest jobs; persists across Studio restarts. */
export function JobList({ jobs, selectedId, onSelect }: JobListProps) {
  if (jobs.length === 0) {
    return <p className="text-sm text-ink-muted">No fits yet. Run one above; it will appear here.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="min-w-full text-sm">
        <thead className="bg-surface-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th className="px-3 py-2">Started</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Years</th>
            <th className="px-3 py-2">Base scenario</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Backtest</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {jobs.map((job) => (
            <tr
              key={job.job_id}
              onClick={() => onSelect(job.job_id)}
              className={`cursor-pointer hover:bg-surface-subtle ${job.job_id === selectedId ? 'bg-surface-subtle' : ''}`}
            >
              <td className="px-3 py-2 text-ink">{new Date(job.created_at).toLocaleString()}</td>
              <td className="px-3 py-2 text-ink">{job.mode === 'backtest' ? 'Fit + backtest' : 'Fit'}</td>
              <td className="px-3 py-2 text-ink-muted">{job.snapshot_years.join(', ')}</td>
              <td className="px-3 py-2 text-ink-muted">{job.base_scenario_name}</td>
              <td className="px-3 py-2">
                {isTerminal(job.status) ? (
                  <Badge tone={STATUS_TONES[job.status]}>{job.status}</Badge>
                ) : (
                  <span className="text-info-ink">{progressLabel(job.progress, job.status)}</span>
                )}
              </td>
              <td className="px-3 py-2">{job.verdict ? <Badge tone={verdictTone(job.verdict)}>{job.verdict}</Badge> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
