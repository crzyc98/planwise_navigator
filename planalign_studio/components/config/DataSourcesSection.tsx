import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Database, Check, AlertTriangle, Loader2, FileUp } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { getWorkspace, validateFilePath } from '../../services/api';

interface CensusInfo {
  path: string;
  filename: string;
  rowCount: number;
  lastModified: string | null;
}

export function DataSourcesSection() {
  const { activeWorkspace } = useConfigContext();
  const [censusInfo, setCensusInfo] = useState<CensusInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeWorkspace?.id) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    getWorkspace(activeWorkspace.id)
      .then(async (ws) => {
        const path = (ws.base_config as any)?.setup?.census_parquet_path as string | undefined;
        if (!path) {
          setCensusInfo(null);
          setLoading(false);
          return;
        }

        try {
          const v = await validateFilePath(activeWorkspace.id!, path);
          if (v.valid) {
            const filename = path.split('/').pop() ?? path;
            setCensusInfo({
              path,
              filename,
              rowCount: v.row_count ?? 0,
              lastModified: v.last_modified ? v.last_modified.split('T')[0] : null,
            });
          } else {
            setError(v.error_message ?? 'Census file could not be read');
          }
        } catch {
          setError('Could not validate census file');
        }
        setLoading(false);
      })
      .catch(() => {
        setError('Could not load workspace');
        setLoading(false);
      });
  }, [activeWorkspace?.id]);

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-gray-100 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Data Sources</h2>
        <p className="text-sm text-gray-500">Active census data for this workspace.</p>
      </div>

      <div className="bg-gray-50 rounded-xl p-6 border border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            <Database className="w-5 h-5 text-fidelity-green mr-3" />
            <h3 className="font-semibold text-gray-900">Census Data</h3>
          </div>
          {censusInfo && !loading && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
              <Check size={12} className="mr-1" />
              Active
            </span>
          )}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
            <Loader2 size={16} className="animate-spin" /> Checking census file…
          </div>
        ) : error ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
              <p className="text-sm text-amber-800">{error}</p>
            </div>
            <Link
              to="/import"
              className="inline-flex items-center gap-1 text-sm font-medium text-fidelity-green hover:underline"
            >
              <FileUp size={14} /> Import a new census file
            </Link>
          </div>
        ) : censusInfo ? (
          <div className="space-y-4">
            <div className="bg-white rounded-lg p-4 border border-gray-200">
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-gray-500 block text-xs mb-1">File</span>
                  <span className="font-mono text-gray-900 text-xs break-all">{censusInfo.filename}</span>
                </div>
                <div>
                  <span className="text-gray-500 block text-xs mb-1">Rows</span>
                  <span className="font-semibold text-gray-900">{censusInfo.rowCount.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-gray-500 block text-xs mb-1">Last Modified</span>
                  <span className="text-gray-900">{censusInfo.lastModified ?? '—'}</span>
                </div>
              </div>
            </div>
            <Link
              to="/import"
              className="inline-flex items-center gap-1 text-sm text-fidelity-green hover:underline"
            >
              <FileUp size={14} /> Change census file via Import
            </Link>
          </div>
        ) : (
          <div className="rounded-lg border-2 border-dashed border-gray-300 p-8 text-center space-y-3">
            <Database className="w-10 h-10 text-gray-300 mx-auto" />
            <p className="text-sm font-medium text-gray-600">No census file configured</p>
            <p className="text-xs text-gray-400">
              Import a CSV, Excel, or Parquet file to get started.
            </p>
            <Link
              to="/import"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-fidelity-green text-white text-sm font-medium rounded-lg hover:bg-fidelity-dark transition-colors"
            >
              <FileUp size={14} /> Import Data
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
