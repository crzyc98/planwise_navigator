import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Download, Search, X, AlertCircle, AlertTriangle, Info, FileText } from 'lucide-react';
import { SimulationLogLine, LogPage, fetchRunLogs, getRunLogDownloadUrl } from '../../services/api';

interface LogViewerProps {
  scenarioId: string;
  runId: string;
  isRunning?: boolean;
  liveLines?: SimulationLogLine[];
}

const SEVERITY_STYLES: Record<string, string> = {
  ERROR: 'bg-danger-surface text-danger-ink border-danger-border',
  WARNING: 'bg-warning-surface text-warning-ink border-warning-border',
  INFO: 'bg-surface-subtle text-ink-muted border-border',
};

const SEVERITY_ICONS: Record<string, React.ReactNode> = {
  ERROR: <AlertCircle size={12} className="inline mr-1" />,
  WARNING: <AlertTriangle size={12} className="inline mr-1" />,
  INFO: <Info size={12} className="inline mr-1" />,
};

type SeverityFilter = 'ALL' | 'INFO' | 'WARNING' | 'ERROR';

function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-warning-surface text-warning-ink rounded px-0.5">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export default function LogViewer({ scenarioId, runId, isRunning = false, liveLines = [] }: LogViewerProps) {
  const [logPage, setLogPage] = useState<LogPage | null>(null);
  const [page, setPage] = useState(1);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevLiveLinesLen = useRef(liveLines.length);

  const loadLogs = useCallback(async (targetPage: number, sev: SeverityFilter) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRunLogs(
        scenarioId,
        runId,
        targetPage,
        200,
        sev === 'ALL' ? undefined : sev,
      );
      setLogPage(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load logs');
    } finally {
      setLoading(false);
    }
  }, [scenarioId, runId]);

  useEffect(() => {
    setPage(1);
    loadLogs(1, severityFilter);
  }, [severityFilter, loadLogs]);

  useEffect(() => {
    loadLogs(page, severityFilter);
  }, [page, loadLogs, severityFilter]);

  // Auto-scroll when live lines arrive
  useEffect(() => {
    if (liveLines.length > prevLiveLinesLen.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    prevLiveLinesLen.current = liveLines.length;
  }, [liveLines]);

  // Merge paginated lines with live lines (dedup by sequence)
  const allLines = React.useMemo<SimulationLogLine[]>(() => {
    if (!logPage) return liveLines;
    const seenSeqs = new Set(logPage.lines.map(l => l.sequence));
    const newLive = liveLines.filter(l => !seenSeqs.has(l.sequence));
    return [...logPage.lines, ...newLive];
  }, [logPage, liveLines]);

  // Client-side search filter
  const displayLines = searchQuery
    ? allLines.filter(l => l.message.toLowerCase().includes(searchQuery.toLowerCase()))
    : allLines;

  const matchCount = searchQuery ? displayLines.length : null;

  if (!logPage && loading) {
    return (
      <div className="flex items-center justify-center py-8 text-ink-muted">
        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-fidelity-green mr-2" />
        Loading logs...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center py-4 text-danger-ink">
        <AlertCircle size={16} className="mr-2" />
        {error}
      </div>
    );
  }

  if (logPage && !logPage.log_available) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-ink-muted">
        <FileText size={32} className="mb-2 opacity-40" />
        <p className="text-sm">
          {isRunning ? 'Waiting for simulation to start writing logs…' : 'No log file found for this run.'}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        {/* Severity filter */}
        <div className="flex items-center border border-border rounded-lg overflow-hidden text-xs">
          {(['ALL', 'INFO', 'WARNING', 'ERROR'] as SeverityFilter[]).map(s => (
            <button
              key={s}
              onClick={() => { setSeverityFilter(s); setPage(1); }}
              className={`px-2.5 py-1.5 font-medium transition-colors ${
                severityFilter === s
                  ? 'bg-fidelity-green text-ink-inverse'
                  : 'bg-surface-raised text-ink-muted hover:bg-surface-subtle'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-subtle" />
          <input
            type="text"
            placeholder="Search logs…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-7 py-1.5 text-sm border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-fidelity-green"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-subtle hover:text-ink-muted"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {matchCount !== null && (
          <span className="text-xs text-ink-muted">{matchCount} match{matchCount !== 1 ? 'es' : ''} on this page</span>
        )}

        <div className="ml-auto flex items-center gap-2">
          {logPage && (
            <span className="text-xs text-ink-muted">{logPage.total_lines.toLocaleString()} lines total</span>
          )}
          <a
            href={getRunLogDownloadUrl(scenarioId, runId)}
            download="simulation.log"
            className="flex items-center px-3 py-1.5 text-sm bg-surface-subtle hover:bg-surface-disabled text-ink-muted rounded-lg font-medium"
          >
            <Download size={14} className="mr-1.5" />
            Download Logs
          </a>
        </div>
      </div>

      {/* Log lines */}
      <div className="flex-1 overflow-y-auto bg-surface-inverse rounded-lg p-3 font-mono text-xs min-h-[200px] max-h-[500px]">
        {displayLines.length === 0 ? (
          <p className="text-ink-muted text-center py-4">No log lines match the current filter.</p>
        ) : (
          displayLines.map(line => (
            <div key={line.sequence} className="flex items-start gap-2 py-0.5 hover:bg-surface-inverse rounded px-1">
              <span className="text-ink-muted select-none w-8 shrink-0 text-right">{line.sequence}</span>
              <span className={`shrink-0 px-1.5 rounded text-[10px] font-semibold border ${SEVERITY_STYLES[line.severity] || SEVERITY_STYLES.INFO}`}>
                {SEVERITY_ICONS[line.severity]}
                {line.severity}
              </span>
              <span className="text-ink-subtle shrink-0 text-[10px]">
                {new Date(line.timestamp).toLocaleTimeString(undefined, { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <span className={`break-all ${line.severity === 'ERROR' ? 'text-danger-ink' : line.severity === 'WARNING' ? 'text-warning-ink' : 'text-ink-subtle'}`}>
                {highlightMatch(line.message, searchQuery)}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Pagination */}
      {logPage && (logPage.has_more || page > 1) && (
        <div className="flex items-center justify-between mt-3">
          <button
            disabled={page <= 1}
            onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-40 hover:bg-surface-subtle"
          >
            Previous
          </button>
          <span className="text-xs text-ink-muted">Page {page}</span>
          <button
            disabled={!logPage.has_more}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-40 hover:bg-surface-subtle"
          >
            Load More
          </button>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-2 text-ink-muted text-xs">
          <div className="animate-spin rounded-full h-3 w-3 border-b border-fidelity-green mr-1" />
          Loading…
        </div>
      )}
    </div>
  );
}
