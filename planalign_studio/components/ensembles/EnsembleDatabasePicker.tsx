import { useMemo, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { EnsembleDatabaseSummary, discoverEnsembleDatabases } from '../../services/api';
import { errorMessage } from './ensembleJobHelpers';

export interface EnsembleSource {
  database: string;
  scenarioId: string;
  ensembleId: string;
}

interface EnsembleDatabasePickerProps {
  readonly source: EnsembleSource;
  readonly onChange: (source: EnsembleSource) => void;
  readonly onLoad: () => void;
  readonly loading: boolean;
}

const INPUT_CLASS =
  'w-full rounded-md border border-border-strong p-2 text-sm shadow-sm focus:border-brand-green focus:ring-brand-green';

/** Advanced: open an ensemble database by path, or pick one found under the server's ensembles folder. */
export function EnsembleDatabasePicker({ source, onChange, onLoad, loading }: EnsembleDatabasePickerProps) {
  const [databases, setDatabases] = useState<EnsembleDatabaseSummary[]>([]);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [discoverLoading, setDiscoverLoading] = useState(false);
  const [scanned, setScanned] = useState(false);

  const runDiscovery = async () => {
    setDiscoverLoading(true);
    setDiscoverError(null);
    try {
      setDatabases(await discoverEnsembleDatabases());
      // Only a successful scan counts, so a failed first scan retries on the next open.
      setScanned(true);
    } catch (err) {
      setDiscoverError(errorMessage(err));
    } finally {
      setDiscoverLoading(false);
    }
  };

  const selectedSummary = useMemo(
    () => databases.find((item) => item.database_path === source.database) ?? null,
    [databases, source.database]
  );

  const update = (patch: Partial<EnsembleSource>) => onChange({ ...source, ...patch });

  const selectDatabase = (summary: EnsembleDatabaseSummary) =>
    update({
      database: summary.database_path,
      scenarioId: summary.scenario_ids[0] ?? '',
      ensembleId: summary.ensemble_ids[0] ?? '',
    });

  const canLoad = source.database.trim() !== '' && source.scenarioId.trim() !== '' && source.ensembleId.trim() !== '';

  return (
    <details
      className="bg-surface-raised rounded-lg shadow p-6"
      onToggle={(e) => {
        if (e.currentTarget.open && !scanned && !discoverLoading) void runDiscovery();
      }}
    >
      <summary className="cursor-pointer text-base font-semibold text-ink">Advanced: open an ensemble database</summary>
      <div className="mt-4 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-ink-muted">For ensembles made outside Studio. Pick one found on the server or enter its path.</p>
          <button
            type="button"
            onClick={() => void runDiscovery()}
            disabled={discoverLoading}
            className="flex shrink-0 items-center gap-2 rounded-md border border-border-strong px-3 py-1.5 text-sm text-ink-muted hover:bg-surface-subtle disabled:opacity-50"
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
                  summary.database_path === source.database
                    ? 'border-brand-green bg-surface-subtle'
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
              className={INPUT_CLASS}
              value={source.database}
              onChange={(e) => update({ database: e.target.value })}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-ink-muted">Scenario ID</span>
            <input
              type="text"
              list={selectedSummary ? 'ensemble-scenario-options' : undefined}
              className={INPUT_CLASS}
              value={source.scenarioId}
              onChange={(e) => update({ scenarioId: e.target.value })}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-ink-muted">Ensemble ID</span>
            <input
              type="text"
              list={selectedSummary ? 'ensemble-id-options' : undefined}
              className={INPUT_CLASS}
              value={source.ensembleId}
              onChange={(e) => update({ ensembleId: e.target.value })}
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
          onClick={onLoad}
          disabled={!canLoad || loading}
          className="flex items-center gap-2 rounded-md bg-brand-green px-4 py-2 text-sm font-medium text-ink-inverse disabled:opacity-50"
        >
          {loading && <Loader2 size={14} className="animate-spin" />}
          Load distributions
        </button>
      </div>
    </details>
  );
}
