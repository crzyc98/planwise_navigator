import React, { useEffect, useState } from 'react';
import { Download, Trash2, Loader2, AlertCircle, Check } from 'lucide-react';
import {
  ParquetFile,
  listParquetFiles,
  downloadParquetFileUrl,
  deleteParquetFile,
} from '../../services/importService';
import { setCensusPath } from '../../services/api';

interface Props {
  workspaceId: string;
  currentUserId?: string;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ImportedFilesList({ workspaceId, currentUserId = 'system' }: Props) {
  const [files, setFiles] = useState<ParquetFile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [settingCensus, setSettingCensus] = useState<string | null>(null);
  const [censusSuccess, setCensusSuccess] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    listParquetFiles(workspaceId)
      .then((r) => setFiles(r.parquet_files))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load files'))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [workspaceId]);

  const handleSetCensus = async (fileId: string, storagePath: string) => {
    setSettingCensus(fileId);
    try {
      await setCensusPath(workspaceId, storagePath);
      setCensusSuccess(fileId);
      setTimeout(() => setCensusSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set census path');
    } finally {
      setSettingCensus(null);
    }
  };

  const handleDelete = async (fileId: string) => {
    setDeletingId(fileId);
    try {
      await deleteParquetFile(workspaceId, fileId);
      setFiles((prev) => prev.filter((f) => f.file_id !== fileId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeletingId(null);
      setConfirmDelete(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-6">
        <Loader2 size={16} className="animate-spin" /> Loading imported files…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3">
        <AlertCircle size={16} className="shrink-0 mt-0.5" /> {error}
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="text-sm text-gray-400 py-6 text-center">
        No imported files yet. Use "Import Data" to create your first Parquet file.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Imported Files ({files.length})</h3>
        <button onClick={load} className="text-xs text-fidelity-green hover:underline">Refresh</button>
      </div>
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Filename</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Rows</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">Size</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">By</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {files.map((f) => (
              <tr key={f.file_id} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-mono text-xs text-gray-800 max-w-xs truncate">{f.filename}</td>
                <td className="px-4 py-2 text-xs text-gray-500 max-w-xs truncate">{f.original_filename}</td>
                <td className="px-4 py-2 text-xs text-gray-700 text-right">{f.row_count.toLocaleString()}</td>
                <td className="px-4 py-2 text-xs text-gray-700 text-right">{formatBytes(f.file_size_bytes)}</td>
                <td className="px-4 py-2 text-xs text-gray-500">
                  {new Date(f.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-2 text-xs text-gray-500">{f.created_by}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3 justify-end">
                    {settingCensus === f.file_id ? (
                      <Loader2 size={14} className="animate-spin text-fidelity-green" />
                    ) : censusSuccess === f.file_id ? (
                      <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                        <Check size={12} /> Set
                      </span>
                    ) : (
                      <button
                        onClick={() => handleSetCensus(f.file_id, f.storage_path)}
                        className="text-xs text-fidelity-green font-medium hover:underline whitespace-nowrap"
                        title="Use this file as the workspace census data source"
                      >
                        Use as Census
                      </button>
                    )}
                    <a
                      href={downloadParquetFileUrl(workspaceId, f.file_id)}
                      download={f.filename}
                      className="text-fidelity-green hover:text-fidelity-dark"
                      title="Download"
                    >
                      <Download size={16} />
                    </a>
                    {f.created_by === currentUserId && (
                      confirmDelete === f.file_id ? (
                        <span className="flex items-center gap-1">
                          <button
                            onClick={() => handleDelete(f.file_id)}
                            disabled={!!deletingId}
                            className="text-xs text-red-600 hover:underline"
                          >
                            {deletingId === f.file_id ? <Loader2 size={12} className="animate-spin inline" /> : 'Confirm'}
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="text-xs text-gray-400 hover:underline"
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={() => setConfirmDelete(f.file_id)}
                          className="text-gray-400 hover:text-red-500"
                          title="Delete"
                        >
                          <Trash2 size={16} />
                        </button>
                      )
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
