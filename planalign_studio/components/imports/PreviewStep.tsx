import React, { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, CheckCircle2, X, XCircle, Download } from 'lucide-react';
import {
  ImportSession,
  MappedPreviewResponse,
  ParquetFile,
  DataQualityResult,
  getMappedPreview,
  generateParquet,
  getImportStatus,
  downloadFlaggedRows,
} from '../../services/importService';

interface Props {
  workspaceId: string;
  session: ImportSession;
  onGenerated: (file: ParquetFile) => void;
}

interface DataQualityNoticeProps {
  workspaceId: string;
  importId: string;
  dataQuality: DataQualityResult;
}

/** Whole-file checks. Nothing here blocks generating the file. */
export function DataQualityNotice({ workspaceId, importId, dataQuality }: DataQualityNoticeProps) {
  const [dismissed, setDismissed] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const errors = dataQuality.plausibility.filter((r) => r.severity === 'error');
  const warnings = dataQuality.plausibility.filter((r) => r.severity === 'warning');
  const nulls = Object.entries(dataQuality.null_required_field_counts).filter(([, n]) => n > 0);
  const hasWarnings = warnings.length > 0 || nulls.length > 0 || dataQuality.duplicate_employee_id_count > 0;
  if (dismissed || (errors.length === 0 && !hasWarnings)) return null;

  const handleDownload = () => {
    setDownloadError(null);
    downloadFlaggedRows(workspaceId, importId).catch((err) =>
      setDownloadError(err instanceof Error ? err.message : 'Download failed'),
    );
  };
  const dismiss = (
    <button onClick={() => setDismissed(true)} aria-label="Dismiss" className="shrink-0">
      <X size={14} />
    </button>
  );

  return (
    <div className="space-y-2">
      {errors.length > 0 && (
        <div className="flex items-start gap-3 text-danger-ink text-sm bg-danger-surface border border-danger-border rounded-lg p-3">
          <XCircle size={16} className="shrink-0 mt-0.5" />
          <div className="flex-1 space-y-1">
            <div className="font-medium">Impossible values. You can still generate, but fix the source file if you can:</div>
            {errors.map((r) => <div key={r.rule_id}>{r.message}</div>)}
          </div>
          {dismiss}
        </div>
      )}
      {hasWarnings && (
        <div className="flex items-start gap-3 text-warning-ink text-sm bg-warning-surface border border-warning-border rounded-lg p-3">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          <div className="flex-1 space-y-1">
            <div className="font-medium">Data quality notice — review before generating:</div>
            {dataQuality.duplicate_employee_id_count > 0 && (
              <div>
                {dataQuality.duplicate_employee_id_count} duplicate employee ID row(s) —
                the simulation engine will automatically keep the row with the most recent hire date.
              </div>
            )}
            {nulls.map(([field, count]) => (
              <div key={field}>
                {count} row(s) have null <span className="font-mono">{field}</span> (required field).
              </div>
            ))}
            {warnings.map((r) => <div key={r.rule_id}>{r.message}</div>)}
          </div>
          {errors.length === 0 && dismiss}
        </div>
      )}
      {dataQuality.plausibility.length > 0 && (
        <div className="flex items-center gap-3 text-sm">
          <button onClick={handleDownload} className="flex items-center gap-1.5 text-brand-ink hover:underline">
            <Download size={14} />
            Download flagged rows (CSV)
          </button>
          {downloadError && <span className="text-danger-ink">{downloadError}</span>}
        </div>
      )}
    </div>
  );
}

export default function PreviewStep({ workspaceId, session, onGenerated }: Props) {
  const [preview, setPreview] = useState<MappedPreviewResponse | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    setIsLoadingPreview(true);
    getMappedPreview(workspaceId, session.import_id)
      .then(setPreview)
      .catch((err) => setPreviewError(err instanceof Error ? err.message : 'Preview failed'))
      .finally(() => setIsLoadingPreview(false));
  }, [workspaceId, session.import_id]);

  const handleGenerate = async () => {
    setIsGenerating(true);
    setGenError(null);
    try {
      await generateParquet(workspaceId, session.import_id);
      // Poll until completed or failed
      let attempts = 0;
      const poll = async () => {
        const status = await getImportStatus(workspaceId, session.import_id);
        if (status.status === 'completed') {
          // Get the parquet file from listing
          const { listParquetFiles } = await import('../../services/importService');
          const result = await listParquetFiles(workspaceId);
          const file = result.parquet_files.find((f) => f.import_id === session.import_id);
          if (file) onGenerated(file);
        } else if (status.status === 'failed') {
          setGenError(status.error_message ?? 'Generation failed');
          setIsGenerating(false);
        } else if (attempts < 30) {
          attempts++;
          setTimeout(poll, 2000);
        } else {
          setGenError('Generation timed out');
          setIsGenerating(false);
        }
      };
      await poll();
    } catch (err) {
      setGenError(err instanceof Error ? err.message : 'Generation failed');
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-5">
      {isLoadingPreview ? (
        <div className="flex items-center gap-2 text-sm text-ink-muted">
          <Loader2 size={16} className="animate-spin" />
          Loading preview…
        </div>
      ) : previewError ? (
        <div className="text-sm text-danger-ink bg-danger-surface border border-danger-border rounded-lg p-3">{previewError}</div>
      ) : preview && (
        <>
          {preview.data_quality && (
            <DataQualityNotice
              workspaceId={workspaceId}
              importId={session.import_id}
              dataQuality={preview.data_quality}
            />
          )}
          {preview.transformation_warnings.length > 0 && (
            <div className="space-y-2">
              {preview.transformation_warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-warning-ink text-sm bg-warning-surface border border-warning-border rounded-lg p-3">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                  <div>
                    <span className="font-medium">{w.input_column}</span>: {w.message}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-muted">
                Mapped Preview ({preview.preview_row_count} of {preview.total_row_count.toLocaleString()} rows)
              </h3>
              <span className="text-xs text-ink-subtle">{preview.columns.length} output columns</span>
            </div>
            <div className="overflow-x-auto border border-border rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-surface-subtle border-b border-border">
                  <tr>
                    {preview.columns.map((col) => (
                      <th key={col} className="px-3 py-2 text-left font-medium text-ink-muted uppercase whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {preview.rows.slice(0, 20).map((row, i) => (
                    <tr key={i} className="hover:bg-surface-subtle">
                      {preview.columns.map((col) => (
                        <td key={col} className="px-3 py-2 text-ink-muted font-mono whitespace-nowrap max-w-xs truncate">
                          {row[col] == null ? <span className="text-ink-subtle italic">null</span> : String(row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {genError && (
        <div className="text-sm text-danger-ink bg-danger-surface border border-danger-border rounded-lg p-3">{genError}</div>
      )}

      <div className="flex justify-end">
        {isGenerating ? (
          <div className="flex items-center gap-2 text-sm text-brand-ink">
            <Loader2 size={16} className="animate-spin" />
            Generating Parquet file…
          </div>
        ) : (
          <button
            onClick={handleGenerate}
            disabled={isLoadingPreview || !!previewError}
            className="flex items-center gap-2 px-5 py-2 bg-brand-green text-ink-inverse text-sm rounded-lg hover:bg-brand-dark disabled:opacity-50"
          >
            <CheckCircle2 size={16} />
            Generate Parquet File
          </button>
        )}
      </div>
    </div>
  );
}
