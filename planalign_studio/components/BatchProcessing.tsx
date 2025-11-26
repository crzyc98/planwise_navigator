import React, { useState, useEffect } from 'react';
import {
  Plus, Database, Play, FileDown, CheckCircle,
  Clock, AlertCircle, Trash2, ArrowRight, LayoutGrid, RotateCw
} from 'lucide-react';
import { MOCK_BATCH_JOBS, MOCK_CONFIGS, COMPARISON_DATA } from '../constants';
import { BatchJob, ComparisonMetric } from '../types';

export default function BatchProcessing() {
  const [view, setView] = useState<'list' | 'create' | 'details'>('list');
  const [selectedBatch, setSelectedBatch] = useState<BatchJob | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'running' | 'completed'>('all');

  // Creation State
  const [newBatchName, setNewBatchName] = useState('');
  const [selectedConfigIds, setSelectedConfigIds] = useState<string[]>([]);
  const [executionMode, setExecutionMode] = useState<'parallel' | 'sequential'>('parallel');
  const [exportFormat, setExportFormat] = useState<'excel' | 'csv'>('excel');

  // Mock Real-time Update for Demo
  const [activeJob, setActiveJob] = useState<BatchJob | null>(null);

  useEffect(() => {
    if (activeJob && activeJob.status === 'running') {
      const interval = setInterval(() => {
        setActiveJob(prev => {
          if (!prev) return null;
          // Deep clone to update nested scenario progress
          const updated = { ...prev };
          let allComplete = true;

          updated.scenarios = updated.scenarios.map(s => {
            if (s.status === 'completed') return s;

            if (s.status === 'queued') {
               // simple logic to start queued items if others are somewhat done
               if (Math.random() > 0.7) return { ...s, status: 'running', progress: 5 };
               return s;
            }

            if (s.status === 'running') {
              const newProgress = Math.min(s.progress + Math.random() * 10, 100);
              if (newProgress >= 100) {
                return { ...s, status: 'completed', progress: 100 };
              }
              allComplete = false;
              return { ...s, progress: newProgress };
            }
            return s;
          });

          if (allComplete) {
            updated.status = 'completed';
            updated.duration = '2m 15s'; // Mock duration
          }

          return updated;
        });
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [activeJob?.status]);

  const handleStartBatch = () => {
    const newJob: BatchJob = {
      id: `batch_${Math.random().toString(36).substr(2, 5)}`,
      name: newBatchName || 'Untitled Batch',
      status: 'running',
      submittedAt: new Date().toLocaleString(),
      duration: '-',
      executionMode,
      exportFormat,
      scenarios: selectedConfigIds.map(id => {
        const cfg = MOCK_CONFIGS.find(c => c.id === id);
        return {
          scenario_id: `sc_${Math.random().toString(36).substr(2, 5)}`,
          config_id: id,
          name: cfg?.name || 'Unknown',
          status: 'queued',
          progress: 0
        };
      })
    };

    // Start first one immediately
    if (newJob.scenarios.length > 0) {
      newJob.scenarios[0].status = 'running';
    }

    setActiveJob(newJob);
    setView('details');
  };

  const handleRerun = (job: BatchJob, e: React.MouseEvent) => {
    e.stopPropagation();
    setNewBatchName(`${job.name} (Rerun)`);
    setSelectedConfigIds(job.scenarios.map(s => s.config_id));
    setExecutionMode(job.executionMode || 'parallel');
    setExportFormat(job.exportFormat || 'excel');
    setView('create');
  };

  const handleViewDetails = (job: BatchJob) => {
    // If it's the one we are "simulating", use the active state, else use the static mock
    if (activeJob && job.id === activeJob.id) {
       setSelectedBatch(activeJob);
    } else {
       setSelectedBatch(job);
    }
    setView('details');
  };

  const toggleConfigSelection = (id: string) => {
    setSelectedConfigIds(prev =>
      prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]
    );
  };

  // Filter logic
  const getFilteredJobs = () => {
    let jobs = MOCK_BATCH_JOBS;
    // Include active job in the list if it's running/active
    if (activeJob && !MOCK_BATCH_JOBS.find(j => j.id === activeJob.id)) {
      jobs = [activeJob, ...MOCK_BATCH_JOBS];
    }

    if (statusFilter === 'all') return jobs;
    return jobs.filter(j => j.status === statusFilter);
  };

  // RENDERERS

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
                    onClick={() => setExecutionMode('sequential')}
                    className={`flex-1 px-4 py-2 text-sm font-medium border rounded-r-lg ${
                      executionMode === 'sequential'
                        ? 'bg-fidelity-green text-white border-fidelity-green'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    Sequential
                  </button>
               </div>
               <p className="text-xs text-gray-500 mt-1">Parallel runs all scenarios simultaneously (Higher load).</p>
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
          <label className="block text-sm font-medium text-gray-700 mb-4">Select Configurations to Run</label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {MOCK_CONFIGS.map(config => (
              <div
                key={config.id}
                onClick={() => toggleConfigSelection(config.id)}
                className={`cursor-pointer p-4 rounded-lg border-2 transition-all ${
                  selectedConfigIds.includes(config.id)
                    ? 'border-fidelity-green bg-green-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-gray-900">{config.name}</h3>
                    <p className="text-xs text-gray-500 mt-1">{config.description}</p>
                    <div className="mt-2 text-xs text-gray-600 bg-white inline-block px-2 py-1 rounded border border-gray-200">
                      {config.startYear}-{config.endYear} • Target: {config.growthTarget}%
                    </div>
                  </div>
                  {selectedConfigIds.includes(config.id) && (
                    <CheckCircle className="text-fidelity-green" size={20} />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="pt-4 border-t border-gray-100 flex justify-end">
          <button
            disabled={selectedConfigIds.length === 0}
            onClick={handleStartBatch}
            className={`flex items-center px-6 py-3 rounded-lg font-medium shadow-md transition-colors ${
              selectedConfigIds.length === 0
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-fidelity-green text-white hover:bg-fidelity-dark'
            }`}
          >
            <Play size={18} className="mr-2" />
            Launch Batch Execution
          </button>
        </div>
      </div>
    </div>
  );

  const renderDetailsView = () => {
    // Determine which job to show. If it's the active simulation, show that state.
    const jobToShow = (activeJob && selectedBatch?.id === activeJob.id) ? activeJob : selectedBatch;

    if (!jobToShow) return <div>Job not found</div>;

    const completedCount = jobToShow.scenarios.filter(s => s.status === 'completed').length;
    const progress = Math.round((completedCount / jobToShow.scenarios.length) * 100);

    return (
      <div className="space-y-6 animate-fadeIn">
        <div className="flex items-center justify-between">
           <div className="flex items-center">
              <button onClick={() => setView('list')} className="text-gray-500 hover:text-gray-700 mr-4 flex items-center">
                <ArrowRight className="transform rotate-180 mr-1" size={16}/> Back
              </button>
              <div>
                <h2 className="text-xl font-bold text-gray-900">{jobToShow.name}</h2>
                <div className="flex items-center space-x-2 text-sm text-gray-500 mt-1">
                   <span>ID: {jobToShow.id}</span>
                   <span>•</span>
                   <span>Submitted: {jobToShow.submittedAt}</span>
                   <span>•</span>
                   <span className="capitalize">{jobToShow.executionMode || 'Parallel'} Mode</span>
                </div>
              </div>
           </div>
           {jobToShow.status === 'completed' && (
             <button className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">
               <FileDown size={18} className="mr-2" /> Export Results
             </button>
           )}
        </div>

        {/* Status Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
           <div className="flex justify-between items-center mb-4">
              <h3 className="font-semibold text-gray-800">Execution Status</h3>
              <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${
                jobToShow.status === 'completed' ? 'bg-green-100 text-green-800' :
                jobToShow.status === 'running' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-600'
              }`}>
                {jobToShow.status}
              </span>
           </div>

           <div className="w-full bg-gray-100 rounded-full h-3 mb-6">
              <div
                className="bg-fidelity-green h-3 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              ></div>
           </div>

           <div className="space-y-4">
             {jobToShow.scenarios.map(scenario => (
               <div key={scenario.scenario_id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100">
                  <div className="flex items-center space-x-4 w-1/3">
                     <div className={`w-2 h-12 rounded-full ${
                        scenario.status === 'completed' ? 'bg-green-500' :
                        scenario.status === 'running' ? 'bg-blue-500' : 'bg-gray-300'
                     }`}></div>
                     <div>
                       <p className="font-medium text-gray-900">{scenario.name}</p>
                       <p className="text-xs text-gray-500">Config: {scenario.config_id}</p>
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
                     {scenario.status === 'completed' && <span className="text-xs text-green-600 font-medium">Processing Complete</span>}
                     {scenario.status === 'queued' && <span className="text-xs text-gray-400">Waiting in queue...</span>}
                  </div>

                  <div className="w-24 text-right">
                     {scenario.status === 'running' && <span className="text-sm font-mono">{Math.round(scenario.progress)}%</span>}
                     {scenario.status === 'completed' && <CheckCircle size={20} className="ml-auto text-green-500" />}
                     {scenario.status === 'queued' && <Clock size={20} className="ml-auto text-gray-400" />}
                  </div>
               </div>
             ))}
           </div>
        </div>

        {/* Comparison Matrix (Only if completed) */}
        {jobToShow.status === 'completed' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
             <div className="px-6 py-4 border-b border-gray-200 bg-gray-50 flex justify-between items-center">
                <h3 className="font-semibold text-gray-800 flex items-center">
                  <LayoutGrid size={18} className="mr-2" />
                  Scenario Comparison Matrix
                </h3>
             </div>
             <div className="overflow-x-auto">
               <table className="min-w-full divide-y divide-gray-200">
                 <thead className="bg-gray-50">
                   <tr>
                     <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Metric</th>
                     <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Unit</th>
                     {/* Dynamic Columns based on scenarios in the job */}
                     {jobToShow.scenarios.map(s => (
                       <th key={s.scenario_id} className="px-6 py-3 text-left text-xs font-medium text-gray-900 uppercase tracking-wider bg-gray-100">
                         {s.name}
                       </th>
                     ))}
                   </tr>
                 </thead>
                 <tbody className="bg-white divide-y divide-gray-200">
                   {COMPARISON_DATA.map((row, idx) => (
                     <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                       <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{row.metric}</td>
                       <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{row.unit}</td>
                       {jobToShow.scenarios.map(s => {
                         // Fallback logic to map scenario name to mock data keys
                         // In real app, this data comes from the backend keyed by ID
                         const val = row[s.name];
                         return (
                           <td key={s.scenario_id} className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                             {val !== undefined ? val : '-'}
                           </td>
                         )
                       })}
                     </tr>
                   ))}
                 </tbody>
               </table>
             </div>
          </div>
        )}
      </div>
    );
  };

  const renderListView = () => {
    const jobs = getFilteredJobs();
    const runningJobs = jobs.filter(j => j.status === 'running');
    const historyJobs = jobs.filter(j => j.status !== 'running');

    return (
      <div className="space-y-6 animate-fadeIn">
        <div className="flex justify-between items-center">
          <div>
             <h1 className="text-2xl font-bold text-gray-900">Batch Processing</h1>
             <p className="text-gray-500 mt-1">Manage parallel simulations and comparison sets.</p>
          </div>
          <button
            onClick={() => setView('create')}
            className="flex items-center px-4 py-2 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark transition-colors shadow-sm"
          >
            <Plus size={20} className="mr-2" />
            Create New Batch
          </button>
        </div>

        {/* Active Jobs Section */}
        {(activeJob || runningJobs.length > 0) && (
          <div className="space-y-4">
             <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Active Execution</h3>
             {[activeJob, ...runningJobs].filter((v,i,a) => v && a.indexOf(v) === i).map((job) => (
               job && (
                <div key={job.id} className="bg-white rounded-lg border border-blue-200 shadow-sm p-6">
                  <div className="flex items-center justify-between mb-4">
                     <div>
                        <h3 className="text-lg font-bold text-gray-900">{job.name}</h3>
                        <div className="flex items-center space-x-4 mt-1 text-sm text-gray-500">
                           <span>{job.scenarios.length} Scenarios</span>
                           <span>•</span>
                           <span className="text-blue-600 font-medium animate-pulse">Running...</span>
                           <span>•</span>
                           <span className="capitalize">{job.executionMode || 'Parallel'}</span>
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
                             {s.status === 'queued' && <div className="w-2 h-2 rounded-full bg-gray-300 mr-2.5"></div>}
                             {s.name}
                          </span>
                          <span className={`text-xs font-medium ${
                             s.status === 'completed' ? 'text-green-600' :
                             s.status === 'running' ? 'text-blue-600' : 'text-gray-400'
                          }`}>
                             {s.status === 'completed' ? 'Completed' :
                              s.status === 'running' ? `Running (${Math.round(s.progress)}%)` : 'Pending'}
                          </span>
                       </div>
                     ))}
                  </div>
                </div>
               )
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
                    <div className="text-xs text-gray-500">{job.id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                     <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                       job.status === 'completed' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                     }`}>
                       {job.status}
                     </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                     {job.scenarios.length}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                     {job.submittedAt}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                     {job.duration || '-'}
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
                      View Report
                    </button>
                    <button className="text-gray-400 hover:text-red-500">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {historyJobs.length === 0 && (
                <tr>
                   <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">
                      No batches found.
                   </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
