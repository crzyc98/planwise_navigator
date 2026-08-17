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
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">Data Sources</h2>
        <p className="text-sm text-ink-muted">Active census data for this workspace.</p>
      </div>

      <div className="bg-surface-subtle rounded-xl p-6 border border-border">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            <Database className="w-5 h-5 text-fidelity-green mr-3" />
            <h3 className="font-semibold text-ink">Census Data</h3>
          </div>
          {censusInfo && !loading && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success-surface text-success-ink">
              <Check size={12} className="mr-1" />
              Active
            </span>
          )}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-ink-muted py-4">
            <Loader2 size={16} className="animate-spin" /> Checking census file…
          </div>
        ) : error ? (
          <div className="rounded-lg border border-warning-border bg-warning-surface p-4 space-y-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-warning-ink mt-0.5 shrink-0" />
              <p className="text-sm text-warning-ink">{error}</p>
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
            <div className="bg-surface-raised rounded-lg p-4 border border-border">
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-ink-muted block text-xs mb-1">File</span>
                  <span className="font-mono text-ink text-xs break-all">{censusInfo.filename}</span>
                </div>
                <div>
                  <span className="text-ink-muted block text-xs mb-1">Rows</span>
                  <span className="font-semibold text-ink">{censusInfo.rowCount.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-ink-muted block text-xs mb-1">Last Modified</span>
                  <span className="text-ink">{censusInfo.lastModified ?? '—'}</span>
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
          <div className="rounded-lg border-2 border-dashed border-border-strong p-8 text-center space-y-3">
            <Database className="w-10 h-10 text-ink-subtle mx-auto" />
            <p className="text-sm font-medium text-ink-muted">No census file configured</p>
            <p className="text-xs text-ink-subtle">
              Import a CSV, Excel, or Parquet file to get started.
            </p>
            <Link
              to="/import"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-fidelity-green text-ink-inverse text-sm font-medium rounded-lg hover:bg-fidelity-dark transition-colors"
            >
              <FileUp size={14} /> Import Data
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
