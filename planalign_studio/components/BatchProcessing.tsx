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
  const [executionMode, setExecutionMode] = useState<'parallel' | 'sequential'>('parallel');
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
      case 'completed': return 'bg-green-100 text-green-700';
      case 'running': return 'bg-blue-100 text-blue-700';
      case 'failed': return 'bg-red-100 text-red-700';
      case 'pending': return 'bg-yellow-100 text-yellow-700';
      default: return 'bg-gray-100 text-gray-600';
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
          <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h2 className="text-lg font-medium text-gray-900">No Workspace Selected</h2>
          <p className="text-sm text-gray-500 mt-1">Please select a workspace from the sidebar.</p>
        </div>
      </div>
    );
  }

  // RENDER: Create View
  const renderCreateView = () => (
    <div className="max-w-4xl mx-auto animate-fadeIn">
      <div className="flex items-center mb-6">
        <button onClick={() => setView('list')} className="text-gray-500 hover:text-gray-700 mr-4 flex items-center">
          <ArrowRight className="transform rotate-180 mr-1" size={16}/> Back
        </button>
        <h2 className="text-xl font-bold text-gray-900">Create New Batch</h2>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 space-y-8">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Batch Name</label>
          <input
            type="text"
            placeholder="e.g., Q3 Planning Scenarios"
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-fidelity-green focus:border-fidelity-green"
            value={newBatchName}
            onChange={e => setNewBatchName(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Execution Mode</label>
            <div className="flex rounded-md shadow-sm" role="group">
              <button
                type="button"
                onClick={() => setExecutionMode('parallel')}
                className={`flex-1 px-4 py-2 text-sm font-medium border rounded-l-lg ${
                  executionMode === 'parallel'
                    ? 'bg-fidelity-green text-white border-fidelity-green'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                Parallel
              </button>
              <button
                type="button"
                disabled
                title="Sequential mode is not yet supported"
                className="flex-1 px-4 py-2 text-sm font-medium border rounded-r-lg bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed"
              >
                Sequential
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">Parallel runs all scenarios simultaneously.</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Export Format</label>
            <div className="flex rounded-md shadow-sm" role="group">
              <button
                type="button"
                onClick={() => setExportFormat('excel')}
                className={`flex-1 px-4 py-2 text-sm font-medium border rounded-l-lg ${
                  exportFormat === 'excel'
                    ? 'bg-fidelity-green text-white border-fidelity-green'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                Excel (.xlsx)
              </button>
              <button
                type="button"
                onClick={() => setExportFormat('csv')}
                className={`flex-1 px-4 py-2 text-sm font-medium border rounded-r-lg ${
                  exportFormat === 'csv'
                    ? 'bg-fidelity-green text-white border-fidelity-green'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                CSV (.zip)
              </button>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-4">
            Select Scenarios to Run ({selectedScenarioIds.length} selected)
          </label>
          {scenarios.length === 0 ? (
            <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
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
                  onClick={() => toggleScenarioSelection(scenario.id)}
                  className={`cursor-pointer p-4 rounded-lg border-2 transition-all ${
                    selectedScenarioIds.includes(scenario.id)
                      ? 'border-fidelity-green bg-green-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-gray-900 truncate">{scenario.name}</h3>
                      {scenario.description && (
                        <p className="text-xs text-gray-500 mt-1 truncate">{scenario.description}</p>
                      )}
                      <div className="mt-2 flex items-center space-x-2">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${getStatusColor(scenario.status)}`}>
                          {scenario.status === 'not_run' ? 'Not Run' : scenario.status}
                        </span>
                        {scenario.last_run_at && (
                          <span className="text-xs text-gray-400">
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

        <div className="pt-4 border-t border-gray-100 flex justify-end">
          <button
            disabled={selectedScenarioIds.length === 0 || isSubmitting}
            onClick={handleStartBatch}
            className={`flex items-center px-6 py-3 rounded-lg font-medium shadow-md transition-colors ${
              selectedScenarioIds.length === 0 || isSubmitting
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-fidelity-green text-white hover:bg-fidelity-dark'
            }`}
          >
            {isSubmitting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
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
            <button onClick={() => setView('list')} className="text-gray-500 hover:text-gray-700 mr-4 flex items-center">
              <ArrowRight className="transform rotate-180 mr-1" size={16}/> Back
            </button>
            <div>
              <h2 className="text-xl font-bold text-gray-900">{selectedBatch.name}</h2>
              <div className="flex items-center space-x-2 text-sm text-gray-500 mt-1">
                <span>ID: {selectedBatch.id.substring(0, 8)}...</span>
                <span>•</span>
                <span>Submitted: {new Date(selectedBatch.submitted_at).toLocaleString()}</span>
                <span>•</span>
                <span>{selectedBatch.parallel ? 'Parallel' : 'Sequential'} Mode</span>
              </div>
            </div>
          </div>
          {selectedBatch.status === 'completed' && (
            <button className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">
              <FileDown size={18} className="mr-2" /> Export Results
            </button>
          )}
        </div>

        {/* Status Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-semibold text-gray-800">Execution Status</h3>
            <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${getStatusColor(selectedBatch.status)}`}>
              {getStatusIcon(selectedBatch.status)}
              {selectedBatch.status}
            </span>
          </div>

          <div className="w-full bg-gray-100 rounded-full h-3 mb-6">
            <div
              className="bg-fidelity-green h-3 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            ></div>
          </div>

          <div className="space-y-4">
            {selectedBatch.scenarios.map(scenario => (
              <div key={scenario.scenario_id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100">
                <div className="flex items-center space-x-4 w-1/3">
                  <div className={`w-2 h-12 rounded-full ${
                    scenario.status === 'completed' ? 'bg-green-500' :
                    scenario.status === 'running' ? 'bg-blue-500' :
                    scenario.status === 'failed' ? 'bg-red-500' : 'bg-gray-300'
                  }`}></div>
                  <div>
                    <p className="font-medium text-gray-900">{scenario.name}</p>
                    <p className="text-xs text-gray-500">ID: {scenario.scenario_id.substring(0, 8)}...</p>
                  </div>
                </div>

                <div className="flex-1 px-4">
                  {scenario.status === 'running' && (
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${scenario.progress}%` }}
                      ></div>
                    </div>
                  )}
                  {scenario.status === 'completed' && <span className="text-xs text-green-600 font-medium">Completed</span>}
                  {scenario.status === 'failed' && (
                    <span className="text-xs text-red-600 font-medium">
                      {scenario.error_message || 'Failed'}
                    </span>
                  )}
                  {scenario.status === 'pending' && <span className="text-xs text-gray-400">Waiting in queue...</span>}
                </div>

                <div className="w-24 text-right">
                  {scenario.status === 'running' && <span className="text-sm font-mono">{Math.round(scenario.progress)}%</span>}
                  {scenario.status === 'completed' && <CheckCircle size={20} className="ml-auto text-green-500" />}
                  {scenario.status === 'failed' && <XCircle size={20} className="ml-auto text-red-500" />}
                  {scenario.status === 'pending' && <Clock size={20} className="ml-auto text-gray-400" />}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Comparison link for completed batches */}
        {selectedBatch.status === 'completed' && selectedBatch.scenarios.length >= 2 && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <LayoutGrid size={24} className="text-blue-600 mr-3" />
                <div>
                  <h3 className="font-semibold text-blue-900">Compare Results</h3>
                  <p className="text-sm text-blue-700">View side-by-side comparison of all scenarios in this batch.</p>
                </div>
              </div>
              <button
                onClick={() => navigate(`/analytics/compare?scenarios=${selectedBatch.scenarios.map(s => s.scenario_id).join(',')}`)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
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
            <h1 className="text-2xl font-bold text-gray-900">Batch Processing</h1>
            <p className="text-gray-500 mt-1">Run multiple scenarios and compare results.</p>
          </div>
          <button
            onClick={() => setView('create')}
            className="flex items-center px-4 py-2 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark transition-colors shadow-sm"
          >
            <Plus size={20} className="mr-2" />
            Create New Batch
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
              <p className="text-sm text-gray-500">Loading batches...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
              <p className="text-sm text-red-600">{error}</p>
            </div>
          </div>
        ) : (
          <>
            {/* Active Jobs Section */}
            {runningJobs.length > 0 && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Active Executions</h3>
                {runningJobs.map((job) => (
                  <div key={job.id} className="bg-white rounded-lg border border-blue-200 shadow-sm p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h3 className="text-lg font-bold text-gray-900">{job.name}</h3>
                        <div className="flex items-center space-x-4 mt-1 text-sm text-gray-500">
                          <span>{job.scenarios.length} Scenarios</span>
                          <span>•</span>
                          <span className="text-blue-600 font-medium animate-pulse">Running...</span>
                          <span>•</span>
                          <span>{job.parallel ? 'Parallel' : 'Sequential'}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => handleViewDetails(job)}
                        className="px-4 py-2 border border-gray-300 rounded text-gray-700 hover:bg-gray-50 text-sm font-medium"
                      >
                        Monitor
                      </button>
                    </div>

                    {/* Inline Scenario Progress Summary */}
                    <div className="space-y-2 bg-gray-50 p-3 rounded-lg border border-gray-100">
                      {job.scenarios.map(s => (
                        <div key={s.scenario_id} className="flex items-center justify-between text-sm">
                          <span className="flex items-center text-gray-700">
                            {s.status === 'completed' && <CheckCircle size={14} className="text-green-500 mr-2" />}
                            {s.status === 'running' && <div className="w-2 h-2 rounded-full bg-blue-500 mr-2.5 animate-pulse"></div>}
                            {s.status === 'pending' && <div className="w-2 h-2 rounded-full bg-gray-300 mr-2.5"></div>}
                            {s.status === 'failed' && <XCircle size={14} className="text-red-500 mr-2" />}
                            {s.name}
                          </span>
                          <span className={`text-xs font-medium ${
                            s.status === 'completed' ? 'text-green-600' :
                            s.status === 'running' ? 'text-blue-600' :
                            s.status === 'failed' ? 'text-red-600' : 'text-gray-400'
                          }`}>
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
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center">
                <h3 className="font-semibold text-gray-800">Batch History</h3>

                {/* Filter Tabs */}
                <div className="flex space-x-1 bg-gray-100 p-1 rounded-lg">
                  {['all', 'running', 'completed'].map((filter) => (
                    <button
                      key={filter}
                      onClick={() => setStatusFilter(filter as any)}
                      className={`px-3 py-1 text-xs font-medium rounded-md capitalize transition-colors ${
                        statusFilter === filter
                          ? 'bg-white text-gray-900 shadow-sm'
                          : 'text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      {filter}
                    </button>
                  ))}
                </div>
              </div>

              {historyJobs.length === 0 && runningJobs.length === 0 ? (
                <div className="px-6 py-12 text-center">
                  <Layers className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-1">No batches yet</h3>
                  <p className="text-sm text-gray-500 mb-4">Create a batch to run multiple scenarios together.</p>
                  <button
                    onClick={() => setView('create')}
                    className="px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark inline-flex items-center"
                  >
                    <Plus size={16} className="mr-2" />
                    Create Batch
                  </button>
                </div>
              ) : (
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Batch Name</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Scenarios</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Submitted</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duration</th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {historyJobs.map((job) => (
                      <tr key={job.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">{job.name}</div>
                          <div className="text-xs text-gray-500">{job.id.substring(0, 8)}...</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(job.status)}`}>
                            {getStatusIcon(job.status)}
                            {job.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {job.scenarios.length}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {new Date(job.submitted_at).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                          {job.duration_seconds ? `${Math.round(job.duration_seconds)}s` : '-'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <button
                            onClick={(e) => handleRerun(job, e)}
                            className="text-gray-500 hover:text-fidelity-green mr-4"
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
