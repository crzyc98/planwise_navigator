import { Link } from 'react-router-dom';
import { Database, Check, AlertTriangle, Loader2, FileUp } from 'lucide-react';
import { useConfigContext } from './ConfigContext';
import { useWorkspacePath } from '../../hooks/useWorkspaceNavigation';

export function DataSourcesSection() {
  const importPath = useWorkspacePath('/import');
  const { formData, scenarioLoading } = useConfigContext();
  const loading = scenarioLoading || formData.censusDataStatus === 'validating';
  const error = formData.censusDataStatus === 'error' ? 'Census file could not be read' : null;
  const censusInfo = formData.censusDataPath && formData.censusDataStatus === 'loaded' ? {
    filename: formData.censusDataPath.split(/[\\/]/).pop() ?? formData.censusDataPath,
    rowCount: formData.censusRowCount,
    lastModified: formData.censusLastModified || null,
  } : null;

  return (
    <div className="space-y-8 animate-fadeIn">
      <div className="border-b border-border pb-4">
        <h2 className="text-lg font-bold text-ink">Data Sources</h2>
        <p className="text-sm text-ink-muted">
          {formData.censusDataSource === 'scenario' ? 'This scenario uses its own census file.' : 'Census data inherited from this workspace.'}
        </p>
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
              to={importPath}
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
              to={importPath}
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
              to={importPath}
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
