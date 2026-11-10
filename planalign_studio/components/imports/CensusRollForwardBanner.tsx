import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from 'lucide-react';
import {
  CensusRollForwardJob,
  CensusStatus,
  getCensusRollForward,
  getCensusStatus,
  startCensusRollForward,
} from '../../services/api';

const POLL_MS = 2000;

interface Props {
  workspaceId: string;
  /** The workspace census path; the status is re-read when it changes. */
  censusPath?: string;
  /** Called once a roll-forward has saved and activated the bridge census. */
  onRolledForward: () => void;
}

const isActive = (job: CensusRollForwardJob | null): boolean =>
  job !== null && (job.status === 'queued' || job.status === 'running');

/** Warns when the census is more than a year behind the start year (#1078). */
export default function CensusRollForwardBanner({ workspaceId, censusPath, onRolledForward }: Props) {
  const [status, setStatus] = useState<CensusStatus | null>(null);
  const [job, setJob] = useState<CensusRollForwardJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A job belongs to one workspace; forget it when the analyst switches.
  useEffect(() => {
    setJob(null);
    setError(null);
  }, [workspaceId]);

  useEffect(() => {
    let cancelled = false;
    getCensusStatus(workspaceId)
      .then((next) => {
        if (cancelled) return;
        setStatus(next);
        if (next.active_job) setJob(next.active_job);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, censusPath]);

  useEffect(() => {
    if (job === null || !isActive(job)) return;
    const timer = window.setInterval(() => {
      getCensusRollForward(workspaceId, job.id)
        .then((next) => {
          setJob(next);
          if (next.status === 'completed') onRolledForward();
        })
        .catch(() =>
          // The job is gone (for example, the API restarted): stop polling.
          setJob({ ...job, status: 'failed', error_message: 'Lost track of the roll-forward. Try again.' }),
        );
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [workspaceId, job, onRolledForward]);

  const start = useCallback(async () => {
    setError(null);
    try {
      setJob(await startCensusRollForward(workspaceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the roll-forward');
    }
  }, [workspaceId]);

  return <CensusRollForwardView status={status} job={job} error={error} onStart={start} />;
}

interface ViewProps {
  status: CensusStatus | null;
  job: CensusRollForwardJob | null;
  error: string | null;
  onStart: () => void;
}

/** The banner for a given status and job; renders nothing when the census is current. */
export function CensusRollForwardView({ status, job, error, onStart }: ViewProps) {
  if (job?.status === 'completed' && job.summary) return <RolledForward summary={job.summary} />;
  if (job !== null && isActive(job)) return <Running job={job} />;
  if (!status?.behind || status.census_year === null || status.bridge_year === null) return null;
  const failed = job?.status === 'failed';
  const problem = error ?? (failed ? job?.error_message ?? 'The roll-forward failed.' : null);
  return (
    <Behind
      censusYear={status.census_year}
      startYear={status.start_year}
      bridgeYear={status.bridge_year}
      problem={problem}
      retry={failed}
      onStart={onStart}
    />
  );
}

function RolledForward({ summary: s }: { summary: NonNullable<CensusRollForwardJob['summary']> }) {
  return (
    <div role="status" className="flex items-start gap-3 p-4 bg-success-surface border border-success-border rounded-lg text-sm text-success-ink">
      <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
      <div>
        <p className="font-medium">Census rolled forward to {s.bridge_year} and now in use</p>
        <p className="mt-1">
          {s.hires.toLocaleString()} hires · {s.terminations.toLocaleString()} terminations ·{' '}
          {s.ending_headcount.toLocaleString()} employees ({s.simulated_employees.toLocaleString()} simulated).
          The {s.census_year} census stays in Imported Files.
        </p>
      </div>
    </div>
  );
}

function Running({ job }: { job: CensusRollForwardJob }) {
  return (
    <div role="status" className="flex items-center gap-3 p-4 bg-info-surface border border-info-border rounded-lg text-sm text-info-ink">
      <Loader2 size={18} className="animate-spin shrink-0" />
      <span>
        {job.status === 'queued'
          ? `Waiting for a running simulation to finish before simulating ${job.bridge_year}…`
          : `Simulating ${job.bridge_year}…`}
      </span>
    </div>
  );
}

interface BehindProps {
  censusYear: number;
  startYear: number;
  bridgeYear: number;
  problem: string | null;
  retry: boolean;
  onStart: () => void;
}

function Behind({ censusYear, startYear, bridgeYear, problem, retry, onStart }: BehindProps) {
  const missing = bridgeYear === censusYear + 1 ? `${bridgeYear}` : `${censusYear + 1}–${bridgeYear}`;
  return (
    <div className="p-4 bg-warning-surface border border-warning-border rounded-lg text-sm text-warning-ink space-y-3">
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
        <p>
          Your census is from {censusYear}, but simulations start in {startYear}. {missing} has no hires, so
          first-year turnover will run low. Rolling forward simulates {missing} once and uses the result as the
          census.
        </p>
      </div>
      {problem && (
        <p className="flex items-center gap-2 text-danger-ink">
          <XCircle size={16} className="shrink-0" />
          {problem}
        </p>
      )}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onStart}
          className="px-3 py-1.5 text-sm font-medium bg-brand-green text-ink-inverse rounded-md hover:opacity-90"
        >
          {retry ? 'Try again' : `Roll forward to ${bridgeYear}`}
        </button>
      </div>
    </div>
  );
}
