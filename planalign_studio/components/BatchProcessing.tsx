import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useOutletContext, useSearchParams } from 'react-router-dom';
import {
  Plus, Play, FileDown, CheckCircle,
  Clock, AlertCircle, Trash2, ArrowRight, LayoutGrid, RotateCw,
  Layers, XCircle, CircleDot
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import {
  listScenarios,
  runAllScenarios,
  getBatchStatus,
  listBatchJobs,
  Scenario,
  BatchJob,
} from '../services/api';

export default function BatchProcessing() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

  const [view, setView] = useState<'list' | 'create' | 'details'>('list');
  const [selectedBatch, setSelectedBatch] = useState<BatchJob | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'running' | 'completed'>('all');

  // Data from API
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [batchJobs, setBatchJobs] = useState<BatchJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Creation State
  const [newBatchName, setNewBatchName] = useState('');
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [executionMode, setExecutionMode] = useState<'parallel' | 'sequential'>('sequential');
  const [exportFormat, setExportFormat] = useState<'excel' | 'csv'>('excel');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Active job polling
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Load scenarios and batch jobs
  useEffect(() => {
    const loadData = async () => {
      if (!activeWorkspace?.id) return;

      setLoading(true);
      setError(null);

      try {
        const [scenariosData, batchesData] = await Promise.all([
          listScenarios(activeWorkspace.id),
          listBatchJobs(activeWorkspace.id).catch(() => []), // May not have batch history
        ]);

        setScenarios(scenariosData);
        setBatchJobs(batchesData);
      } catch (err) {
        console.error('Failed to load data:', err);
        setError('Failed to load data');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [activeWorkspace?.id]);

  // Check for pre-selected scenarios from URL params
  useEffect(() => {
    const preselected = searchParams.get('scenarios');
    if (preselected) {
      const ids = preselected.split(',');
      setSelectedScenarioIds(ids);
      setView('create');
    }
  }, [searchParams]);

  // Poll for active job status
  useEffect(() => {
    if (!activeJobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const status = await getBatchStatus(activeJobId);
        setSelectedBatch(status);

        // Update in the list too
        setBatchJobs(prev => {
          const existing = prev.find(j => j.id === activeJobId);
          if (existing) {
            return prev.map(j => j.id === activeJobId ? status : j);
          }
          return [status, ...prev];
        });

        // Stop polling when completed or failed
        if (status.status === 'completed' || status.status === 'failed') {
          setActiveJobId(null);
        }
      } catch (err) {
        console.error('Failed to poll batch status:', err);
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [activeJobId]);

  const handleStartBatch = async () => {
    if (!activeWorkspace?.id || selectedScenarioIds.length === 0) return;

    setIsSubmitting(true);
    try {
      const batch = await runAllScenarios(activeWorkspace.id, {
        scenario_ids: selectedScenarioIds,
        name: newBatchName || `Batch ${new Date().toLocaleString()}`,
        parallel: executionMode === 'parallel',
        export_format: exportFormat,
      });

      setSelectedBatch(batch);
      setActiveJobId(batch.id);
      setBatchJobs(prev => [batch, ...prev]);
      setView('details');

      // Reset form
      setNewBatchName('');
      setSelectedScenarioIds([]);
    } catch (err) {
      console.error('Failed to start batch:', err);
      setError('Failed to start batch execution');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleViewDetails = (job: BatchJob) => {
    setSelectedBatch(job);
    if (job.status === 'running' || job.status === 'pending') {
      setActiveJobId(job.id);
    }
    setView('details');
  };

  const handleRerun = (job: BatchJob, e: React.MouseEvent) => {
    e.stopPropagation();
    setNewBatchName(`${job.name} (Rerun)`);
    setSelectedScenarioIds(job.scenarios.map(s => s.scenario_id));
    setExecutionMode(job.parallel ? 'parallel' : 'sequential');
    setExportFormat((job.export_format as 'excel' | 'csv') || 'excel');
    setView('create');
  };

  const toggleScenarioSelection = (id: string) => {
    setSelectedScenarioIds(prev =>
      prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]
    );
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-success-surface text-success-ink';
      case 'running': return 'bg-info-surface text-info-ink';
      case 'failed': return 'bg-danger-surface text-danger-ink';
      case 'pending': return 'bg-warning-surface text-warning-ink';
      default: return 'bg-surface-subtle text-ink-muted';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle size={14} className="mr-1" />;
      case 'running': return <CircleDot size={14} className="mr-1 animate-pulse" />;
      case 'failed': return <XCircle size={14} className="mr-1" />;
      default: return <Clock size={14} className="mr-1" />;
    }
  };

  // Filter jobs
  const getFilteredJobs = () => {
    if (statusFilter === 'all') return batchJobs;
    return batchJobs.filter(j => j.status === statusFilter);
  };

  if (!activeWorkspace) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-ink-subtle mx-auto mb-4" />
          <h2 className="text-lg font-medium text-ink">No Workspace Selected</h2>
          <p className="text-sm text-ink-muted mt-1">Please select a workspace from the sidebar.</p>
        </div>
      </div>
    );
  }

  // RENDER: Create View
  const renderCreateView = () => (
    <div className="max-w-4xl mx-auto animate-fadeIn">
      <div className="flex items-center mb-6">
        <button onClick={() => setView('list')} className="text-ink-muted hover:text-ink-muted mr-4 flex items-center">
          <ArrowRight className="transform rotate-180 mr-1" size={16}/> Back
        </button>
        <h2 className="text-xl font-bold text-ink">Create New Batch</h2>
      </div>

      <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-8 space-y-8">
        <div>
          <label htmlFor="batch-name" className="block text-sm font-medium text-ink-muted mb-2">Batch Name</label>
          <input
            id="batch-name"
            type="text"
            placeholder="e.g., Q3 Planning Scenarios"
            className="w-full p-2 border border-border-strong rounded-md focus:ring-fidelity-green focus:border-fidelity-green"
            value={newBatchName}
            onChange={e => setNewBatchName(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <fieldset>
            <legend className="block text-sm font-medium text-ink-muted mb-2">Execution Mode</legend>
            <div className="flex rounded-md shadow-sm">
              <button
                type="button"
                disabled
                title="Parallel mode is not yet supported"
                className="flex-1 px-4 py-2 text-sm font-medium border rounded-l-lg bg-surface-subtle text-ink-subtle border-border cursor-not-allowed"
              >
                Parallel
              </button>
              <button
                type="button"
                onClick={() => setExecutionMode('sequential')}
                className={`flex-1 px-4 py-2 text-sm font-medium border rounded-r-lg ${executionMode === 'sequential' ? 'bg-fidelity-green text-ink-inverse border-fidelity-green' : 'bg-surface-raised text-ink-muted border-border-strong hover:bg-surface-subtle'}`}
              >
                Sequential
              </button>
            </div>
            <p className="text-xs text-ink-muted mt-1">Sequential runs scenarios one at a time.</p>
          </fieldset>

          <fieldset>
            <legend className="block text-sm font-medium text-ink-muted mb-2">Export Format</legend>
            <div className="flex rounded-md shadow-sm">
              <button
                type="button"
                onClick={() => setExportFormat('excel')}
                className={`flex-1 px-4 py-2 text-sm font-medium border rounded-l-lg ${exportFormat === 'excel' ? 'bg-fidelity-green text-ink-inverse border-fidelity-green' : 'bg-surface-raised text-ink-muted border-border-strong hover:bg-surface-subtle'}`}
              >
                Excel (.xlsx)
              </button>
              <button
                type="button"
                onClick={() => setExportFormat('csv')}
                className={`flex-1 px-4 py-2 text-sm font-medium border rounded-r-lg ${exportFormat === 'csv' ? 'bg-fidelity-green text-ink-inverse border-fidelity-green' : 'bg-surface-raised text-ink-muted border-border-strong hover:bg-surface-subtle'}`}
              >
                CSV (.zip)
              </button>
            </div>
          </fieldset>
        </div>

        <div>
          <span className="block text-sm font-medium text-ink-muted mb-4">
            Select Scenarios to Run ({selectedScenarioIds.length} selected)
          </span>
          {scenarios.length === 0 ? (
            <div className="text-center py-8 text-ink-muted bg-surface-subtle rounded-lg border border-border">
              <Layers className="w-10 h-10 mx-auto mb-2 opacity-50" />
              <p>No scenarios available.</p>
              <button
                onClick={() => navigate('/scenarios')}
                className="mt-2 text-fidelity-green hover:underline text-sm"
              >
                Create a scenario first
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {scenarios.map(scenario => (
                <div
                  key={scenario.id}
                  role="checkbox"
                  aria-label={`Select ${scenario.name}`}
                  aria-checked={selectedScenarioIds.includes(scenario.id)}
                  tabIndex={0}
                  onClick={() => toggleScenarioSelection(scenario.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleScenarioSelection(scenario.id); } }}
                  className={`cursor-pointer p-4 rounded-lg border-2 transition-all ${selectedScenarioIds.includes(scenario.id) ? 'border-fidelity-green bg-success-surface' : 'border-border hover:border-border-strong'}`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-ink truncate">{scenario.name}</h3>
                      {scenario.description && (
                        <p className="text-xs text-ink-muted mt-1 truncate">{scenario.description}</p>
                      )}
                      <div className="mt-2 flex items-center space-x-2">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${getStatusColor(scenario.status)}`}>
                          {scenario.status === 'not_run' ? 'Not Run' : scenario.status}
                        </span>
                        {scenario.last_run_at && (
                          <span className="text-xs text-ink-subtle">
                            Last: {new Date(scenario.last_run_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                    {selectedScenarioIds.includes(scenario.id) && (
                      <CheckCircle className="text-fidelity-green flex-shrink-0 ml-2" size={20} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="pt-4 border-t border-border flex justify-end">
          <button
            disabled={selectedScenarioIds.length === 0 || isSubmitting}
            onClick={handleStartBatch}
            className={`flex items-center px-6 py-3 rounded-lg font-medium shadow-md transition-colors ${selectedScenarioIds.length === 0 || isSubmitting ? 'bg-surface-disabled text-ink-muted cursor-not-allowed' : 'bg-fidelity-green text-ink-inverse hover:bg-fidelity-dark'}`}
          >
            {isSubmitting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border mr-2"></div>
                Starting...
              </>
            ) : (
              <>
                <Play size={18} className="mr-2" />
                Launch Batch ({selectedScenarioIds.length} scenarios)
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );

  // RENDER: Details View
  const renderDetailsView = () => {
    if (!selectedBatch) return <div>Batch not found</div>;

    const completedCount = selectedBatch.scenarios.filter(s => s.status === 'completed').length;
    const progress = selectedBatch.scenarios.length > 0
      ? Math.round((completedCount / selectedBatch.scenarios.length) * 100)
      : 0;

    return (
      <div className="space-y-6 animate-fadeIn">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <button onClick={() => setView('list')} className="text-ink-muted hover:text-ink-muted mr-4 flex items-center">
              <ArrowRight className="transform rotate-180 mr-1" size={16}/> Back
            </button>
            <div>
              <h2 className="text-xl font-bold text-ink">{selectedBatch.name}</h2>
              <div className="flex items-center space-x-2 text-sm text-ink-muted mt-1">
                <span>ID: {selectedBatch.id.substring(0, 8)}...</span>
                <span>•</span>
                <span>Submitted: {new Date(selectedBatch.submitted_at).toLocaleString()}</span>
                <span>•</span>
                <span>{selectedBatch.parallel ? 'Parallel' : 'Sequential'} Mode</span>
              </div>
            </div>
          </div>
          {selectedBatch.status === 'completed' && (
            <button className="flex items-center px-4 py-2 bg-surface-raised border border-border-strong rounded-lg text-ink-muted hover:bg-surface-subtle transition-colors">
              <FileDown size={18} className="mr-2" /> Export Results
            </button>
          )}
        </div>

        {/* Status Card */}
        <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-semibold text-ink">Execution Status</h3>
            <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${getStatusColor(selectedBatch.status)}`}>
              {getStatusIcon(selectedBatch.status)}
              {selectedBatch.status}
            </span>
          </div>

          <div className="w-full bg-surface-subtle rounded-full h-3 mb-6">
            <div
              className="bg-fidelity-green h-3 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            ></div>
          </div>

          <div className="space-y-4">
            {selectedBatch.scenarios.map(scenario => (
              <div key={scenario.scenario_id} className="flex items-center justify-between p-4 bg-surface-subtle rounded-lg border border-border">
                <div className="flex items-center space-x-4 w-1/3">
                  <div className={`w-2 h-12 rounded-full ${scenario.status === 'completed' ? 'bg-success-solid' : scenario.status === 'running' ? 'bg-info-solid' : scenario.status === 'failed' ? 'bg-danger-solid' : 'bg-surface-disabled'}`}></div>
                  <div>
                    <p className="font-medium text-ink">{scenario.name}</p>
                    <p className="text-xs text-ink-muted">ID: {scenario.scenario_id.substring(0, 8)}...</p>
                  </div>
                </div>

                <div className="flex-1 px-4">
                  {scenario.status === 'running' && (
                    <div className="w-full bg-surface-disabled rounded-full h-2">
                      <div
                        className="bg-info-solid h-2 rounded-full transition-all duration-300"
                        style={{ width: `${scenario.progress}%` }}
                      ></div>
                    </div>
                  )}
                  {scenario.status === 'completed' && <span className="text-xs text-success-ink font-medium">Completed</span>}
                  {scenario.status === 'failed' && (
                    <span className="text-xs text-danger-ink font-medium">
                      {scenario.error_message || 'Failed'}
                    </span>
                  )}
                  {scenario.status === 'pending' && <span className="text-xs text-ink-subtle">Waiting in queue...</span>}
                </div>

                <div className="w-24 text-right">
                  {scenario.status === 'running' && <span className="text-sm font-mono">{Math.round(scenario.progress)}%</span>}
                  {scenario.status === 'completed' && <CheckCircle size={20} className="ml-auto text-success-ink" />}
                  {scenario.status === 'failed' && <XCircle size={20} className="ml-auto text-danger-ink" />}
                  {scenario.status === 'pending' && <Clock size={20} className="ml-auto text-ink-subtle" />}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Comparison link for completed batches */}
        {selectedBatch.status === 'completed' && selectedBatch.scenarios.length >= 2 && (
          <div className="bg-info-surface border border-info-border rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <LayoutGrid size={24} className="text-info-ink mr-3" />
                <div>
                  <h3 className="font-semibold text-info-ink">Compare Results</h3>
                  <p className="text-sm text-info-ink">View side-by-side comparison of all scenarios in this batch.</p>
                </div>
              </div>
              <button
                onClick={() => navigate(`/analytics/compare?scenarios=${selectedBatch.scenarios.map(s => s.scenario_id).join(',')}`)}
                className="px-4 py-2 bg-info-solid text-ink-inverse rounded-lg hover:bg-info-solid-hover font-medium"
              >
                View Comparison
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  // RENDER: List View
  const renderListView = () => {
    const jobs = getFilteredJobs();
    const runningJobs = jobs.filter(j => j.status === 'running' || j.status === 'pending');
    const historyJobs = jobs.filter(j => j.status !== 'running' && j.status !== 'pending');

    return (
      <div className="space-y-6 animate-fadeIn">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-ink">Batch Processing</h1>
            <p className="text-ink-muted mt-1">Run multiple scenarios and compare results.</p>
          </div>
          <button
            onClick={() => setView('create')}
            className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-dark transition-colors shadow-sm"
          >
            <Plus size={20} className="mr-2" />
            Create New Batch
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
              <p className="text-sm text-ink-muted">Loading batches...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <AlertCircle className="w-10 h-10 text-danger-ink mx-auto mb-3" />
              <p className="text-sm text-danger-ink">{error}</p>
            </div>
          </div>
        ) : (
          <>
            {/* Active Jobs Section */}
            {runningJobs.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-ink-muted uppercase tracking-wider">Active Executions</h3>
                {runningJobs.map((job) => (
                  <div key={job.id} className="bg-surface-raised rounded-lg border border-info-border shadow-sm p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="text-lg font-bold text-ink">{job.name}</h3>
                        <div className="flex items-center space-x-4 mt-1 text-sm text-ink-muted">
                          <span>{job.scenarios.length} Scenarios</span>
                          <span>•</span>
                          <span className="text-info-ink font-medium animate-pulse">Running...</span>
                          <span>•</span>
                          <span>{job.parallel ? 'Parallel' : 'Sequential'}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => handleViewDetails(job)}
                        className="px-4 py-2 border border-border-strong rounded text-ink-muted hover:bg-surface-subtle text-sm font-medium"
                      >
                        Monitor
                      </button>
                    </div>

                    {/* Inline Scenario Progress Summary */}
                    <div className="space-y-2 bg-surface-subtle p-3 rounded-lg border border-border">
                      {job.scenarios.map(s => (
                        <div key={s.scenario_id} className="flex items-center justify-between text-sm">
                          <span className="flex items-center text-ink-muted">
                            {s.status === 'completed' && <CheckCircle size={14} className="text-success-ink mr-2" />}
                            {s.status === 'running' && <div className="w-2 h-2 rounded-full bg-info-solid mr-2.5 animate-pulse"></div>}
                            {s.status === 'pending' && <div className="w-2 h-2 rounded-full bg-surface-disabled mr-2.5"></div>}
                            {s.status === 'failed' && <XCircle size={14} className="text-danger-ink mr-2" />}
                            {s.name}
                          </span>
                          <span className={`text-xs font-medium ${s.status === 'completed' ? 'text-success-ink' : s.status === 'running' ? 'text-info-ink' : s.status === 'failed' ? 'text-danger-ink' : 'text-ink-subtle'}`}>
                            {s.status === 'completed' ? 'Completed' :
                             s.status === 'running' ? `Running (${Math.round(s.progress)}%)` :
                             s.status === 'failed' ? 'Failed' : 'Pending'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* History Table */}
            <div className="bg-surface-raised rounded-xl shadow-sm border border-border overflow-hidden">
              <div className="px-6 py-4 border-b border-border flex justify-between items-center">
                <h3 className="font-semibold text-ink">Batch History</h3>

                {/* Filter Tabs */}
                <div className="flex space-x-1 bg-surface-subtle p-1 rounded-lg">
                  {['all', 'running', 'completed'].map((filter) => (
                    <button
                      key={filter}
                      onClick={() => setStatusFilter(filter as any)}
                      className={`px-3 py-1 text-xs font-medium rounded-md capitalize transition-colors ${statusFilter === filter ? 'bg-surface-raised text-ink shadow-sm' : 'text-ink-muted hover:text-ink-muted'}`}
                    >
                      {filter}
                    </button>
                  ))}
                </div>
              </div>

              {historyJobs.length === 0 && runningJobs.length === 0 ? (
                <div className="px-6 py-12 text-center">
                  <Layers className="w-12 h-12 text-ink-subtle mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-ink mb-1">No batches yet</h3>
                  <p className="text-sm text-ink-muted mb-4">Create a batch to run multiple scenarios together.</p>
                  <button
                    onClick={() => setView('create')}
                    className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark inline-flex items-center"
                  >
                    <Plus size={16} className="mr-2" />
                    Create Batch
                  </button>
                </div>
              ) : (
                <table className="min-w-full divide-y divide-border">
                  <thead className="bg-surface-subtle">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Batch Name</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Status</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Scenarios</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Submitted</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-ink-muted uppercase tracking-wider">Duration</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-ink-muted uppercase tracking-wider">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="bg-surface-raised divide-y divide-border">
                    {historyJobs.map((job) => (
                      <tr key={job.id} className="hover:bg-surface-subtle">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-ink">{job.name}</div>
                          <div className="text-xs text-ink-muted">{job.id.substring(0, 8)}...</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(job.status)}`}>
                            {getStatusIcon(job.status)}
                            {job.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted">
                          {job.scenarios.length}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted">
                          {new Date(job.submitted_at).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-ink-muted font-mono">
                          {job.duration_seconds ? `${Math.round(job.duration_seconds)}s` : '-'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <button
                            onClick={(e) => handleRerun(job, e)}
                            className="text-ink-muted hover:text-fidelity-green mr-4"
                            title="Re-run Batch"
                          >
                            <RotateCw size={16} />
                          </button>
                          <button
                            onClick={() => handleViewDetails(job)}
                            className="text-fidelity-green hover:text-fidelity-dark mr-4"
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="h-full">
      {view === 'list' && renderListView()}
      {view === 'create' && renderCreateView()}
      {view === 'details' && renderDetailsView()}
    </div>
  );
}
