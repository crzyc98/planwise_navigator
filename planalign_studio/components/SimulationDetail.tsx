import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
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
} from 'lucide-react';
import { getRunDetails, getArtifactDownloadUrl, getResultsExportUrl, RunDetails, Artifact } from '../services/api';

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

const getStatusColor = (status: string) => {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-700 border-green-200';
    case 'running':
      return 'bg-blue-100 text-blue-700 border-blue-200';
    case 'failed':
      return 'bg-red-100 text-red-700 border-red-200';
    case 'cancelled':
      return 'bg-orange-100 text-orange-700 border-orange-200';
    case 'pending':
    case 'queued':
      return 'bg-yellow-100 text-yellow-700 border-yellow-200';
    default:
      return 'bg-gray-100 text-gray-600 border-gray-200';
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
      return <FileSpreadsheet size={18} className="text-green-600" />;
    case 'yaml':
      return <FileText size={18} className="text-blue-600" />;
    case 'duckdb':
      return <Database size={18} className="text-purple-600" />;
    case 'json':
      return <FileText size={18} className="text-yellow-600" />;
    default:
      return <FileText size={18} className="text-gray-500" />;
  }
};

export default function SimulationDetail() {
  const { scenarioId } = useParams<{ scenarioId: string }>();
  const navigate = useNavigate();

  const [details, setDetails] = useState<RunDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [configExpanded, setConfigExpanded] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);

  useEffect(() => {
    const loadDetails = async () => {
      if (!scenarioId) return;

      try {
        setIsLoading(true);
        setError(null);
        const data = await getRunDetails(scenarioId);
        setDetails(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load simulation details');
      } finally {
        setIsLoading(false);
      }
    };

    loadDetails();
  }, [scenarioId]);

  const handleCopyConfig = () => {
    if (details?.config) {
      navigator.clipboard.writeText(JSON.stringify(details.config, null, 2));
      setCopiedConfig(true);
      setTimeout(() => setCopiedConfig(false), 2000);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-fidelity-green mx-auto mb-4"></div>
          <p className="text-gray-500">Loading simulation details...</p>
        </div>
      </div>
    );
  }

  if (error || !details) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <AlertCircle size={48} className="text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-800 mb-2">Error Loading Details</h2>
          <p className="text-gray-500 mb-4">{error || 'Simulation details not found'}</p>
          <button
            onClick={() => navigate('/simulate')}
            className="px-4 py-2 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark"
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
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center">
            <button
              onClick={() => navigate('/simulate')}
              className="mr-4 p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="Back to Simulations"
            >
              <ArrowLeft size={20} className="text-gray-600" />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{details.scenario_name}</h1>
              <p className="text-sm text-gray-500">
                Workspace: <span className="font-medium">{details.workspace_name}</span>
              </p>
            </div>
          </div>
          <span className={`inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium border ${getStatusColor(details.status)}`}>
            {getStatusIcon(details.status)}
            {details.status.toUpperCase().replace('_', ' ')}
          </span>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center text-gray-500 text-sm mb-1">
              <Clock size={14} className="mr-1.5" />
              Duration
            </div>
            <p className="text-xl font-bold text-gray-900">{formatDuration(details.duration_seconds)}</p>
          </div>

          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center text-gray-500 text-sm mb-1">
              <Calendar size={14} className="mr-1.5" />
              Years Simulated
            </div>
            <p className="text-xl font-bold text-gray-900">
              {details.start_year && details.end_year
                ? `${details.start_year}-${details.end_year}`
                : '--'}
            </p>
          </div>

          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center text-gray-500 text-sm mb-1">
              <Users size={14} className="mr-1.5" />
              Final Headcount
            </div>
            <p className="text-xl font-bold text-gray-900">
              {details.final_headcount?.toLocaleString() || '--'}
            </p>
          </div>

          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center text-gray-500 text-sm mb-1">
              <Activity size={14} className="mr-1.5" />
              Total Events
            </div>
            <p className="text-xl font-bold text-gray-900">
              {details.total_events?.toLocaleString() || '--'}
            </p>
          </div>
        </div>

        {/* Run Info */}
        <div className="mt-6 pt-4 border-t border-gray-200">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Run ID:</span>
              <code className="ml-2 bg-gray-100 px-2 py-0.5 rounded text-xs font-mono">
                {details.id !== 'none' ? details.id : 'N/A'}
              </code>
            </div>
            <div>
              <span className="text-gray-500">Started:</span>
              <span className="ml-2 text-gray-900">
                {details.started_at
                  ? new Date(details.started_at).toLocaleString()
                  : 'Never run'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Completed:</span>
              <span className="ml-2 text-gray-900">
                {details.completed_at
                  ? new Date(details.completed_at).toLocaleString()
                  : '--'}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Artifacts Panel */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800 flex items-center">
              <Download size={20} className="mr-2 text-gray-500" />
              Output Artifacts
            </h2>
            {details.status === 'completed' && (
              <a
                href={getResultsExportUrl(details.scenario_id, 'excel')}
                className="flex items-center px-3 py-1.5 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark text-sm font-medium"
              >
                <FileSpreadsheet size={16} className="mr-1.5" />
                Export Excel
              </a>
            )}
          </div>

          {details.artifacts.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Download size={40} className="mx-auto mb-3 opacity-30" />
              <p>No artifacts available yet.</p>
              <p className="text-sm mt-1">Run the simulation to generate output files.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {details.artifacts.map((artifact) => (
                <a
                  key={artifact.path}
                  href={getArtifactDownloadUrl(details.scenario_id, artifact.path)}
                  className="flex items-center justify-between p-3 bg-gray-50 hover:bg-gray-100 rounded-lg border border-gray-200 transition-colors group"
                >
                  <div className="flex items-center">
                    {getArtifactIcon(artifact.type)}
                    <div className="ml-3">
                      <p className="font-medium text-gray-900 group-hover:text-fidelity-green">
                        {artifact.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {formatBytes(artifact.size_bytes)}
                        {artifact.created_at && (
                          <> &bull; {new Date(artifact.created_at).toLocaleDateString()}</>
                        )}
                      </p>
                    </div>
                  </div>
                  <ExternalLink size={16} className="text-gray-400 group-hover:text-fidelity-green" />
                </a>
              ))}
            </div>
          )}
        </div>

        {/* Configuration Panel */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800 flex items-center">
              <Settings size={20} className="mr-2 text-gray-500" />
              Configuration
            </h2>
            <div className="flex items-center space-x-2">
              <button
                onClick={handleCopyConfig}
                className="flex items-center px-3 py-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg text-sm"
                title="Copy configuration"
              >
                <Copy size={14} className="mr-1.5" />
                {copiedConfig ? 'Copied!' : 'Copy'}
              </button>
              <button
                onClick={() => setConfigExpanded(!configExpanded)}
                className="flex items-center px-3 py-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg text-sm"
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

          {details.config ? (
            <div className={`bg-gray-900 rounded-lg overflow-hidden ${configExpanded ? 'max-h-[600px]' : 'max-h-64'} overflow-y-auto transition-all`}>
              <pre className="p-4 text-sm text-gray-300 font-mono whitespace-pre-wrap">
                {JSON.stringify(details.config, null, 2)}
              </pre>
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <Settings size={40} className="mx-auto mb-3 opacity-30" />
              <p>No configuration available.</p>
            </div>
          )}

          {/* Quick Config Summary */}
          {details.config && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <h3 className="text-sm font-medium text-gray-700 mb-3">Quick Summary</h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {details.config.simulation?.seed && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Seed:</span>
                    <span className="font-mono text-gray-900">{details.config.simulation.seed}</span>
                  </div>
                )}
                {details.config.simulation?.growth_target && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Growth Target:</span>
                    <span className="text-gray-900">{(details.config.simulation.growth_target * 100).toFixed(1)}%</span>
                  </div>
                )}
                {details.config.compensation?.merit_budget && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Merit Budget:</span>
                    <span className="text-gray-900">{(details.config.compensation.merit_budget * 100).toFixed(1)}%</span>
                  </div>
                )}
                {details.config.turnover?.base_rate && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Turnover Rate:</span>
                    <span className="text-gray-900">{(details.config.turnover.base_rate * 100).toFixed(1)}%</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error Message if Failed */}
      {details.status === 'failed' && details.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-red-800 flex items-center mb-2">
            <XCircle size={20} className="mr-2" />
            Simulation Error
          </h3>
          <pre className="bg-red-100 p-4 rounded-lg text-sm text-red-900 font-mono whitespace-pre-wrap overflow-x-auto">
            {details.error_message}
          </pre>
        </div>
      )}

      {/* Actions Footer */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate('/simulate')}
            className="flex items-center px-4 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeft size={18} className="mr-2" />
            Back to Simulations
          </button>
          <div className="flex items-center space-x-3">
            <Link
              to={`/config?scenario=${details.scenario_id}`}
              className="flex items-center px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium"
            >
              <Settings size={18} className="mr-2" />
              Edit Configuration
            </Link>
            {details.status === 'completed' && (
              <Link
                to={`/analytics?scenario=${details.scenario_id}`}
                className="flex items-center px-4 py-2 bg-fidelity-green text-white hover:bg-fidelity-dark rounded-lg font-medium"
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
