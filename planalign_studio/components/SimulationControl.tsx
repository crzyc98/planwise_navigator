import React, { useState, useEffect } from 'react';
import { useOutletContext, useNavigate, useSearchParams } from 'react-router-dom';
import { Play, Square, Activity, Cpu, Server, Clock, AlertCircle, History, CheckCircle, XCircle, CircleDot, ExternalLink, RefreshCw, Loader2, BarChart3 } from 'lucide-react';
import { useRunTelemetry } from '../services/websocket';
import { listScenarios, startSimulation, cancelSimulation, resetSimulation, Scenario } from '../services/api';
import { LayoutContextType } from './Layout';
import LiveStatsPanel from './simulation/LiveStatsPanel';
import ActivityFeed from './simulation/ActivityFeed';
import PerformanceTrendChart from './simulation/PerformanceTrendChart';
import ConnectionStatusBadge from './simulation/ConnectionStatusBadge';

const STAGE_LABELS = ['INIT', 'FOUNDATION', 'EVENT GEN', 'STATE ACC', 'VALIDATION', 'REPORTING'];
const STAGE_NAMES = ['INITIALIZATION', 'FOUNDATION', 'EVENT_GENERATION', 'STATE_ACCUMULATION', 'VALIDATION', 'REPORTING'];

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

  // Feature 094: reliable run telemetry (snapshot resync, polling fallback)
  const { connectionState, snapshot, secondsSinceUpdate } = useRunTelemetry(
    activeRunId,
    runningScenarioId
  );

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
    if (!runningScenarioId) return;
    try {
      await cancelSimulation(runningScenarioId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop simulation');
    }
  };

  // Terminal-state handling driven by authoritative run status (FR-010/FR-015)
  const terminalStatus =
    snapshot && ['completed', 'failed', 'cancelled'].includes(snapshot.status)
      ? snapshot.status
      : null;

  useEffect(() => {
    if (!terminalStatus || !activeRunId) return;
    // Show the final state briefly, then release the run slot
    const timer = setTimeout(() => {
      const finishedScenarioId = runningScenarioId;
      clearSimulationRunning();
      if (!finishedScenarioId) return;
      if (terminalStatus === 'completed') {
        setLastRunScenarioId(finishedScenarioId);
        navigate(`/simulate/${finishedScenarioId}`);
      } else if (terminalStatus === 'failed') {
        // Detail page shows the failure banner and the run's simulation.log
        navigate(`/simulate/${finishedScenarioId}`);
      }
    }, 2000);
    return () => clearTimeout(timer);
  }, [terminalStatus, activeRunId, runningScenarioId, navigate, setLastRunScenarioId, clearSimulationRunning]);

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
    if (snapshot && isSimulationRunning) {
      lastHeartbeatRef.current = Date.now();
    }
  }, [snapshot, isSimulationRunning, lastHeartbeatRef]);

  const lastRunScenario = scenarios.find(s => s.last_run_at) ?
    [...scenarios].sort((a, b) =>
      new Date(b.last_run_at ?? 0).getTime() - new Date(a.last_run_at ?? 0).getTime()
    )[0] : null;

  const metrics = snapshot?.performance_metrics;

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
            <div className="flex items-center space-x-3">
              {activeRunId && (
                <ConnectionStatusBadge state={connectionState} secondsSinceUpdate={secondsSinceUpdate} />
              )}
              {!activeRunId ? (
                <button
                  onClick={handleStart}
                  disabled={!selectedScenarioId || isLoading || isSimulationRunning}
                  className={`flex items-center px-6 py-2 text-white rounded-lg transition-all shadow-md font-medium ${!selectedScenarioId || isLoading || isSimulationRunning ? 'bg-gray-300 cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'}`}
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
                <button
                  onClick={handleStop}
                  disabled={!!terminalStatus}
                  className="flex items-center px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 font-medium disabled:opacity-50"
                >
                  <Square size={18} className="mr-2" /> Stop
                </button>
              )}
            </div>
          </div>

          {!activeRunId ? (
            <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
              <label htmlFor="sim-scenario-select" className="block text-sm font-medium text-gray-700 mb-2">Select Scenario to Run</label>
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
                  id="sim-scenario-select"
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
                   <span>
                     {terminalStatus
                       ? `Run ${terminalStatus.toUpperCase()}`
                       : `Overall Progress (Year ${snapshot?.current_year ?? '…'})`}
                   </span>
                   <span>{snapshot ? Math.round(snapshot.progress) : 0}%</span>
                 </div>
                 <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
                   <div
                     className={`h-4 rounded-full transition-all duration-500 ease-out ${terminalStatus === 'failed' ? 'bg-red-500' : terminalStatus === 'cancelled' ? 'bg-gray-400' : 'bg-fidelity-green'}`}
                     style={{ width: `${snapshot?.progress ?? 0}%` }}
                   ></div>
                 </div>
               </div>

               {/* Stage Indicators */}
               <div className="grid grid-cols-6 gap-2">
                 {STAGE_LABELS.map((stage, idx) => {
                    const currentIdx = STAGE_NAMES.indexOf(snapshot?.current_stage || '');
                    let colorClass = 'bg-gray-100 text-gray-400';
                    if (snapshot?.status === 'completed') colorClass = 'bg-green-100 text-green-700 border-green-200';
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

        {/* Live Run Dashboard (feature 094) */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex-1">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Live Run Dashboard</h3>

          {activeRunId && snapshot ? (
            <div className="space-y-6">
              {/* Event statistics + per-year progress */}
              <LiveStatsPanel snapshot={snapshot} />

              {/* Performance tiles */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                 <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                    <div className="flex items-center mb-1">
                      <Activity className="text-blue-500 mr-2" size={16} />
                      <p className="text-xs text-gray-500">Throughput</p>
                    </div>
                    <p className="text-lg font-bold text-gray-900">{(metrics?.events_per_second || 0).toFixed(1)}</p>
                    <p className="text-[10px] text-gray-400">events/sec</p>
                 </div>

                 <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                    <div className="flex items-center mb-1">
                      <Server className="text-purple-500 mr-2" size={16} />
                      <p className="text-xs text-gray-500">Memory</p>
                    </div>
                    <p className="text-lg font-bold text-gray-900">{Math.round(metrics?.memory_mb || 0)}</p>
                    <p className="text-[10px] text-gray-400">MB Used</p>
                 </div>

                 <div className={`p-3 rounded-lg border ${getPressureColor(metrics?.memory_pressure || 'low')}`}>
                    <div className="flex items-center mb-1">
                      <Cpu className="mr-2" size={16} />
                      <p className="text-xs opacity-75">Pressure</p>
                    </div>
                    <p className="text-lg font-bold uppercase">{metrics?.memory_pressure || 'LOW'}</p>
                    <p className="text-[10px] opacity-75">System Load</p>
                 </div>

                 <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                    <div className="flex items-center mb-1">
                      <Clock className="text-orange-500 mr-2" size={16} />
                      <p className="text-xs text-gray-500">Elapsed</p>
                    </div>
                    <p className="text-lg font-bold text-gray-900">{formatTime(metrics?.elapsed_seconds || 0)}</p>
                    <p className="text-[10px] text-gray-400">mm:ss</p>
                 </div>
              </div>

              {/* Performance trend (replaces the old placeholder) */}
              <PerformanceTrendChart samples={snapshot.performance_samples} />
            </div>
          ) : (
            /* Idle state (FR-007): meaningful summary instead of placeholders */
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <BarChart3 size={40} className="text-gray-300 mb-3" />
              {lastRunScenario ? (
                <>
                  <p className="text-gray-600 font-medium">
                    Last run: <span className="text-gray-900">{lastRunScenario.name}</span>
                    {' — '}
                    <span className={lastRunScenario.status === 'completed' ? 'text-fidelity-green' : 'text-red-600'}>
                      {lastRunScenario.status.toUpperCase()}
                    </span>
                  </p>
                  <p className="text-sm text-gray-400 mt-1">
                    {lastRunScenario.last_run_at ? new Date(lastRunScenario.last_run_at).toLocaleString() : ''}
                  </p>
                  <button
                    onClick={() => navigate(`/simulate/${lastRunScenario.id}`)}
                    className="mt-4 text-sm text-fidelity-green hover:text-fidelity-dark font-medium"
                  >
                    View results →
                  </button>
                </>
              ) : (
                <p className="text-gray-500">
                  Start a simulation to see live event counts, per-year progress, and performance trends here.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right Column: Run Activity feed (replaces raw event stream — FR-003) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col overflow-hidden max-h-[600px]">
        <ActivityFeed milestones={snapshot?.milestones ?? []} />
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
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${({ completed: 'bg-green-100 text-green-700', running: 'bg-blue-100 text-blue-700', failed: 'bg-red-100 text-red-700', queued: 'bg-yellow-100 text-yellow-700' } as Record<string, string>)[scenario.status] ?? 'bg-gray-100 text-gray-600'}`}>
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
                        className={`text-sm px-3 py-1.5 rounded font-medium transition-colors ${isSimulationRunning ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-fidelity-green text-white hover:bg-fidelity-dark'}`}
                      >
                        {isSimulationRunning && scenario.id === runningScenarioId && (
                          <>
                            <Loader2 size={14} className="inline mr-1 animate-spin" />
                            Running...
                          </>
                        )}
                        {isSimulationRunning && scenario.id !== runningScenarioId && 'Busy'}
                        {!isSimulationRunning && 'Run'}
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
