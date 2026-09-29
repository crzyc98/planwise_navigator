import { useRef, useState } from 'react';
import { Loader2, Trash2, Upload } from 'lucide-react';
import { deleteFitHistory, FitHistorySet, uploadFitHistory } from '../../services/api';
import { errorText } from './paramFitUi';
import { shortHash } from './paramFitHelpers';

interface HistoryStepProps {
  readonly workspaceId: string;
  readonly histories: FitHistorySet[];
  readonly selectedId: string | null;
  readonly onSelect: (historyId: string) => void;
  readonly onChanged: (selectId?: string | null) => void;
}

/** Upload 2-5 annual census snapshots, then check exactly what the fitter will read. */
export function HistoryStep({ workspaceId, histories, selectedId, onSelect, onChanged }: HistoryStepProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = histories.find((item) => item.history_id === selectedId) ?? null;

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const created = await uploadFitHistory(workspaceId, Array.from(files));
      onChanged(created.history_id);
    } catch (uploadError) {
      setError(errorText(uploadError));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function handleDelete(historyId: string) {
    setError(null);
    try {
      await deleteFitHistory(workspaceId, historyId);
      onChanged(historyId === selectedId ? null : selectedId);
    } catch (deleteError) {
      setError(errorText(deleteError));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv,.parquet"
          className="hidden"
          onChange={(event) => void handleFiles(event.target.files)}
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="inline-flex items-center gap-2 rounded-lg bg-fidelity-green px-4 py-2 text-sm font-medium text-ink-inverse transition-colors hover:bg-fidelity-dark disabled:cursor-not-allowed disabled:bg-surface-disabled"
        >
          {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
          {uploading ? 'Validating…' : 'Upload census snapshots'}
        </button>
        <span className="text-xs text-ink-muted">
          2–5 consecutive annual files (.csv or .parquet), one per year, e.g. census_2023.csv.
        </span>
      </div>

      {error && (
        <div className="rounded-lg border border-danger-border bg-danger-surface p-3 text-sm text-danger-ink">{error}</div>
      )}

      {histories.length > 0 && (
        <label className="block max-w-xl">
          <span className="mb-1 block text-sm font-medium text-ink">History set</span>
          <select
            value={selectedId ?? ''}
            onChange={(event) => onSelect(event.target.value)}
            className="w-full rounded-md border border-border-strong bg-surface-raised p-2 text-sm text-ink shadow-sm focus:border-fidelity-green focus:ring-fidelity-green"
          >
            {histories.map((history) => (
              <option key={history.history_id} value={history.history_id}>
                {history.snapshots.map((snapshot) => snapshot.year).join(', ')} · uploaded{' '}
                {new Date(history.created_at).toLocaleString()}
              </option>
            ))}
          </select>
        </label>
      )}

      {selected && <HistoryPreview history={selected} onDelete={() => void handleDelete(selected.history_id)} />}
    </div>
  );
}

function HistoryPreview({ history, onDelete }: { history: FitHistorySet; onDelete: () => void }) {
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="min-w-full text-sm">
          <thead className="bg-surface-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th className="px-3 py-2">Year</th>
              <th className="px-3 py-2">As of</th>
              <th className="px-3 py-2">File</th>
              <th className="px-3 py-2 text-right">Rows</th>
              <th className="px-3 py-2">SHA-256</th>
              <th className="px-3 py-2">Optional columns</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {history.snapshots.map((snapshot) => (
              <tr key={snapshot.year}>
                <td className="px-3 py-2 font-medium text-ink">{snapshot.year}</td>
                <td className="px-3 py-2 text-ink-muted">{snapshot.as_of_date}</td>
                <td className="px-3 py-2 text-ink">{snapshot.filename}</td>
                <td className="px-3 py-2 text-right tabular-nums text-ink">{snapshot.row_count.toLocaleString()}</td>
                <td className="px-3 py-2 font-mono text-xs text-ink-muted" title={snapshot.sha256}>
                  {shortHash(snapshot.sha256)}
                </td>
                <td className="px-3 py-2 text-xs text-ink-muted">
                  {snapshot.columns_present.length ? snapshot.columns_present.join(', ') : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
        <span title={history.source_digest}>
          Source digest <span className="font-mono">{shortHash(history.source_digest, 16)}</span>
        </span>
        <button
          type="button"
          onClick={onDelete}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-ink-muted hover:bg-surface-subtle hover:text-danger-ink"
        >
          <Trash2 size={14} /> Remove this history set
        </button>
      </div>
    </div>
  );
}
