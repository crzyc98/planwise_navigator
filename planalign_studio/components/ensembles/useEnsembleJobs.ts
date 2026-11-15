import { useCallback, useEffect, useRef, useState } from 'react';
import { EnsembleJob, listEnsembleJobs } from '../../services/api';
import { errorMessage, isActive } from './ensembleJobHelpers';

const POLL_MS = 2000;

interface EnsembleJobsState {
  jobs: EnsembleJob[];
  error: string | null;
  /** Put a job the caller just got from the API (start, cancel) into the list. */
  upsert: (job: EnsembleJob) => void;
}

/**
 * A workspace's ensemble jobs, polled only while one is queued or running.
 *
 * Polls are sequential (the next is scheduled after a response), and a list
 * requested before the latest local change (start, cancel) is dropped so it
 * can't revert that change.
 */
export function useEnsembleJobs(workspaceId: string): EnsembleJobsState {
  const [jobs, setJobs] = useState<EnsembleJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const localChangeRef = useRef(0);
  const anyActive = jobs.some((job) => isActive(job.status));

  useEffect(() => {
    setJobs([]);
    setError(null);
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    // Stop scheduling, and drop late responses, once the workspace changes or the page unmounts.
    let alive = true;
    let timer: number | undefined;
    const load = async () => {
      const changeAtRequest = localChangeRef.current;
      try {
        const loaded = await listEnsembleJobs(workspaceId);
        if (!alive) return;
        if (changeAtRequest === localChangeRef.current) setJobs(loaded);
        setError(null);
      } catch (err) {
        if (alive) setError(errorMessage(err));
      }
      if (alive && anyActive) timer = window.setTimeout(() => void load(), POLL_MS);
    };
    void load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [workspaceId, anyActive]);

  const upsert = useCallback((job: EnsembleJob) => {
    localChangeRef.current += 1;
    setJobs((current) =>
      current.some((item) => item.job_id === job.job_id)
        ? current.map((item) => (item.job_id === job.job_id ? job : item))
        : [job, ...current]
    );
  }, []);

  return { jobs, error, upsert };
}
