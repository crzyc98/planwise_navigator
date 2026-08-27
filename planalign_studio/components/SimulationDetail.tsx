import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Clock,
  Calendar,
  Users,
  Activity,
  Download,
  FileSpreadsheet,
  FileText,
  Database,
  Settings,
  CheckCircle,
  XCircle,
  CircleDot,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  History,
  Play,
  FolderOpen,
  ScrollText,
  ShieldCheck,
  Loader2,
} from 'lucide-react';
import { downloadRunProvenanceBundle, getRunDetails, getArtifactDownloadUrl, getResultsExportUrl, listRuns, getRunById, RunDetails, Artifact, RunSummary } from '../services/api';
import LogViewer from './simulation/LogViewer';
import EvidencePackPanel from './EvidencePackPanel';
import RunHealthSummary from './simulation/RunHealthSummary';
import { useWorkspaceNavigate } from '../hooks/useWorkspaceNavigation';

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

const formatDuration = (seconds: number | null): string => {
  if (seconds === null || seconds === undefined) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  const remainMins = mins % 60;
  return `${hours}h ${remainMins}m`;
};

const isArchivedProvenanceRun = (run: RunSummary): boolean => (
  !['pending', 'queued', 'running'].includes(run.status)
  && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(run.id)
);

const getStatusColor = (status: string) => {
  switch (status) {
    case 'completed':
      return 'bg-success-surface text-success-ink border-success-border';
    case 'running':
      return 'bg-info-surface text-info-ink border-info-border';
    case 'failed':
      return 'bg-danger-surface text-danger-ink border-danger-border';
    case 'cancelled':
      return 'bg-warning-surface text-warning-ink border-warning-border';
    case 'pending':
    case 'queued':
      return 'bg-warning-surface text-warning-ink border-warning-border';
    default:
      return 'bg-surface-subtle text-ink-muted border-border';
  }
};

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return <CheckCircle size={16} className="mr-1.5" />;
    case 'running':
      return <CircleDot size={16} className="mr-1.5 animate-pulse" />;
    case 'failed':
      return <XCircle size={16} className="mr-1.5" />;
    default:
      return <AlertCircle size={16} className="mr-1.5" />;
  }
};

const getArtifactIcon = (type: string) => {
  switch (type) {
    case 'excel':
      return <FileSpreadsheet size={18} className="text-success-ink" />;
    case 'yaml':
      return <FileText size={18} className="text-info-ink" />;
    case 'duckdb':
      return <Database size={18} className="text-info-ink" />;
    case 'json':
      return <FileText size={18} className="text-warning-ink" />;
    default:
      return <FileText size={18} className="text-ink-muted" />;
  }
};

export default function SimulationDetail() {
  const { scenarioId } = useParams<{ scenarioId: string }>();
  const navigate = useWorkspaceNavigate();

  const [details, setDetails] = useState<RunDetails | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set());
  const [runArtifacts, setRunArtifacts] = useState<Record<string, Artifact[]>>({});
  const [activeRunTab, setActiveRunTab] = useState<Record<string, 'artifacts' | 'logs' | 'evidence'>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [configExpanded, setConfigExpanded] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);
  const [provenanceDownloadRun, setProvenanceDownloadRun] = useState<string | null>(null);
  const [provenanceError, setProvenanceError] = useState<string | null>(null);

  useEffect(() => {
    const loadDetails = async () => {
      if (!scenarioId) return;

      try {
        setIsLoading(true);
        setError(null);

        // Load both scenario details and run history in parallel
        const [detailsData, runsData] = await Promise.all([
          getRunDetails(scenarioId),
          listRuns(scenarioId),
        ]);

        setDetails(detailsData);
        setRuns(runsData);

        // If we have runs, auto-expand the most recent one
        if (runsData.length > 0) {
          setExpandedRuns(new Set([runsData[0].id]));
          // Load artifacts for the first run
          try {
            const runDetails = await getRunById(scenarioId, runsData[0].id);
            setRunArtifacts({ [runsData[0].id]: runDetails.artifacts });
          } catch {
            // Ignore error loading first run artifacts
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load simulation details');
      } finally {
        setIsLoading(false);
      }
    };

    loadDetails();
  }, [scenarioId]);

  const toggleRunExpanded = async (runId: string) => {
    const newExpanded = new Set(expandedRuns);
    if (newExpanded.has(runId)) {
      newExpanded.delete(runId);
    } else {
      newExpanded.add(runId);
      // Load artifacts for this run if not already loaded
      if (!runArtifacts[runId] && scenarioId) {
        try {
          const runDetails = await getRunById(scenarioId, runId);
          setRunArtifacts(prev => ({ ...prev, [runId]: runDetails.artifacts }));
        } catch {
          // Ignore error
        }
      }
    }
    setExpandedRuns(newExpanded);
  };

  const handleCopyConfig = () => {
    if (details?.config) {
      navigator.clipboard.writeText(JSON.stringify(details.config, null, 2));
      setCopiedConfig(true);
      setTimeout(() => setCopiedConfig(false), 2000);
    }
  };

  const handleProvenanceDownload = async (runId: string) => {
    try {
      setProvenanceDownloadRun(runId);
      setProvenanceError(null);
      await downloadRunProvenanceBundle(runId);
    } catch (err) {
      setProvenanceError(err instanceof Error ? err.message : 'Failed to download audit report');
    } finally {
      setProvenanceDownloadRun(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-fidelity-green mx-auto mb-4"></div>
          <p className="text-ink-muted">Loading simulation details...</p>
        </div>
      </div>
    );
  }

  if (error || !details) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <AlertCircle size={48} className="text-danger-ink mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-ink mb-2">Error Loading Details</h2>
          <p className="text-ink-muted mb-4">{error || 'Simulation details not found'}</p>
          <button
            onClick={() => navigate('/simulate')}
            className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-dark"
          >
            Back to Simulations
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            <button
              onClick={() => navigate('/simulate')}
              className="mr-4 p-2 hover:bg-surface-subtle rounded-lg transition-colors"
              title="Back to Simulations"
            >
              <ArrowLeft size={20} className="text-ink-muted" />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-ink">{details.scenario_name}</h1>
              <p className="text-sm text-ink-muted">
                Workspace: <span className="font-medium">{details.workspace_name}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <span className={`inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium border ${getStatusColor(details.status)}`}>
              {getStatusIcon(details.status)}
              {details.status.toUpperCase().replace('_', ' ')}
            </span>
            {details.status === 'completed' && (
              <Link
                to={`/analytics?scenario=${details.scenario_id}`}
                className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse hover:bg-fidelity-dark rounded-lg font-medium shadow-sm"
              >
                <Activity size={18} className="mr-2" />
                View Analytics
              </Link>
            )}
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div className="bg-surface-subtle rounded-lg p-4 border border-border">
            <div className="flex items-center text-ink-muted text-sm mb-1">
              <Clock size={14} className="mr-1.5" />
              Duration
            </div>
            <p className="text-xl font-bold text-ink">{formatDuration(details.duration_seconds)}</p>
          </div>

          <div className="bg-surface-subtle rounded-lg p-4 border border-border">
            <div className="flex items-center text-ink-muted text-sm mb-1">
              <Calendar size={14} className="mr-1.5" />
              Years Simulated
            </div>
            <p className="text-xl font-bold text-ink">
              {details.start_year && details.end_year
                ? `${details.start_year}-${details.end_year}`
                : '--'}
            </p>
          </div>

          <div className="bg-surface-subtle rounded-lg p-4 border border-border">
            <div className="flex items-center text-ink-muted text-sm mb-1">
              <Users size={14} className="mr-1.5" />
              Final Headcount
            </div>
            <p className="text-xl font-bold text-ink">
              {details.final_headcount?.toLocaleString() || '--'}
            </p>
          </div>

          <div className="bg-surface-subtle rounded-lg p-4 border border-border">
            <div className="flex items-center text-ink-muted text-sm mb-1">
              <Activity size={14} className="mr-1.5" />
              Total Events
            </div>
            <p className="text-xl font-bold text-ink">
              {details.total_events?.toLocaleString() || '--'}
            </p>
          </div>
        </div>

        {/* Run Info */}
        <div className="mt-6 pt-4 border-t border-border">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-ink-muted">Run ID:</span>
              <code className="ml-2 bg-surface-subtle px-2 py-0.5 rounded text-xs font-mono">
                {details.id !== 'none' ? details.id : 'N/A'}
              </code>
            </div>
            <div>
              <span className="text-ink-muted">Started:</span>
              <span className="ml-2 text-ink">
                {details.started_at
                  ? new Date(details.started_at).toLocaleString()
                  : 'Never run'}
              </span>
            </div>
            <div>
              <span className="text-ink-muted">Completed:</span>
              <span className="ml-2 text-ink">
                {details.completed_at
                  ? new Date(details.completed_at).toLocaleString()
                  : '--'}
              </span>
            </div>
          </div>
        </div>

        {/* E087: Storage Location Section */}
        {details.storage_path && (
          <div className="mt-6 pt-4 border-t border-border">
            <div className="flex items-center text-sm">
              <FolderOpen size={16} className="text-ink-muted mr-2" />
              <span className="text-ink-muted">Storage Location:</span>
              <code className="ml-2 bg-surface-subtle px-3 py-1 rounded text-xs font-mono text-ink-muted break-all">
                {details.storage_path}
              </code>
            </div>
          </div>
        )}
      </div>

      {/* Run History Section - Full Width */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink flex items-center">
            <History size={20} className="mr-2 text-ink-muted" />
            Run History
          </h2>
          <span className="text-sm text-ink-muted">
            {runs.length} run{runs.length !== 1 ? 's' : ''}
          </span>
        </div>

        {runs.length === 0 ? (
          <div className="text-center py-8 text-ink-muted">
            <Play size={40} className="mx-auto mb-3 opacity-30" />
            <p>No runs yet.</p>
            <p className="text-sm mt-1">Start a simulation to see run history.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map((run, index) => (
              <div
                key={run.id}
                className={`border rounded-lg overflow-hidden ${index === 0 ? 'border-fidelity-green' : 'border-border'}`}
              >
                {/* Run Header */}
                <button
                  onClick={() => toggleRunExpanded(run.id)}
                  className={`w-full flex items-center justify-between p-4 hover:bg-surface-subtle transition-colors ${expandedRuns.has(run.id) ? 'bg-surface-subtle' : 'bg-surface-raised'}`}
                >
                  <div className="flex items-center space-x-4">
                    {expandedRuns.has(run.id) ? (
                      <ChevronDown size={18} className="text-ink-subtle" />
                    ) : (
                      <ChevronRight size={18} className="text-ink-subtle" />
                    )}
                    <div className="text-left">
                      <div className="flex items-center space-x-2">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(run.status)}`}>
                          {getStatusIcon(run.status)}
                          {run.status.toUpperCase()}
                        </span>
                        {index === 0 && (
                          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-fidelity-green/10 text-fidelity-green">
                            Latest
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-ink-muted mt-1">
                        {new Date(run.started_at).toLocaleString()}
                        {run.duration_seconds && (
                          <span className="ml-2 text-ink-subtle">({formatDuration(run.duration_seconds)})</span>
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-4 text-sm text-ink-muted">
                    {run.start_year && run.end_year && (
                      <span className="flex items-center">
                        <Calendar size={14} className="mr-1" />
                        {run.start_year}-{run.end_year}
                      </span>
                    )}
                    {run.final_headcount && (
                      <span className="flex items-center">
                        <Users size={14} className="mr-1" />
                        {run.final_headcount.toLocaleString()}
                      </span>
                    )}
                    <span className="flex items-center">
                      <Download size={14} className="mr-1" />
                      {run.artifact_count} files
                    </span>
                  </div>
                </button>

                {/* Expanded Run Panel */}
                {expandedRuns.has(run.id) && (
                  <div className="border-t border-border bg-surface-subtle">
                    {/* Tab bar */}
                    <div className="flex border-b border-border bg-surface-raised">
                      <button
                        onClick={() => setActiveRunTab(t => ({ ...t, [run.id]: 'artifacts' }))}
                        className={`flex items-center px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                          (activeRunTab[run.id] ?? 'artifacts') === 'artifacts'
                            ? 'border-fidelity-green text-fidelity-green'
                            : 'border-transparent text-ink-muted hover:text-ink-muted'
                        }`}
                      >
                        <Download size={14} className="mr-1.5" />
                        Artifacts
                      </button>
                      <button
                        onClick={() => setActiveRunTab(t => ({ ...t, [run.id]: 'logs' }))}
                        className={`flex items-center px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                          activeRunTab[run.id] === 'logs'
                            ? 'border-fidelity-green text-fidelity-green'
                            : 'border-transparent text-ink-muted hover:text-ink-muted'
                        }`}
                      >
                        <ScrollText size={14} className="mr-1.5" />
                        Logs
                      </button>
                      {run.status === 'completed' && index === 0 && run.start_year !== null && run.end_year !== null && (
                        <button
                          onClick={() => setActiveRunTab(t => ({ ...t, [run.id]: 'evidence' }))}
                          className={`flex items-center px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeRunTab[run.id] === 'evidence' ? 'border-fidelity-green text-fidelity-green' : 'border-transparent text-ink-muted hover:text-ink-muted'}`}
                        >
                          <FileText size={14} className="mr-1.5" />Evidence Pack
                        </button>
                      )}
                    </div>

                    <div className="p-4">
                      {isArchivedProvenanceRun(run) && (
                        <div className="mb-4">
                          <RunHealthSummary scenarioId={details.scenario_id} runId={run.id} />
                        </div>
                      )}
                      {isArchivedProvenanceRun(run) && (
                        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-success-border bg-success-surface p-3">
                          <ShieldCheck size={18} className="text-fidelity-green" />
                          <span className="mr-auto text-sm text-success-ink">
                            Review the execution evidence and integrity digest for this archived run.
                          </span>
                          <Link
                            to={`/simulate/${details.scenario_id}/runs/${run.id}/provenance`}
                            className="flex items-center rounded-lg border border-fidelity-green bg-surface-raised px-3 py-2 text-sm font-medium text-fidelity-green hover:bg-success-surface"
                          >
                            <ShieldCheck size={15} className="mr-1.5" />
                            View Provenance
                          </Link>
                          <button
                            onClick={() => void handleProvenanceDownload(run.id)}
                            disabled={provenanceDownloadRun !== null}
                            className="flex items-center rounded-lg bg-fidelity-green px-3 py-2 text-sm font-medium text-ink-inverse hover:bg-fidelity-dark disabled:opacity-60"
                          >
                            {provenanceDownloadRun === run.id ? (
                              <Loader2 size={15} className="mr-1.5 animate-spin" />
                            ) : (
                              <Download size={15} className="mr-1.5" />
                            )}
                            Download Audit Report
                          </button>
                        </div>
                      )}
                      {provenanceError && (
                        <p className="mb-3 rounded-lg bg-danger-surface px-3 py-2 text-sm text-danger-ink">
                          {provenanceError}
                        </p>
                      )}
                      {(activeRunTab[run.id] ?? 'artifacts') === 'artifacts' ? (
                        <>
                          {runArtifacts[run.id] ? (
                            runArtifacts[run.id].length > 0 ? (
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                                {runArtifacts[run.id].map((artifact) => (
                                  <a
                                    key={artifact.path}
                                    href={getArtifactDownloadUrl(details.scenario_id, artifact.path)}
                                    className="flex items-center p-3 bg-surface-raised hover:bg-surface-subtle rounded-lg border border-border transition-colors group"
                                  >
                                    {getArtifactIcon(artifact.type)}
                                    <div className="ml-3 flex-1 min-w-0">
                                      <p className="font-medium text-sm text-ink group-hover:text-fidelity-green truncate">
                                        {artifact.name}
                                      </p>
                                      <p className="text-xs text-ink-muted">
                                        {formatBytes(artifact.size_bytes)}
                                      </p>
                                    </div>
                                    <ExternalLink size={14} className="text-ink-subtle group-hover:text-fidelity-green ml-2" />
                                  </a>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-ink-muted text-center py-2">No artifacts found for this run.</p>
                            )
                          ) : (
                            <div className="flex items-center justify-center py-2">
                              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-fidelity-green"></div>
                              <span className="ml-2 text-sm text-ink-muted">Loading artifacts...</span>
                            </div>
                          )}
                        </>
                      ) : activeRunTab[run.id] === 'logs' ? (
                        <LogViewer
                          scenarioId={details.scenario_id}
                          runId={run.id}
                          isRunning={run.status === 'running'}
                        />
                      ) : run.start_year !== null && run.end_year !== null ? (
                        <EvidencePackPanel
                          workspaceId={details.workspace_id}
                          scenarioId={details.scenario_id}
                          startYear={run.start_year}
                          endYear={run.end_year}
                        />
                      ) : null}

                      {/* Run ID */}
                      <div className="mt-3 pt-3 border-t border-border">
                        <code className="text-xs text-ink-subtle font-mono">
                          Run ID: {run.id}
                        </code>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Configuration Panel - Collapsible */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink flex items-center">
            <Settings size={20} className="mr-2 text-ink-muted" />
            Configuration
          </h2>
          <div className="flex items-center space-x-2">
            <button
              onClick={handleCopyConfig}
              className="flex items-center px-3 py-1.5 text-ink-muted hover:text-ink hover:bg-surface-subtle rounded-lg text-sm"
              title="Copy configuration"
            >
              <Copy size={14} className="mr-1.5" />
              {copiedConfig ? 'Copied!' : 'Copy'}
            </button>
            <button
              onClick={() => setConfigExpanded(!configExpanded)}
              className="flex items-center px-3 py-1.5 text-ink-muted hover:text-ink hover:bg-surface-subtle rounded-lg text-sm"
            >
              {configExpanded ? (
                <>
                  <ChevronDown size={14} className="mr-1" />
                  Collapse
                </>
              ) : (
                <>
                  <ChevronRight size={14} className="mr-1" />
                  Expand
                </>
              )}
            </button>
          </div>
        </div>

        {/* Quick Config Summary - Always visible */}
        {details.config && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {details.config.simulation?.seed !== undefined && (
              <div className="bg-surface-subtle rounded-lg p-3 border border-border">
                <span className="text-ink-muted block text-xs">Seed</span>
                <span className="font-mono text-ink">{details.config.simulation.seed}</span>
              </div>
            )}
            {details.config.simulation?.growth_target !== undefined && (
              <div className="bg-surface-subtle rounded-lg p-3 border border-border">
                <span className="text-ink-muted block text-xs">Growth Target</span>
                <span className="text-ink">{(details.config.simulation.growth_target * 100).toFixed(1)}%</span>
              </div>
            )}
            {details.config.compensation?.merit_budget !== undefined && (
              <div className="bg-surface-subtle rounded-lg p-3 border border-border">
                <span className="text-ink-muted block text-xs">Merit Budget</span>
                <span className="text-ink">{(details.config.compensation.merit_budget * 100).toFixed(1)}%</span>
              </div>
            )}
            {details.config.turnover?.base_rate !== undefined && (
              <div className="bg-surface-subtle rounded-lg p-3 border border-border">
                <span className="text-ink-muted block text-xs">Turnover Rate</span>
                <span className="text-ink">{(details.config.turnover.base_rate * 100).toFixed(1)}%</span>
              </div>
            )}
          </div>
        )}

        {/* Full config JSON - Expandable */}
        {configExpanded && details.config && (
          <div className="mt-4 bg-surface-inverse rounded-lg overflow-hidden max-h-[400px] overflow-y-auto">
            <pre className="p-4 text-sm text-ink-subtle font-mono whitespace-pre-wrap">
              {JSON.stringify(details.config, null, 2)}
            </pre>
          </div>
        )}

        {!details.config && (
          <div className="text-center py-8 text-ink-muted">
            <Settings size={40} className="mx-auto mb-3 opacity-30" />
            <p>No configuration available.</p>
          </div>
        )}
      </div>

      {/* Error Message if Failed */}
      {details.status === 'failed' && details.error_message && (
        <div className="bg-danger-surface border border-danger-border rounded-xl p-6">
          <h3 className="text-lg font-semibold text-danger-ink flex items-center mb-2">
            <XCircle size={20} className="mr-2" />
            Simulation Error
          </h3>
          <pre className="bg-danger-surface p-4 rounded-lg text-sm text-danger-ink font-mono whitespace-pre-wrap overflow-x-auto">
            {details.error_message}
          </pre>
        </div>
      )}

      {/* Actions Footer */}
      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate('/simulate')}
            className="flex items-center px-4 py-2 text-ink-muted hover:text-ink hover:bg-surface-subtle rounded-lg"
          >
            <ArrowLeft size={18} className="mr-2" />
            Back to Simulations
          </button>
          <div className="flex items-center space-x-3">
            <Link
              to={`/config?scenario=${details.scenario_id}`}
              className="flex items-center px-4 py-2 text-ink-muted bg-surface-subtle hover:bg-surface-disabled rounded-lg font-medium"
            >
              <Settings size={18} className="mr-2" />
              Edit Configuration
            </Link>
            {details.status === 'completed' && (
              <Link
                to={`/analytics?scenario=${details.scenario_id}`}
                className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse hover:bg-fidelity-dark rounded-lg font-medium"
              >
                <Activity size={18} className="mr-2" />
                View Analytics
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
