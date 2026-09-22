import React, { useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Loader2, Plus, RefreshCw, X } from 'lucide-react';
import {
  ApiError,
  EnsembleAttributionRow,
  EnsembleDatabaseSummary,
  EnsembleDistributionRow,
  EnsembleRiskStatement,
  Workspace,
  discoverEnsembleDatabases,
  getEnsembleAttribution,
  getEnsembleDistributions,
  getEnsembleRisk,
} from '../services/api';
import EnsembleAnalysisPanel, { EnsembleAnalysisData } from './EnsembleAnalysisPanel';

interface EnsemblesOutletContext {
  activeWorkspace: Workspace | null;
}

interface ThresholdRow {
  id: number;
  metric: string;
  value: string;
}

let nextThresholdRowId = 1;
const newThresholdRow = (): ThresholdRow => ({ id: nextThresholdRowId++, metric: '', value: '' });

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? (err.detail ?? err.message) : 'Something went wrong.';
}

export default function EnsemblesPage() {
  useOutletContext<EnsemblesOutletContext>();

  const [databases, setDatabases] = useState<EnsembleDatabaseSummary[]>([]);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [discoverLoading, setDiscoverLoading] = useState(false);

  const [database, setDatabase] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [ensembleId, setEnsembleId] = useState('');

  const [distributions, setDistributions] = useState<EnsembleDistributionRow[]>([]);
  const [attribution, setAttribution] = useState<EnsembleAttributionRow[]>([]);
  const [loadLoading, setLoadLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [thresholdRows, setThresholdRows] = useState<ThresholdRow[]>([newThresholdRow()]);
  const [riskStatements, setRiskStatements] = useState<EnsembleRiskStatement[]>([]);
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState<string | null>(null);

  const runDiscovery = async () => {
    setDiscoverLoading(true);
    setDiscoverError(null);
    try {
      setDatabases(await discoverEnsembleDatabases());
    } catch (err) {
      setDiscoverError(errorMessage(err));
    } finally {
      setDiscoverLoading(false);
    }
  };

  useEffect(() => {
    void runDiscovery();
  }, []);

  const selectedSummary = useMemo(
    () => databases.find((item) => item.database_path === database) ?? null,
    [databases, database]
  );

  const selectDatabase = (summary: EnsembleDatabaseSummary) => {
    setDatabase(summary.database_path);
    setScenarioId(summary.scenario_ids[0] ?? '');
    setEnsembleId(summary.ensemble_ids[0] ?? '');
  };

  const canLoad = database.trim() !== '' && scenarioId.trim() !== '' && ensembleId.trim() !== '';

  const loadAnalysis = async () => {
    if (!canLoad) return;
    setLoadLoading(true);
    setLoadError(null);
    setRiskStatements([]);
    try {
      const [distributionRows, attributionRows] = await Promise.all([
        getEnsembleDistributions(database, scenarioId, ensembleId),
        getEnsembleAttribution(database, scenarioId, ensembleId),
      ]);
      setDistributions(distributionRows);
      setAttribution(attributionRows);
    } catch (err) {
      setLoadError(errorMessage(err));
      setDistributions([]);
      setAttribution([]);
    } finally {
      setLoadLoading(false);
    }
  };

  const addThresholdRow = () => setThresholdRows((prev) => [...prev, newThresholdRow()]);
  const removeThresholdRow = (id: number) =>
    setThresholdRows((prev) => prev.filter((row) => row.id !== id));
  const updateThresholdRow = (id: number, patch: Partial<ThresholdRow>) =>
    setThresholdRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));

  const evaluateRisk = async () => {
    const thresholds = thresholdRows
      .filter((row) => row.metric.trim() !== '' && row.value.trim() !== '')
      .map((row) => ({ metric: row.metric.trim(), value: Number(row.value) }));
    if (thresholds.length === 0 || !canLoad) return;
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

  const analysisData: EnsembleAnalysisData = { distributions, riskStatements, attribution };

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-xl font-bold text-ink">Ensembles</h1>
        <p className="text-sm text-ink-muted">
          P10/P50/P90 outcome bands, threshold-exceedance risk, and variance attribution from a
          seed-ensemble aggregate database (<code>planalign simulate --seeds N</code>).
        </p>
      </div>

      <div className="bg-surface-raised rounded-lg shadow p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-ink">Select an ensemble database</h2>
          <button
            type="button"
            onClick={() => void runDiscovery()}
            disabled={discoverLoading}
            className="flex items-center gap-2 rounded-md border border-border-strong px-3 py-1.5 text-sm text-ink-muted hover:bg-surface-subtle disabled:opacity-50"
          >
            {discoverLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Rescan
          </button>
        </div>

        {discoverError && <p className="text-sm text-danger-ink">{discoverError}</p>}

        {databases.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {databases.map((summary) => (
              <button
                key={summary.database_path}
                type="button"
                onClick={() => selectDatabase(summary)}
                className={`rounded-md border p-3 text-left text-sm transition-colors ${
                  summary.database_path === database
                    ? 'border-fidelity-green bg-surface-subtle'
                    : 'border-border hover:bg-surface-subtle'
                }`}
              >
                <div className="font-medium text-ink">{summary.scenario_ids.join(', ') || summary.database_path}</div>
                <div className="mt-1 text-xs text-ink-muted">{summary.database_path}</div>
                <div className="mt-1 text-xs text-ink-muted">
                  {summary.min_simulation_year ?? '?'}–{summary.max_simulation_year ?? '?'} · {summary.metrics.length} metrics
                </div>
              </button>
            ))}
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block text-ink-muted">Database path</span>
            <input
              type="text"
              placeholder="/path/to/ensemble.duckdb"
              className="w-full rounded-md border border-border-strong p-2 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-ink-muted">Scenario ID</span>
            <input
              type="text"
              list={selectedSummary ? 'ensemble-scenario-options' : undefined}
              className="w-full rounded-md border border-border-strong p-2 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
              value={scenarioId}
              onChange={(e) => setScenarioId(e.target.value)}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-ink-muted">Ensemble ID</span>
            <input
              type="text"
              list={selectedSummary ? 'ensemble-id-options' : undefined}
              className="w-full rounded-md border border-border-strong p-2 text-sm shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
              value={ensembleId}
              onChange={(e) => setEnsembleId(e.target.value)}
            />
          </label>
        </div>
        {selectedSummary && (
          <>
            <datalist id="ensemble-scenario-options">
              {selectedSummary.scenario_ids.map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>
            <datalist id="ensemble-id-options">
              {selectedSummary.ensemble_ids.map((id) => (
                <option key={id} value={id} />
              ))}
            </datalist>
          </>
        )}

        <button
          type="button"
          onClick={() => void loadAnalysis()}
          disabled={!canLoad || loadLoading}
          className="flex items-center gap-2 rounded-md bg-fidelity-green px-4 py-2 text-sm font-medium text-ink-inverse disabled:opacity-50"
        >
          {loadLoading && <Loader2 size={14} className="animate-spin" />}
          Load distributions
        </button>
        {loadError && <p className="text-sm text-danger-ink">{loadError}</p>}
      </div>

      <div className="bg-surface-raised rounded-lg shadow p-6 space-y-3">
        <h2 className="text-base font-semibold text-ink">Threshold-exceedance risk</h2>
        <p className="text-sm text-ink-muted">
          Thresholds aren&apos;t stored in the ensemble database; enter one per metric to evaluate on demand.
        </p>
        <div className="space-y-2">
          {thresholdRows.map((row) => (
            <div key={row.id} className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                placeholder="metric (e.g. total_employer_plan_cost)"
                list={selectedSummary ? 'ensemble-metric-options' : undefined}
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
        {selectedSummary && (
          <datalist id="ensemble-metric-options">
            {selectedSummary.metrics.map((metric) => (
              <option key={metric} value={metric} />
            ))}
          </datalist>
        )}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={addThresholdRow}
            className="flex items-center gap-1 text-sm text-fidelity-green hover:underline"
          >
            <Plus size={14} /> Add threshold
          </button>
          <button
            type="button"
            onClick={() => void evaluateRisk()}
            disabled={!canLoad || riskLoading}
            className="flex items-center gap-2 rounded-md border border-border-strong px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {riskLoading && <Loader2 size={14} className="animate-spin" />}
            Evaluate risk
          </button>
        </div>
        {riskError && <p className="text-sm text-danger-ink">{riskError}</p>}
      </div>

      <EnsembleAnalysisPanel data={analysisData} />
    </div>
  );
}
