import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Loader2, Plus, X } from 'lucide-react';
import {
  EnsembleAttributionRow,
  EnsembleDistributionRow,
  EnsembleJob,
  EnsembleRiskStatement,
  Scenario,
  Workspace,
  getEnsembleAttribution,
  getEnsembleDistributions,
  getEnsembleRisk,
  listScenarios,
} from '../services/api';
import EnsembleAnalysisPanel, { EnsembleAnalysisData } from './EnsembleAnalysisPanel';
import { EnsembleDatabasePicker, EnsembleSource } from './ensembles/EnsembleDatabasePicker';
import { EnsembleJobList } from './ensembles/EnsembleJobList';
import { RunEnsembleForm } from './ensembles/RunEnsembleForm';
import { RANGE_DISCLAIMER, errorMessage } from './ensembles/ensembleJobHelpers';
import { useEnsembleJobs } from './ensembles/useEnsembleJobs';

interface EnsemblesOutletContext {
  activeWorkspace: Workspace | null;
}

interface ThresholdRow {
  id: number;
  metric: string;
  value: string;
}

/** What the analysis panel is showing, and from where. */
interface LoadedEnsemble {
  source: EnsembleSource;
  label: string;
  jobId: string | null;
}

let nextThresholdRowId = 1;
const newThresholdRow = (): ThresholdRow => ({ id: nextThresholdRowId++, metric: '', value: '' });

const EMPTY_SOURCE: EnsembleSource = { database: '', scenarioId: '', ensembleId: '' };

export default function EnsemblesPage() {
  const { activeWorkspace } = useOutletContext<EnsemblesOutletContext>();
  const workspaceId = activeWorkspace?.id ?? '';

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const { jobs, error: jobsError, upsert } = useEnsembleJobs(workspaceId);

  const [manualSource, setManualSource] = useState<EnsembleSource>(EMPTY_SOURCE);
  const [loaded, setLoaded] = useState<LoadedEnsemble | null>(null);
  const [distributions, setDistributions] = useState<EnsembleDistributionRow[]>([]);
  const [attribution, setAttribution] = useState<EnsembleAttributionRow[]>([]);
  const [loadLoading, setLoadLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Only the latest open request may fill the panel.
  const loadRequestRef = useRef(0);

  const [thresholdRows, setThresholdRows] = useState<ThresholdRow[]>([newThresholdRow()]);
  const [riskStatements, setRiskStatements] = useState<EnsembleRiskStatement[]>([]);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);

  useEffect(() => {
    setScenarios([]);
    if (!workspaceId) return;
    let alive = true;
    listScenarios(workspaceId)
      .then((items) => alive && setScenarios(items))
      .catch(() => alive && setScenarios([]));
    return () => {
      alive = false;
    };
  }, [workspaceId]);

  const openEnsemble = async (target: LoadedEnsemble) => {
    const request = ++loadRequestRef.current;
    const { database, scenarioId, ensembleId } = target.source;
    setLoadLoading(true);
    setLoadError(null);
    setRiskStatements([]);
    setRiskError(null);
    try {
      const [distributionRows, attributionRows] = await Promise.all([
        getEnsembleDistributions(database, scenarioId, ensembleId),
        getEnsembleAttribution(database, scenarioId, ensembleId),
      ]);
      if (request !== loadRequestRef.current) return;
      setLoaded(target);
      setDistributions(distributionRows);
      setAttribution(attributionRows);
    } catch (err) {
      if (request !== loadRequestRef.current) return;
      setLoadError(errorMessage(err));
      setLoaded(null);
      setDistributions([]);
      setAttribution([]);
    } finally {
      if (request === loadRequestRef.current) setLoadLoading(false);
    }
  };

  const openJob = (job: EnsembleJob) => {
    if (!job.output) return;
    void openEnsemble({
      source: {
        database: job.output.database_path,
        scenarioId: job.output.ensemble_scenario_id,
        ensembleId: job.output.ensemble_id,
      },
      label: `${job.scenario_name}, ${job.seed_count} seeds, ${job.start_year}–${job.end_year}`,
      jobId: job.job_id,
    });
  };

  const openManual = () =>
    void openEnsemble({ source: manualSource, label: manualSource.database, jobId: null });

  const addThresholdRow = () => setThresholdRows((prev) => [...prev, newThresholdRow()]);
  const removeThresholdRow = (id: number) =>
    setThresholdRows((prev) => prev.filter((row) => row.id !== id));
  const updateThresholdRow = (id: number, patch: Partial<ThresholdRow>) =>
    setThresholdRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));

  const evaluateRisk = async () => {
    const thresholds = thresholdRows
      .filter((row) => row.metric.trim() !== '' && row.value.trim() !== '')
      .map((row) => ({ metric: row.metric.trim(), value: Number(row.value) }));
    if (thresholds.length === 0 || !loaded) return;
    const { database, scenarioId, ensembleId } = loaded.source;
    setRiskLoading(true);
    setRiskError(null);
    try {
      setRiskStatements(await getEnsembleRisk(database, scenarioId, ensembleId, thresholds));
    } catch (err) {
      setRiskError(errorMessage(err));
    } finally {
      setRiskLoading(false);
    }
  };

  const metrics = useMemo(() => [...new Set(distributions.map((row) => row.metric))].sort(), [distributions]);
  const analysisData: EnsembleAnalysisData = { distributions, riskStatements, attribution };

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-xl font-bold text-ink">Ensembles</h1>
        <p className="text-sm text-ink-muted">
          Run a scenario many times with different random seeds to see the range of likely outcomes (P10, P50, P90), not
          just one result.
        </p>
        <p className="mt-1 text-xs text-ink-muted">{RANGE_DISCLAIMER}</p>
      </div>

      <section className="bg-surface-raised rounded-lg shadow p-6 space-y-4">
        <h2 className="text-base font-semibold text-ink">Run an ensemble</h2>
        {activeWorkspace ? (
          <RunEnsembleForm key={workspaceId} workspaceId={workspaceId} scenarios={scenarios} onStarted={upsert} />
        ) : (
          <p className="text-sm text-ink-muted">Select a workspace to run an ensemble.</p>
        )}
      </section>

      {activeWorkspace && (
        <section className="bg-surface-raised rounded-lg shadow p-6 space-y-4">
          <h2 className="text-base font-semibold text-ink">Ensembles in this workspace</h2>
          {jobsError && <p className="text-sm text-danger-ink">{jobsError}</p>}
          <EnsembleJobList
            workspaceId={workspaceId}
            jobs={jobs}
            openedJobId={loaded?.jobId ?? null}
            onOpen={openJob}
            onChanged={upsert}
          />
          {loadLoading && (
            <p className="flex items-center gap-2 text-sm text-ink-muted">
              <Loader2 size={14} className="animate-spin" /> Opening results…
            </p>
          )}
          {loadError && <p className="text-sm text-danger-ink">{loadError}</p>}
        </section>
      )}

      <EnsembleDatabasePicker source={manualSource} onChange={setManualSource} onLoad={openManual} loading={loadLoading} />

      {loaded && (
        <div className="bg-surface-raised rounded-lg shadow p-6 space-y-3">
          <h2 className="text-base font-semibold text-ink">Threshold-exceedance risk</h2>
          <p className="text-sm text-ink-muted">
            Enter a metric and a value to see how often seeds land above it. Thresholds aren&apos;t saved.
          </p>
          <div className="space-y-2">
            {thresholdRows.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center gap-2">
                <input
                  type="text"
                  placeholder="metric (e.g. total_employer_plan_cost)"
                  list="ensemble-metric-options"
                  className="w-64 rounded-md border border-border-strong p-2 text-sm shadow-sm"
                  value={row.metric}
                  onChange={(e) => updateThresholdRow(row.id, { metric: e.target.value })}
                />
                <input
                  type="number"
                  placeholder="value"
                  className="w-32 rounded-md border border-border-strong p-2 text-sm shadow-sm"
                  value={row.value}
                  onChange={(e) => updateThresholdRow(row.id, { value: e.target.value })}
                />
                <button
                  type="button"
                  onClick={() => removeThresholdRow(row.id)}
                  className="text-ink-muted hover:text-danger-ink"
                  aria-label="Remove threshold"
                >
                  <X size={16} />
                </button>
              </div>
            ))}
          </div>
          <datalist id="ensemble-metric-options">
            {metrics.map((metric) => (
              <option key={metric} value={metric} />
            ))}
          </datalist>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={addThresholdRow}
              className="flex items-center gap-1 text-sm text-brand-ink hover:underline"
            >
              <Plus size={14} /> Add threshold
            </button>
            <button
              type="button"
              onClick={() => void evaluateRisk()}
              disabled={riskLoading}
              className="flex items-center gap-2 rounded-md border border-border-strong px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {riskLoading && <Loader2 size={14} className="animate-spin" />}
              Evaluate risk
            </button>
          </div>
          {riskError && <p className="text-sm text-danger-ink">{riskError}</p>}
        </div>
      )}

      {loaded && <p className="text-sm text-ink-muted">Showing {loaded.label}</p>}
      <EnsembleAnalysisPanel data={analysisData} />
    </div>
  );
}
