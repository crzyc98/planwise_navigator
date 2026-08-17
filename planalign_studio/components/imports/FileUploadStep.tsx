import React, { useRef, useState } from 'react';
import { Upload, AlertCircle, Loader2, Check } from 'lucide-react';
import { ImportSession, DetectedColumn, uploadFile, selectSheet } from '../../services/importService';
import { uploadCensusFile, FileUploadResponse } from '../../services/api';

interface Props {
  workspaceId: string;
  onDone: (session: ImportSession) => void;
  onParquetDone?: (result: FileUploadResponse) => void;
}

function InferredTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    string: 'bg-info-surface text-info-ink',
    integer: 'bg-success-surface text-success-ink',
    decimal: 'bg-teal-100 text-teal-700',
    boolean: 'bg-info-surface text-info-ink',
    date: 'bg-warning-surface text-warning-ink',
    timestamp: 'bg-warning-surface text-warning-ink',
    unknown: 'bg-surface-subtle text-ink-muted',
  };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${colors[type] ?? 'bg-surface-subtle text-ink-muted'}`}>
      {type}
    </span>
  );
}

export default function FileUploadStep({ workspaceId, onDone, onParquetDone }: Props) {
  const [session, setSession] = useState<ImportSession | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSelectingSheet, setIsSelectingSheet] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isParquetUploading, setIsParquetUploading] = useState(false);
  const [parquetError, setParquetError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const parquetInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setError(null);
    setIsUploading(true);
    try {
      const result = await uploadFile(workspaceId, file);
      setSession(result);
      if (result.available_sheets.length <= 1) {
        onDone(result);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  const handleParquetFile = async (file: File) => {
    setParquetError(null);
    setIsParquetUploading(true);
    try {
      const result = await uploadCensusFile(workspaceId, file);
      onParquetDone?.(result);
    } catch (err) {
      setParquetError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsParquetUploading(false);
      if (parquetInputRef.current) parquetInputRef.current.value = '';
    }
  };

  const handleSheetSelect = async (sheetName: string) => {
    if (!session) return;
    setIsSelectingSheet(true);
    setError(null);
    try {
      const updated = await selectSheet(workspaceId, session.import_id, sheetName);
      setSession(updated);
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sheet selection failed');
    } finally {
      setIsSelectingSheet(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  if (session && session.available_sheets.length > 1 && !session.sheet_name) {
    return (
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-ink-muted">Select Excel Sheet</h3>
        <p className="text-sm text-ink-muted">
          {session.original_filename} contains {session.available_sheets.length} sheets. Which one should be imported?
        </p>
        <div className="space-y-2">
          {session.available_sheets.map((sheet) => (
            <button
              key={sheet}
              onClick={() => handleSheetSelect(sheet)}
              disabled={isSelectingSheet}
              className="w-full text-left px-4 py-3 border border-border rounded-lg hover:border-fidelity-green hover:bg-success-surface transition-colors text-sm font-medium text-ink-muted"
            >
              {isSelectingSheet ? <Loader2 size={14} className="inline animate-spin mr-2" /> : null}
              {sheet}
            </button>
          ))}
        </div>
        {error && <p className="text-sm text-danger-ink">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* CSV / Excel drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          isDragging ? 'border-fidelity-green bg-success-surface' : 'border-border-strong hover:border-fidelity-green hover:bg-surface-subtle'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={handleInputChange}
        />
        {isUploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={40} className="text-fidelity-green animate-spin" />
            <p className="text-sm font-medium text-ink-muted">Uploading and analyzing file…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <Upload size={40} className="text-ink-subtle" />
            <p className="text-sm font-medium text-ink-muted">Drop a CSV or Excel file here</p>
            <p className="text-xs text-ink-subtle">or click to browse — max 500 MB</p>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-2 text-danger-ink text-sm bg-danger-surface border border-danger-border rounded-lg p-3">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {session && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink-muted">Detected Columns ({session.column_count})</h3>
            <span className="text-xs text-ink-subtle">{session.row_count.toLocaleString()} rows</span>
          </div>
          {session.encoding_warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-warning-ink text-xs bg-warning-surface border border-warning-border rounded-lg p-2">
              <AlertCircle size={14} className="shrink-0 mt-0.5" />
              {w}
            </div>
          ))}
          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-surface-subtle border-b border-border">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Column</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Type</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Nulls</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-ink-muted uppercase">Samples</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {session.detected_columns.map((col: DetectedColumn) => (
                  <tr key={col.name} className="hover:bg-surface-subtle">
                    <td className="px-4 py-2 font-mono text-xs text-ink">{col.name}</td>
                    <td className="px-4 py-2"><InferredTypeBadge type={col.inferred_type} /></td>
                    <td className="px-4 py-2 text-xs text-ink-muted">{col.null_count}</td>
                    <td className="px-4 py-2 text-xs text-ink-subtle max-w-xs truncate">
                      {col.sample_values.slice(0, 3).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Parquet direct upload */}
      {onParquetDone && (
        <>
          <div className="flex items-center gap-3 text-xs text-ink-subtle">
            <div className="flex-1 border-t border-border" />
            or upload a Parquet directly
            <div className="flex-1 border-t border-border" />
          </div>

          <div
            onClick={() => parquetInputRef.current?.click()}
            className="border-2 border-dashed border-border rounded-xl p-6 text-center cursor-pointer hover:border-fidelity-green hover:bg-surface-subtle transition-colors"
          >
            <input
              ref={parquetInputRef}
              type="file"
              accept=".parquet"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleParquetFile(file);
              }}
            />
            {isParquetUploading ? (
              <div className="flex flex-col items-center gap-2">
                <Loader2 size={28} className="text-fidelity-green animate-spin" />
                <p className="text-sm text-ink-muted">Validating and saving Parquet…</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Check size={28} className="text-ink-subtle" />
                <p className="text-sm font-medium text-ink-muted">Already have a Parquet?</p>
                <p className="text-xs text-ink-subtle">Drop or click to upload a .parquet file — no mapping needed</p>
              </div>
            )}
          </div>

          {parquetError && (
            <div className="flex items-start gap-2 text-danger-ink text-sm bg-danger-surface border border-danger-border rounded-lg p-3">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              <span>{parquetError}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
