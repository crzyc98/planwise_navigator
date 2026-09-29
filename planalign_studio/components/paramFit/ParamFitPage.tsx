import { useCallback, useEffect, useState } from 'react';
import { Link, useOutletContext } from 'react-router-dom';
import {
  FitHistorySet,
  getParamFit,
  listFitHistory,
  listParamFits,
  listScenarios,
  ParamFitJob,
  ParamFitJobSummary,
  Scenario,
  Workspace,
} from '../../services/api';
import { ApplyPackModal } from './ApplyPackModal';
import { ConfigureStep } from './ConfigureStep';
import { FitResults } from './FitResults';
import { HistoryStep } from './HistoryStep';
import { JobList } from './JobList';
import { JobProgress } from './JobProgress';
import { isTerminal } from './paramFitHelpers';
import { errorText, StepHeader } from './paramFitUi';

interface ParamFitOutletContext {
  activeWorkspace: Workspace | null;
}

const POLL_MS = 1500;

/**
 * Fit & Backtest (#588): fit simulation parameters from a client's census
 * history, optionally score them against held-out years, and apply an
 * accepted pack to a new scenario — all without the command line.
 */
export default function ParamFitPage() {
  const { activeWorkspace } = useOutletContext<ParamFitOutletContext>();
  const workspaceId = activeWorkspace?.id ?? '';

  const [histories, setHistories] = useState<FitHistorySet[]>([]);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [jobs, setJobs] = useState<ParamFitJobSummary[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<ParamFitJob | null>(null);
  const [showApply, setShowApply] = useState(false);
  const [applied, setApplied] = useState<Scenario | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshHistories = useCallback(
    async (selectId?: string | null) => {
      if (!workspaceId) return;
      try {
        const items = await listFitHistory(workspaceId);
        setHistories(items);
        setHistoryId((current) => {
          const wanted = selectId === undefined ? current : selectId;
          return items.some((item) => item.history_id === wanted) ? wanted : (items[0]?.history_id ?? null);
        });
      } catch (loadError) {
        setError(errorText(loadError));
      }
    },
    [workspaceId]
  );

  const refreshJobs = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setJobs(await listParamFits(workspaceId));
    } catch (loadError) {
      setError(errorText(loadError));
    }
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    setJobId(null);
    setJob(null);
    void refreshHistories(null);
    void refreshJobs();
    listScenarios(workspaceId)
      .then(setScenarios)
      .catch(() => setScenarios([]));
  }, [workspaceId, refreshHistories, refreshJobs]);

  useEffect(() => {
    if (!workspaceId || !jobId) {
      setJob(null);
      return;
    }
    let cancelled = false;
    getParamFit(workspaceId, jobId)
      .then((loaded) => !cancelled && setJob(loaded))
      .catch((loadError) => !cancelled && setError(errorText(loadError)));
    return () => {
      cancelled = true;
    };
  }, [workspaceId, jobId]);

  const anyActive = jobs.some((item) => !isTerminal(item.status));
  const selectedActive = job !== null && !isTerminal(job.status);

  useEffect(() => {
    if (!workspaceId || (!anyActive && !selectedActive)) return;
    const timer = window.setInterval(() => {
      void refreshJobs();
      if (jobId) {
        getParamFit(workspaceId, jobId)
          .then(setJob)
          .catch(() => undefined);
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [workspaceId, jobId, anyActive, selectedActive, refreshJobs]);

  const history = histories.find((item) => item.history_id === historyId) ?? null;
  const backtestRunning = jobs.some((item) => item.mode === 'backtest' && !isTerminal(item.status));

  if (!activeWorkspace) {
    return <p className="text-sm text-ink-muted">Select a workspace to fit parameters.</p>;
  }

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-xl font-bold text-ink">Fit &amp; Backtest</h1>
        <p className="text-sm text-ink-muted">
          Learn termination, promotion, merit, and deferral assumptions from a client's census history, check them against
          years the fit never saw, and turn an accepted result into a new scenario.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-danger-border bg-danger-surface p-3 text-sm text-danger-ink">
          {error}
          <button type="button" onClick={() => setError(null)} className="ml-2 underline">
            Dismiss
          </button>
        </div>
      )}

      <section className="space-y-4 rounded-lg bg-surface-raised p-6 shadow">
        <StepHeader n={1} title="Census history">
          Upload consecutive annual snapshots and check exactly what the fit will read.
        </StepHeader>
        <HistoryStep
          workspaceId={workspaceId}
          histories={histories}
          selectedId={historyId}
          onSelect={setHistoryId}
          onChanged={(selectId) => void refreshHistories(selectId)}
        />
      </section>

      <section className="space-y-4 rounded-lg bg-surface-raised p-6 shadow">
        <StepHeader n={2} title="Configure and run">
          Choose the scenario whose assumptions act as priors, and whether to backtest.
        </StepHeader>
        <ConfigureStep
          workspaceId={workspaceId}
          history={history}
          scenarios={scenarios}
          backtestRunning={backtestRunning}
          onLaunched={(launched) => {
            setJobId(launched.job_id);
            setJob(launched);
            void refreshJobs();
          }}
        />
      </section>

      <section className="space-y-4 rounded-lg bg-surface-raised p-6 shadow">
        <StepHeader n={3} title="Results">
          Pick a job to inspect its evidence. Jobs are kept even if Studio restarts.
        </StepHeader>
        <JobList jobs={jobs} selectedId={jobId} onSelect={setJobId} />
        {applied && (
          <div className="rounded-lg border border-success-border bg-success-surface p-3 text-sm text-success-ink">
            Created scenario <span className="font-medium">{applied.name}</span>.{' '}
            <Link to={`/w/${workspaceId}/config/${applied.id}`} className="underline">
              Open it
            </Link>{' '}
            to review or run it.
          </div>
        )}
        {job && (
          <JobProgress
            workspaceId={workspaceId}
            job={job}
            onChanged={(updated) => {
              setJob(updated);
              void refreshJobs();
            }}
          />
        )}
        {job?.status === 'completed' && job.result && (
          <FitResults workspaceId={workspaceId} job={job} result={job.result} onApply={() => setShowApply(true)} />
        )}
      </section>

      {showApply && job && (
        <ApplyPackModal
          workspaceId={workspaceId}
          job={job}
          scenarios={scenarios}
          onClose={() => setShowApply(false)}
          onApplied={(scenario) => {
            setShowApply(false);
            setApplied(scenario);
            setScenarios((current) => [...current, scenario]);
          }}
        />
      )}
    </div>
  );
}
