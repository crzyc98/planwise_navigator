import { useCallback, useEffect, useState } from 'react';
import { EnsembleJob, listEnsembleJobs } from '../../services/api';
import { errorMessage, isActive } from './ensembleJobHelpers';

const POLL_MS = 2000;

interface EnsembleJobsState {
  jobs: EnsembleJob[];
  error: string | null;
  /** Put a job the caller just got from the API (start, cancel) into the list. */
  upsert: (job: EnsembleJob) => void;
}

/** A workspace's ensemble jobs, polled only while one is queued or running. */
export function useEnsembleJobs(workspaceId: string): EnsembleJobsState {
  const [jobs, setJobs] = useState<EnsembleJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const anyActive = jobs.some((job) => isActive(job.status));

  useEffect(() => {
    setJobs([]);
    setError(null);
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    // Drop late responses once the workspace changes or the page unmounts.
    let alive = true;
    const load = async () => {
      try {
        const loaded = await listEnsembleJobs(workspaceId);
        if (!alive) return;
        setJobs(loaded);
        setError(null);
      } catch (err) {
        if (alive) setError(errorMessage(err));
      }
    };
    void load();
    const timer = anyActive ? window.setInterval(() => void load(), POLL_MS) : undefined;
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [workspaceId, anyActive]);

  const upsert = useCallback((job: EnsembleJob) => {
    setJobs((current) =>
      current.some((item) => item.job_id === job.job_id)
        ? current.map((item) => (item.job_id === job.job_id ? job : item))
        : [job, ...current]
    );
  }, []);

  return { jobs, error, upsert };
}
