import React, { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, CheckCircle2, X } from 'lucide-react';
import {
  ImportSession,
  MappedPreviewResponse,
  ParquetFile,
  DataQualityResult,
  getMappedPreview,
  generateParquet,
  getImportStatus,
} from '../../services/importService';

interface Props {
  workspaceId: string;
  session: ImportSession;
  onGenerated: (file: ParquetFile) => void;
  dataQuality?: DataQualityResult | null;
}

export default function PreviewStep({ workspaceId, session, onGenerated, dataQuality }: Props) {
  const [dqDismissed, setDqDismissed] = useState(false);
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

  const hasDqIssues = dataQuality && !dqDismissed && (
    dataQuality.duplicate_employee_id_count > 0 ||
    dataQuality.compensation_outlier_count > 0 ||
    Object.values(dataQuality.null_required_field_counts).some((n) => n > 0)
  );

  return (
    <div className="space-y-5">
      {hasDqIssues && dataQuality && (
        <div className="flex items-start gap-3 text-amber-800 text-sm bg-amber-50 border border-amber-200 rounded-lg p-3">
          <AlertTriangle size={16} className="shrink-0 mt-0.5 text-amber-600" />
          <div className="flex-1 space-y-1">
            <div className="font-medium">Data quality notice — review before generating:</div>
            {dataQuality.duplicate_employee_id_count > 0 && (
              <div>
                {dataQuality.duplicate_employee_id_count} duplicate employee ID(s) detected —
                the simulation engine will automatically keep the row with the most recent hire date.
              </div>
            )}
            {Object.entries(dataQuality.null_required_field_counts).map(([field, count]) =>
              count > 0 ? (
                <div key={field}>
                  {count} row(s) have null <span className="font-mono">{field}</span> (required field).
                </div>
              ) : null
            )}
            {dataQuality.compensation_outlier_count > 0 && (
              <div>
                {dataQuality.compensation_outlier_count} row(s) have unusual compensation values
                (&lt;$1,000 or &gt;$10M) — please verify.
              </div>
            )}
          </div>
          <button onClick={() => setDqDismissed(true)} className="text-amber-500 hover:text-amber-700 shrink-0">
            <X size={14} />
          </button>
        </div>
      )}

      {isLoadingPreview ? (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 size={16} className="animate-spin" />
          Loading preview…
        </div>
      ) : previewError ? (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">{previewError}</div>
      ) : preview && (
        <>
          {preview.transformation_warnings.length > 0 && (
            <div className="space-y-2">
              {preview.transformation_warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-amber-700 text-sm bg-amber-50 border border-amber-200 rounded-lg p-3">
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
              <h3 className="text-sm font-semibold text-gray-700">
                Mapped Preview ({preview.preview_row_count} of {preview.total_row_count.toLocaleString()} rows)
              </h3>
              <span className="text-xs text-gray-400">{preview.columns.length} output columns</span>
            </div>
            <div className="overflow-x-auto border border-gray-200 rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {preview.columns.map((col) => (
                      <th key={col} className="px-3 py-2 text-left font-medium text-gray-500 uppercase whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {preview.rows.slice(0, 20).map((row, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      {preview.columns.map((col) => (
                        <td key={col} className="px-3 py-2 text-gray-700 font-mono whitespace-nowrap max-w-xs truncate">
                          {row[col] == null ? <span className="text-gray-300 italic">null</span> : String(row[col])}
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
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">{genError}</div>
      )}

      <div className="flex justify-end">
        {isGenerating ? (
          <div className="flex items-center gap-2 text-sm text-fidelity-green">
            <Loader2 size={16} className="animate-spin" />
            Generating Parquet file…
          </div>
        ) : (
          <button
            onClick={handleGenerate}
            disabled={isLoadingPreview || !!previewError}
            className="flex items-center gap-2 px-5 py-2 bg-fidelity-green text-white text-sm rounded-lg hover:bg-fidelity-dark disabled:opacity-50"
          >
            <CheckCircle2 size={16} />
            Generate Parquet File
          </button>
        )}
      </div>
    </div>
  );
}
