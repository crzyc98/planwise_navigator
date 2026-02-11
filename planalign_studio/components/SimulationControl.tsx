import React, { useState, useEffect } from 'react';
import { useOutletContext, useNavigate, useSearchParams } from 'react-router-dom';
import { Play, Pause, Square, Activity, Cpu, Server, Clock, Database, AlertCircle, History, CheckCircle, XCircle, CircleDot, ExternalLink, RefreshCw, Loader2 } from 'lucide-react';
import { useSimulationSocket } from '../services/websocket';
import { listScenarios, startSimulation, cancelSimulation, resetSimulation, Scenario } from '../services/api';
import { LayoutContextType } from './Layout';

export default function SimulationControl() {
  const {
    activeWorkspace,
    setLastRunScenarioId,
    isSimulationRunning,
    activeRunId,
    runningScenarioId,
    setSimulationRunning,
    clearSimulationRunning,
    lastHeartbeatRef,
  } = useOutletContext<LayoutContextType>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const scenarioIdFromUrl = searchParams.get('scenario');

  // Fetch scenarios from API
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Real WebSocket connection for telemetry
  const { telemetry, recentEvents } = useSimulationSocket(activeRunId);

  // Load scenarios when workspace changes
  useEffect(() => {
    const loadScenarios = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await listScenarios(activeWorkspace.id);
        setScenarios(data);
        // If scenario ID was passed in URL, use that; otherwise use first
        if (scenarioIdFromUrl && data.some(s => s.id === scenarioIdFromUrl)) {
          setSelectedScenarioId(scenarioIdFromUrl);
        } else if (data.length > 0) {
          setSelectedScenarioId(data[0].id);
        } else {
          setSelectedScenarioId('');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load scenarios');
        setScenarios([]);
      } finally {
        setIsLoading(false);
      }
    };

    loadScenarios();
  }, [activeWorkspace.id, scenarioIdFromUrl]);

  const handleStart = async () => {
    if (!selectedScenarioId) return;
    try {
      setError(null);
      const run = await startSimulation(selectedScenarioId);
      setSimulationRunning(run.id, selectedScenarioId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start simulation');
    }
  };

  const handleStop = async () => {
    if (!selectedScenarioId) return;
    try {
      await cancelSimulation(selectedScenarioId);
      clearSimulationRunning();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop simulation');
    }
  };

  // Detect completion and navigate to detail page
  useEffect(() => {
    if (telemetry?.current_stage === 'COMPLETED' || telemetry?.progress === 100) {
      // Give a moment to show 100% completion, then navigate to detail page
      const timer = setTimeout(() => {
        const completedScenarioId = runningScenarioId; // Use the scenario that was actually started
        clearSimulationRunning();
        // Navigate to the simulation detail page to see results
        if (completedScenarioId) {
          // Store completed scenario for Analytics page context
          setLastRunScenarioId(completedScenarioId);
          navigate(`/simulate/${completedScenarioId}`);
        }
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [telemetry?.current_stage, telemetry?.progress, runningScenarioId, navigate, setLastRunScenarioId, clearSimulationRunning]);

  // Map telemetry to legacy status format for compatibility
  const isCompleted = telemetry?.current_stage === 'COMPLETED' || telemetry?.progress === 100;
  const status = telemetry ? {
    simulation_id: telemetry.run_id,
    status: isCompleted ? 'completed' as const : 'running' as const,
    current_year: telemetry.current_year,
    total_years: telemetry.total_years,
    current_stage: telemetry.current_stage as any,
    progress_percent: telemetry.progress,
    elapsed_seconds: telemetry.performance_metrics.elapsed_seconds,
    events_generated: telemetry.performance_metrics.events_generated,
    performance_metrics: {
      events_per_second: telemetry.performance_metrics.events_per_second,
      memory_usage_mb: telemetry.performance_metrics.memory_mb,
      memory_pressure: telemetry.performance_metrics.memory_pressure,
      cpu_percent: 0, // Not provided by backend yet
    },
  } : null;

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const getPressureColor = (pressure: string) => {
    switch (pressure) {
      case 'low': return 'text-green-600 bg-green-50 border-green-200';
      case 'moderate': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      case 'high': return 'text-orange-600 bg-orange-50 border-orange-200';
      case 'critical': return 'text-red-600 bg-red-50 border-red-200';
      default: return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  // Reload scenarios after simulation completes
  useEffect(() => {
    if (!activeRunId && scenarios.length > 0) {
      // Refresh scenarios to get updated status
      listScenarios(activeWorkspace.id).then(setScenarios).catch(console.error);
    }
  }, [activeRunId, activeWorkspace.id]);

  // Feature 045: Update heartbeat timestamp when telemetry is received
  useEffect(() => {
    if (telemetry && isSimulationRunning) {
      lastHeartbeatRef.current = Date.now();
    }
  }, [telemetry, isSimulationRunning, lastHeartbeatRef]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

      {/* Left Column: Controls & Progress */}
      <div className="lg:col-span-2 space-y-6 flex flex-col">

        {/* Status Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
               <h2 className="text-xl font-bold text-gray-900">Simulation Control Center</h2>
               <p className="text-sm text-gray-500">Workspace: <span className="font-semibold text-gray-700">{activeWorkspace.name}</span></p>
            </div>
            {!activeRunId ? (
              <button
                onClick={handleStart}
                disabled={!selectedScenarioId || isLoading || isSimulationRunning}
                className={`flex items-center px-6 py-2 text-white rounded-lg transition-all shadow-md font-medium ${
                  !selectedScenarioId || isLoading || isSimulationRunning
                    ? 'bg-gray-300 cursor-not-allowed'
                    : 'bg-fidelity-green hover:bg-fidelity-dark'
                }`}
              >
                {isSimulationRunning ? (
                  <>
                    <Loader2 size={20} className="mr-2 animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <Play size={20} className="mr-2" />
                    Start Simulation
                  </>
                )}
              </button>
            ) : (
              <div className="flex space-x-2">
                 <button className="flex items-center px-4 py-2 bg-yellow-100 text-yellow-700 rounded-lg hover:bg-yellow-200 font-medium">
                   <Pause size={18} className="mr-2" /> Pause
                 </button>
                 <button
                   onClick={handleStop}
                   className="flex items-center px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 font-medium"
                 >
                   <Square size={18} className="mr-2" /> Stop
                 </button>
              </div>
            )}
          </div>

          {!activeRunId ? (
            <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
              <label className="block text-sm font-medium text-gray-700 mb-2">Select Scenario to Run</label>
              {error && (
                <div className="flex items-center text-red-600 text-sm p-2 bg-red-50 rounded mb-2">
                  <AlertCircle size={16} className="mr-2" />
                  {error}
                </div>
              )}
              {isLoading ? (
                <div className="text-gray-500 text-sm p-2">Loading scenarios...</div>
              ) : scenarios.length > 0 ? (
                <select
                  value={selectedScenarioId}
                  onChange={(e) => setSelectedScenarioId(e.target.value)}
                  className="block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-fidelity-green focus:border-fidelity-green"
                >
                  {scenarios.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              ) : (
                <div className="flex items-center text-yellow-600 text-sm p-2 bg-yellow-50 rounded">
                  <AlertCircle size={16} className="mr-2" />
                  No scenarios found in this workspace. Please create one in Configuration.
                </div>
              )}
            </div>
          ) : (
             <div className="space-y-6">
               {/* Main Progress Bar */}
               <div>
                 <div className="flex justify-between text-sm font-medium text-gray-700 mb-2">
                   <span>Overall Progress (Year {status?.current_year})</span>
                   <span>{status ? Math.round(status.progress_percent) : 0}%</span>
                 </div>
                 <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                   <div
                     className="bg-fidelity-green h-4 rounded-full transition-all duration-500 ease-out"
                     style={{ width: `${status?.progress_percent}%` }}
                   ></div>
                 </div>
               </div>

               {/* Stage Indicators */}
               <div className="grid grid-cols-6 gap-2">
                 {['INIT', 'FOUNDATION', 'EVENT GEN', 'STATE ACC', 'VALIDATION', 'REPORTING'].map((stage, idx) => {
                    const stages = ['INITIALIZATION', 'FOUNDATION', 'EVENT_GENERATION', 'STATE_ACCUMULATION', 'VALIDATION', 'REPORTING'];
                    const currentIdx = stages.indexOf(status?.current_stage || '');
                    let colorClass = 'bg-gray-100 text-gray-400';
                    if (status?.status === 'completed') colorClass = 'bg-green-100 text-green-700 border-green-200';
                    else if (idx < currentIdx) colorClass = 'bg-green-100 text-green-700 border-green-200';
                    else if (idx === currentIdx) colorClass = 'bg-blue-100 text-blue-700 border-blue-200 ring-2 ring-blue-400';

                    return (
                      <div key={stage} className={`text-center py-2 rounded border text-xs font-bold ${colorClass}`}>
                        {stage}
                      </div>
                    );
                 })}
               </div>
             </div>
          )}
        </div>

        {/* Real-time Metrics Charts (Mock) */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex-1">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Performance Telemetry</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
             <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="flex items-center mb-1">
                  <Activity className="text-blue-500 mr-2" size={16} />
                  <p className="text-xs text-gray-500">Throughput</p>
                </div>
                <p className="text-lg font-bold text-gray-900">{(status?.performance_metrics.events_per_second || 0).toFixed(1)}</p>
                <p className="text-[10px] text-gray-400">events/sec</p>
             </div>

             <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="flex items-center mb-1">
                  <Server className="text-purple-500 mr-2" size={16} />
                  <p className="text-xs text-gray-500">Memory</p>
                </div>
                <p className="text-lg font-bold text-gray-900">{Math.round(status?.performance_metrics.memory_usage_mb || 0)}</p>
                <p className="text-[10px] text-gray-400">MB Used</p>
             </div>

             <div className={`p-3 rounded-lg border ${getPressureColor(status?.performance_metrics.memory_pressure || 'low')}`}>
                <div className="flex items-center mb-1">
                  <Cpu className="mr-2" size={16} />
                  <p className="text-xs opacity-75">Pressure</p>
                </div>
                <p className="text-lg font-bold uppercase">{status?.performance_metrics.memory_pressure || 'LOW'}</p>
                <p className="text-[10px] opacity-75">System Load</p>
             </div>

             <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="flex items-center mb-1">
                  <Clock className="text-orange-500 mr-2" size={16} />
                  <p className="text-xs text-gray-500">Elapsed</p>
                </div>
                <p className="text-lg font-bold text-gray-900">{formatTime(status?.elapsed_seconds || 0)}</p>
                <p className="text-[10px] text-gray-400">mm:ss</p>
             </div>
          </div>
          {/* Placeholder for a line chart */}
          <div className="h-40 bg-gray-50 rounded-lg border border-gray-200 flex items-center justify-center text-gray-400 text-sm">
             [Real-time Performance Graph Placeholder]
          </div>
        </div>
      </div>

      {/* Right Column: Event Log */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col overflow-hidden max-h-[600px]">
         <div className="p-4 border-b border-gray-200 bg-gray-50 flex justify-between items-center">
            <h3 className="font-semibold text-gray-800 flex items-center">
              <Database size={16} className="mr-2 text-gray-500" />
              Event Stream
            </h3>
            <span className="bg-gray-200 text-gray-600 px-2 py-0.5 rounded text-xs">
              Live
            </span>
         </div>
         <div className="flex-1 overflow-y-auto p-0 font-mono text-sm bg-gray-900 text-gray-300">
            {recentEvents.length === 0 ? (
               <div className="p-4 text-gray-500 italic">Waiting for simulation to start...</div>
            ) : (
               <ul className="divide-y divide-gray-800">
                 {recentEvents.map((event, idx) => (
                   <li key={event.employee_id + '-' + idx} className="p-3 hover:bg-gray-800 transition-colors border-l-4 border-transparent hover:border-fidelity-green">
                     <div className="flex justify-between items-start mb-1">
                        <span className={`text-xs font-bold px-1.5 rounded ${
                          event.event_type === 'HIRE' ? 'bg-green-900 text-green-300' :
                          event.event_type === 'TERMINATION' ? 'bg-red-900 text-red-300' :
                          event.event_type === 'PROMOTION' ? 'bg-blue-900 text-blue-300' :
                          event.event_type === 'STAGE' ? 'bg-purple-900 text-purple-300' :
                          event.event_type === 'INFO' ? 'bg-cyan-900 text-cyan-300' :
                          'bg-yellow-900 text-yellow-300'
                        }`}>
                          {event.event_type}
                        </span>
                        <span className="text-xs text-gray-500">{new Date(event.timestamp).toLocaleTimeString()}</span>
                     </div>
                     <p className="text-gray-400 text-xs">{event.details || event.employee_id}</p>
                   </li>
                 ))}
               </ul>
            )}
         </div>
      </div>

      {/* Bottom Row: Simulation History */}
      <div className="lg:col-span-3 bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800 flex items-center">
            <History size={20} className="mr-2 text-gray-500" />
            Simulation History
          </h3>
          <span className="text-sm text-gray-500">{scenarios.length} scenario(s)</span>
        </div>

        {scenarios.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <History size={48} className="mx-auto mb-3 opacity-30" />
            <p>No scenarios found. Create one in Configuration.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-600">Scenario</th>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-600">Status</th>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-600">Last Run</th>
                  <th className="text-left py-3 px-4 text-sm font-semibold text-gray-600">Run ID</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((scenario) => (
                  <tr
                    key={scenario.id}
                    className="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer group"
                    onClick={() => navigate(`/simulate/${scenario.id}`)}
                  >
                    <td className="py-3 px-4">
                      <div className="flex items-center">
                        <div className="flex-1">
                          <p className="font-medium text-gray-900 group-hover:text-fidelity-green transition-colors">
                            {scenario.name}
                          </p>
                          {scenario.description && (
                            <p className="text-xs text-gray-500 mt-0.5">{scenario.description}</p>
                          )}
                        </div>
                        <ExternalLink size={14} className="text-gray-300 group-hover:text-fidelity-green ml-2 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                        scenario.status === 'completed' ? 'bg-green-100 text-green-700' :
                        scenario.status === 'running' ? 'bg-blue-100 text-blue-700' :
                        scenario.status === 'failed' ? 'bg-red-100 text-red-700' :
                        scenario.status === 'queued' ? 'bg-yellow-100 text-yellow-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>
                        {scenario.status === 'completed' && <CheckCircle size={12} className="mr-1" />}
                        {scenario.status === 'running' && <CircleDot size={12} className="mr-1 animate-pulse" />}
                        {scenario.status === 'failed' && <XCircle size={12} className="mr-1" />}
                        {scenario.status.replace('_', ' ').toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600">
                      {scenario.last_run_at ? (
                        <span title={new Date(scenario.last_run_at).toLocaleString()}>
                          {new Date(scenario.last_run_at).toLocaleDateString()} {new Date(scenario.last_run_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      ) : (
                        <span className="text-gray-400 italic">Never</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {scenario.last_run_id ? (
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded font-mono text-gray-600">
                          {scenario.last_run_id.slice(0, 8)}...
                        </code>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      {/* Show Force Reset if stuck (running but not in our active tracking) */}
                      {scenario.status === 'running' && scenario.id !== runningScenarioId && (
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (!confirm('Force reset this stuck simulation? This marks it as failed.')) return;
                            try {
                              setError(null);
                              await resetSimulation(scenario.id);
                              const data = await listScenarios(activeWorkspace.id);
                              setScenarios(data);
                            } catch (err) {
                              setError(err instanceof Error ? err.message : 'Failed to reset simulation');
                            }
                          }}
                          className="text-sm px-3 py-1.5 rounded font-medium bg-orange-100 text-orange-700 hover:bg-orange-200"
                        >
                          <RefreshCw size={14} className="inline mr-1" />
                          Force Reset
                        </button>
                      )}
                      {/* Run button (disabled when any simulation is running) */}
                      <button
                        onClick={async (e) => {
                          e.stopPropagation(); // Prevent row click
                          try {
                            setError(null);
                            const run = await startSimulation(scenario.id);
                            setSelectedScenarioId(scenario.id);
                            setSimulationRunning(run.id, scenario.id);
                            window.scrollTo({ top: 0, behavior: 'smooth' });
                          } catch (err) {
                            setError(err instanceof Error ? err.message : 'Failed to start simulation');
                          }
                        }}
                        disabled={isSimulationRunning}
                        className={`text-sm px-3 py-1.5 rounded font-medium transition-colors ${
                          isSimulationRunning
                            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                            : 'bg-fidelity-green text-white hover:bg-fidelity-dark'
                        }`}
                      >
                        {isSimulationRunning && scenario.id === runningScenarioId ? (
                          <>
                            <Loader2 size={14} className="inline mr-1 animate-spin" />
                            Running...
                          </>
                        ) : isSimulationRunning ? 'Busy' : 'Run'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
