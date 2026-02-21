import React, { useState, useRef, useEffect, useCallback } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, PlayCircle, BarChart3, Settings, Database,
  Activity, Bell, ChevronDown, Check, Search, Briefcase,
  X, Info, AlertTriangle, AlertCircle, CheckCircle, Moon, Sun, HelpCircle,
  Plus, Loader2, Layers, PieChart, Scale, Shield, Menu, PanelLeftClose, PanelLeftOpen
} from 'lucide-react';
import { APP_NAME, MOCK_NOTIFICATIONS, APP_VERSION } from '../constants';
import { Workspace, Notification } from '../types';
import {
  listWorkspaces,
  createWorkspace as apiCreateWorkspace,
  updateWorkspace as apiUpdateWorkspace,
  deleteWorkspace as apiDeleteWorkspace,
  getActiveSimulations,
  Workspace as ApiWorkspace,
} from '../services/api';

export interface LayoutContextType {
  activeWorkspace: Workspace;
  setActiveWorkspace: (ws: Workspace) => void;
  workspaces: Workspace[];
  addWorkspace: (ws: Workspace) => void;
  updateWorkspace: (id: string, updates: Partial<Workspace>) => void;
  deleteWorkspace: (id: string) => void;
  lastRunScenarioId: string | null;
  setLastRunScenarioId: (id: string | null) => void;
  // Feature 045: Global simulation running state
  isSimulationRunning: boolean;
  activeRunId: string | null;
  runningScenarioId: string | null;
  setSimulationRunning: (runId: string, scenarioId: string) => void;
  clearSimulationRunning: () => void;
  lastHeartbeatRef: React.MutableRefObject<number>;
}

const NavItem = ({ to, icon, label, end, collapsed }: { to: string; icon: React.ReactNode; label: string; end?: boolean; collapsed?: boolean }) => (
  <NavLink
    to={to}
    end={end}
    title={collapsed ? label : undefined}
    className={({ isActive }) =>
      `flex items-center ${collapsed ? 'justify-center px-2' : 'px-4'} py-3 text-sm font-medium transition-colors rounded-lg mb-1 ${
        isActive
          ? 'bg-fidelity-green text-white shadow-md'
          : 'text-gray-600 hover:bg-gray-100 hover:text-fidelity-green'
      }`
    }
  >
    <span className={collapsed ? '' : 'mr-3'}>{icon}</span>
    {!collapsed && label}
  </NavLink>
);

// Helper to convert API workspace to frontend workspace type
const toFrontendWorkspace = (ws: ApiWorkspace): Workspace => ({
  id: ws.id,
  name: ws.name,
  description: ws.description,
  scenarios: [], // Scenarios loaded separately
  lastRun: ws.updated_at ? new Date(ws.updated_at).toLocaleDateString() : 'Never',
  created_at: ws.created_at,
  updated_at: ws.updated_at,
  base_config: ws.base_config,
  storage_path: ws.storage_path,
});

export default function Layout() {
  const navigate = useNavigate();

  // Global Workspace State
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace | null>(null);
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [isWorkspaceLoading, setIsWorkspaceLoading] = useState(true);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [lastRunScenarioId, setLastRunScenarioId] = useState<string | null>(null);

  // Sidebar collapse state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Feature 045: Global simulation running state
  const [isSimulationRunning, setIsSimulationRunning] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [runningScenarioId, setRunningScenarioId] = useState<string | null>(null);
  const lastHeartbeatRef = useRef<number>(0);
  const checkInFlightRef = useRef<boolean>(false);

  const setSimulationRunning = useCallback((runId: string, scenarioId: string) => {
    setIsSimulationRunning(true);
    setActiveRunId(runId);
    setRunningScenarioId(scenarioId);
    lastHeartbeatRef.current = Date.now();
  }, []);

  const clearSimulationRunning = useCallback(() => {
    setIsSimulationRunning(false);
    setActiveRunId(null);
    setRunningScenarioId(null);
    lastHeartbeatRef.current = 0;
  }, []);

  // Feature 045: Detect active simulations on page load (refresh recovery)
  useEffect(() => {
    getActiveSimulations()
      .then((response) => {
        if (response.active_runs.length > 0) {
          const run = response.active_runs[0];
          setSimulationRunning(run.run_id, run.scenario_id);
        }
      })
      .catch(() => {
        // Silently ignore - API may not be ready yet
      });
  }, [setSimulationRunning]);

  // Feature 045: Safety timeout - verify with server when heartbeat is stale,
  // hard-clear after 30 minutes as last resort
  useEffect(() => {
    if (!isSimulationRunning) return;

    const SAFETY_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes hard cutoff
    const STALE_THRESHOLD_MS = 60 * 1000; // Poll server after 1 minute without heartbeat
    const CHECK_INTERVAL_MS = 60 * 1000; // Check every minute
    checkInFlightRef.current = false;

    const interval = setInterval(async () => {
      if (checkInFlightRef.current) return; // Skip if previous check hasn't resolved
      if (lastHeartbeatRef.current <= 0) return;

      const heartbeatAge = Date.now() - lastHeartbeatRef.current;

      // Hard safety timeout - always clear after 30 minutes
      if (heartbeatAge > SAFETY_TIMEOUT_MS) {
        clearSimulationRunning();
        return;
      }

      // Stale heartbeat - verify with server whether our specific run is still active
      if (heartbeatAge > STALE_THRESHOLD_MS) {
        checkInFlightRef.current = true;
        try {
          const response = await getActiveSimulations();
          const ourRunStillActive = response.active_runs.some(
            (run) => run.run_id === activeRunId
          );
          if (!ourRunStillActive) {
            clearSimulationRunning();
          }
        } catch {
          // Server unreachable - let the hard timeout handle it
        } finally {
          checkInFlightRef.current = false;
        }
      }
    }, CHECK_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [isSimulationRunning, activeRunId, clearSimulationRunning]);

  // Create Workspace State
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [newWorkspaceDesc, setNewWorkspaceDesc] = useState('');

  // Notification & Settings State
  const [notifications, setNotifications] = useState<Notification[]>(MOCK_NOTIFICATIONS);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false);

  const workspaceDropdownRef = useRef<HTMLDivElement>(null);
  const notificationDropdownRef = useRef<HTMLDivElement>(null);
  const settingsDropdownRef = useRef<HTMLDivElement>(null);

  // Load workspaces from API on mount
  const loadWorkspaces = useCallback(async () => {
    try {
      setIsWorkspaceLoading(true);
      setWorkspaceError(null);
      const apiWorkspaces = await listWorkspaces();
      const frontendWorkspaces = apiWorkspaces.map(toFrontendWorkspace);
      setWorkspaces(frontendWorkspaces);

      // Set active workspace to first one if none selected
      if (frontendWorkspaces.length > 0 && !activeWorkspace) {
        setActiveWorkspace(frontendWorkspaces[0]);
      }
    } catch (err) {
      setWorkspaceError(err instanceof Error ? err.message : 'Failed to load workspaces');
    } finally {
      setIsWorkspaceLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  // Close dropdowns when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (workspaceDropdownRef.current && !workspaceDropdownRef.current.contains(event.target as Node)) {
        setIsWorkspaceMenuOpen(false);
      }
      if (notificationDropdownRef.current && !notificationDropdownRef.current.contains(event.target as Node)) {
        setIsNotificationsOpen(false);
      }
      if (settingsDropdownRef.current && !settingsDropdownRef.current.contains(event.target as Node)) {
        setIsSettingsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Workspace CRUD Handlers - now using API
  const addWorkspace = async (ws: Workspace) => {
    try {
      const created = await apiCreateWorkspace({
        name: ws.name,
        description: ws.description,
      });
      const frontendWs = toFrontendWorkspace(created);
      setWorkspaces(prev => [...prev, frontendWs]);
      return frontendWs;
    } catch (err) {
      console.error('Failed to create workspace:', err);
      throw err;
    }
  };

  const updateWorkspace = async (id: string, updates: Partial<Workspace> & { base_config?: Record<string, any> }) => {
    try {
      const updated = await apiUpdateWorkspace(id, {
        name: updates.name,
        description: updates.description,
        base_config: updates.base_config,
      });
      const frontendWs = toFrontendWorkspace(updated);
      setWorkspaces(prev => prev.map(w => w.id === id ? frontendWs : w));
      if (activeWorkspace?.id === id) {
        setActiveWorkspace(frontendWs);
      }
    } catch (err) {
      console.error('Failed to update workspace:', err);
      throw err;
    }
  };

  const deleteWorkspace = async (id: string) => {
    if (workspaces.length <= 1) return; // Prevent deleting last one

    try {
      await apiDeleteWorkspace(id);
      const newWorkspaces = workspaces.filter(w => w.id !== id);
      setWorkspaces(newWorkspaces);

      // If we deleted the active one, switch to the first available
      if (activeWorkspace?.id === id) {
        setActiveWorkspace(newWorkspaces[0]);
      }
    } catch (err) {
      console.error('Failed to delete workspace:', err);
      throw err;
    }
  };

  const handleWorkspaceSelect = (workspace: Workspace) => {
    if (workspace.id === activeWorkspace?.id) {
      setIsWorkspaceMenuOpen(false);
      return;
    }

    setIsWorkspaceMenuOpen(false);
    setActiveWorkspace(workspace);
  };

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;

    try {
      setIsWorkspaceLoading(true);
      const newWorkspace: Workspace = {
        id: '', // Will be set by API
        name: newWorkspaceName,
        description: newWorkspaceDesc || 'No description provided.',
        scenarios: [],
        lastRun: 'Never',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        base_config: {},
        storage_path: '',
      };

      const created = await addWorkspace(newWorkspace);

      // Switch to new workspace
      setIsCreateModalOpen(false);
      setActiveWorkspace(created);

      // Reset form
      setNewWorkspaceName('');
      setNewWorkspaceDesc('');
    } catch (err) {
      console.error('Failed to create workspace:', err);
    } finally {
      setIsWorkspaceLoading(false);
    }
  };

  const unreadCount = notifications.filter(n => !n.read).length;

  const markAsRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  };

  const clearAllNotifications = () => {
    setNotifications([]);
  };

  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'success': return <CheckCircle size={16} className="text-green-500" />;
      case 'warning': return <AlertTriangle size={16} className="text-yellow-500" />;
      case 'error': return <AlertCircle size={16} className="text-red-500" />;
      default: return <Info size={16} className="text-blue-500" />;
    }
  };

  // Show loading state while fetching workspaces
  if (isWorkspaceLoading && workspaces.length === 0) {
    return (
      <div className="flex h-screen bg-gray-50 items-center justify-center">
        <div className="flex flex-col items-center">
          <Loader2 className="w-10 h-10 text-fidelity-green animate-spin mb-3" />
          <p className="text-sm font-medium text-gray-600">Loading workspaces...</p>
        </div>
      </div>
    );
  }

  // Show error state
  if (workspaceError && workspaces.length === 0) {
    return (
      <div className="flex h-screen bg-gray-50 items-center justify-center">
        <div className="flex flex-col items-center text-center max-w-md">
          <AlertCircle className="w-10 h-10 text-red-500 mb-3" />
          <p className="text-sm font-medium text-gray-800 mb-2">Failed to load workspaces</p>
          <p className="text-xs text-gray-500 mb-4">{workspaceError}</p>
          <button
            onClick={() => loadWorkspaces()}
            className="px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Show create workspace prompt if no workspaces exist
  if (!activeWorkspace && workspaces.length === 0) {
    return (
      <>
        <div className="flex h-screen bg-gray-50 items-center justify-center">
          <div className="flex flex-col items-center text-center max-w-md">
            <Briefcase className="w-10 h-10 text-gray-400 mb-3" />
            <p className="text-lg font-medium text-gray-800 mb-2">No Workspaces Found</p>
            <p className="text-sm text-gray-500 mb-4">Create your first workspace to get started.</p>
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm flex items-center"
            >
              <Plus size={16} className="mr-2" />
              Create Workspace
            </button>
          </div>
        </div>

        {/* Create Workspace Modal */}
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsCreateModalOpen(false)}></div>
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-fadeIn">
              <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                <h3 className="font-semibold text-gray-800">Create New Workspace</h3>
                <button onClick={() => setIsCreateModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <X size={20} />
                </button>
              </div>
              <form onSubmit={handleCreateWorkspace} className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Workspace Name</label>
                  <input
                    type="text"
                    value={newWorkspaceName}
                    onChange={(e) => setNewWorkspaceName(e.target.value)}
                    placeholder="e.g., Q2 2025 Budgeting"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description (Optional)</label>
                  <textarea
                    value={newWorkspaceDesc}
                    onChange={(e) => setNewWorkspaceDesc(e.target.value)}
                    placeholder="Brief description of this workspace's purpose..."
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                  />
                </div>
                <div className="flex justify-end space-x-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsCreateModalOpen(false)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!newWorkspaceName.trim()}
                    className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
                      !newWorkspaceName.trim() ? 'bg-gray-300 cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'
                    }`}
                  >
                    Create Workspace
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </>
    );
  }

  // Guard: ensure activeWorkspace exists for the rest of the render
  if (!activeWorkspace) {
    return null;
  }

  const contextValue: LayoutContextType = {
    activeWorkspace,
    setActiveWorkspace,
    workspaces,
    addWorkspace,
    updateWorkspace,
    deleteWorkspace,
    lastRunScenarioId,
    setLastRunScenarioId,
    isSimulationRunning,
    activeRunId,
    runningScenarioId,
    setSimulationRunning,
    clearSimulationRunning,
    lastHeartbeatRef,
  };

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden relative">
      {/* Loading Overlay */}
      {isWorkspaceLoading && workspaces.length > 0 && (
        <div className="absolute inset-0 bg-white/80 z-50 flex items-center justify-center backdrop-blur-sm animate-fadeIn">
          <div className="flex flex-col items-center">
            <Loader2 className="w-10 h-10 text-fidelity-green animate-spin mb-3" />
            <p className="text-sm font-medium text-gray-600">Switching Workspace...</p>
          </div>
        </div>
      )}

      {/* Create Workspace Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsCreateModalOpen(false)}></div>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-fadeIn">
            <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
              <h3 className="font-semibold text-gray-800">Create New Workspace</h3>
              <button onClick={() => setIsCreateModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreateWorkspace} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Workspace Name</label>
                <input
                  type="text"
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  placeholder="e.g., Q2 2025 Budgeting"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description (Optional)</label>
                <textarea
                  value={newWorkspaceDesc}
                  onChange={(e) => setNewWorkspaceDesc(e.target.value)}
                  placeholder="Brief description of this workspace's purpose..."
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                />
              </div>
              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newWorkspaceName.trim()}
                  className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
                    !newWorkspaceName.trim() ? 'bg-gray-300 cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'
                  }`}
                >
                  Create Workspace
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Sidebar */}
      <aside className={`${sidebarCollapsed ? 'w-16' : 'w-64'} bg-white border-r border-gray-200 flex flex-col z-10 flex-shrink-0 transition-all duration-200`}>
        <div className={`flex items-center ${sidebarCollapsed ? 'justify-center px-2' : 'px-6'} h-16 border-b border-gray-200`}>
          {sidebarCollapsed ? (
            <button
              onClick={() => setSidebarCollapsed(false)}
              className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-fidelity-green transition-colors"
              title="Expand sidebar"
            >
              <PanelLeftOpen size={20} />
            </button>
          ) : (
            <>
              <Activity className="w-8 h-8 text-fidelity-green mr-3 flex-shrink-0" />
              <span className="text-lg font-bold text-gray-800 tracking-tight flex-1 truncate">{APP_NAME}</span>
              <button
                onClick={() => setSidebarCollapsed(true)}
                className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors flex-shrink-0"
                title="Collapse sidebar"
              >
                <PanelLeftClose size={18} />
              </button>
            </>
          )}
        </div>

        <nav className={`flex-1 ${sidebarCollapsed ? 'px-2' : 'px-4'} py-6 overflow-y-auto`}>
          {!sidebarCollapsed && (
            <div className="mb-2 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Main
            </div>
          )}
          <NavItem to="/" icon={<LayoutDashboard size={20} />} label="Dashboard" collapsed={sidebarCollapsed} />
          <NavItem to="/scenarios" icon={<Layers size={20} />} label="Scenarios" collapsed={sidebarCollapsed} />
          <NavItem to="/simulate" icon={<PlayCircle size={20} />} label="Simulate" collapsed={sidebarCollapsed} />
          <NavItem to="/analytics" icon={<BarChart3 size={20} />} label="Analytics" end collapsed={sidebarCollapsed} />
          <NavItem to="/analytics/dc-plan" icon={<PieChart size={20} />} label="DC Plan" collapsed={sidebarCollapsed} />
          <NavItem to="/analytics/vesting" icon={<Scale size={20} />} label="Vesting" collapsed={sidebarCollapsed} />
          <NavItem to="/analytics/ndt" icon={<Shield size={20} />} label="NDT Testing" collapsed={sidebarCollapsed} />
          <NavItem to="/compare" icon={<BarChart3 size={20} />} label="Compare Costs" collapsed={sidebarCollapsed} />
          <NavItem to="/batch" icon={<Database size={20} />} label="Batch Processing" collapsed={sidebarCollapsed} />
        </nav>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-8 shadow-sm flex-shrink-0 z-20">

          {/* Workspace Selector (Global Context) */}
          <div className="flex items-center" ref={workspaceDropdownRef}>
            <div className="relative">
              <button
                onClick={() => setIsWorkspaceMenuOpen(!isWorkspaceMenuOpen)}
                className="flex items-center space-x-3 px-3 py-2 rounded-lg hover:bg-gray-100 transition-colors border border-transparent hover:border-gray-200"
              >
                <div className="p-1.5 bg-blue-50 text-blue-600 rounded-md">
                  <Briefcase size={18} />
                </div>
                <div className="text-left hidden sm:block">
                  <p className="text-xs text-gray-500 font-medium">Active Workspace</p>
                  <p className="text-sm font-bold text-gray-900 flex items-center">
                    {activeWorkspace.name}
                    <ChevronDown size={14} className="ml-2 text-gray-400" />
                  </p>
                </div>
              </button>

              {/* Dropdown Menu */}
              {isWorkspaceMenuOpen && (
                <div className="absolute top-full left-0 mt-2 w-80 bg-white rounded-xl shadow-lg border border-gray-200 py-2 animate-fadeIn z-50">
                  <div className="px-4 py-2 border-b border-gray-100 mb-2">
                    <div className="relative">
                      <Search size={14} className="absolute left-2.5 top-2.5 text-gray-400" />
                      <input
                        type="text"
                        placeholder="Switch workspace..."
                        className="w-full pl-8 pr-3 py-1.5 text-sm bg-gray-50 border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-fidelity-green"
                      />
                    </div>
                  </div>

                  <div className="max-h-64 overflow-y-auto">
                    {workspaces.map((workspace) => (
                      <button
                        key={workspace.id}
                        onClick={() => handleWorkspaceSelect(workspace)}
                        className={`w-full text-left px-4 py-3 flex items-start hover:bg-gray-50 transition-colors ${
                          activeWorkspace.id === workspace.id ? 'bg-blue-50' : ''
                        }`}
                      >
                        <div className={`mt-1 flex-shrink-0 w-2 h-2 rounded-full mr-3 ${
                          activeWorkspace.id === workspace.id ? 'bg-fidelity-green' : 'bg-gray-300'
                        }`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex justify-between items-center">
                            <span className={`text-sm font-medium truncate pr-2 ${
                              activeWorkspace.id === workspace.id ? 'text-fidelity-green' : 'text-gray-900'
                            }`}>
                              {workspace.name}
                            </span>
                            {activeWorkspace.id === workspace.id && <Check size={14} className="text-fidelity-green flex-shrink-0" />}
                          </div>
                          <div className="group relative">
                            <p className="text-xs text-gray-500 mt-0.5 truncate">{workspace.description || 'No description'}</p>
                            {/* Tooltip on hover */}
                            {workspace.description && (
                              <div className="absolute left-0 top-full mt-1 hidden group-hover:block z-50 w-full bg-gray-800 text-white text-xs rounded px-2 py-1 shadow-lg pointer-events-none">
                                {workspace.description}
                              </div>
                            )}
                          </div>
                          <p className="text-[10px] text-gray-400 mt-1 uppercase flex items-center justify-between">
                            <span>Last Run: {workspace.lastRun || 'Never'}</span>
                            <span className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-500 font-mono">
                              {workspace.scenarios.length} Scenarios
                            </span>
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>

                  <div className="border-t border-gray-100 mt-2 pt-2 px-2 space-y-1">
                    <button
                      onClick={() => {
                        setIsWorkspaceMenuOpen(false);
                        setIsCreateModalOpen(true);
                      }}
                      className="w-full py-2 text-xs font-medium text-white bg-fidelity-green hover:bg-fidelity-dark rounded-md transition-colors flex items-center justify-center"
                    >
                      <Plus size={14} className="mr-1.5" /> Create New Workspace
                    </button>
                    <button
                      onClick={() => {
                        setIsWorkspaceMenuOpen(false);
                        navigate('/workspaces');
                      }}
                      className="w-full py-2 text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-50 rounded-md transition-colors flex items-center justify-center"
                    >
                      Manage Workspaces →
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="h-8 w-px bg-gray-200 mx-4 hidden sm:block"></div>
            <span className="text-xs text-gray-400 hidden lg:block">Fidelity Internal Use Only</span>
          </div>

          {/* Right Header Controls */}
          <div className="flex items-center space-x-2 sm:space-x-4">
             {/* Notifications */}
             <div className="relative" ref={notificationDropdownRef}>
               <button
                 onClick={() => setIsNotificationsOpen(!isNotificationsOpen)}
                 className={`relative p-2 text-gray-500 hover:text-fidelity-green hover:bg-gray-50 rounded-full transition-colors ${isNotificationsOpen ? 'bg-gray-50 text-fidelity-green' : ''}`}
               >
                 <Bell size={20} />
                 {unreadCount > 0 && (
                   <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border border-white"></span>
                 )}
               </button>

               {isNotificationsOpen && (
                 <div className="absolute top-full right-0 mt-2 w-80 bg-white rounded-xl shadow-lg border border-gray-200 z-50 animate-fadeIn overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                       <h3 className="text-sm font-semibold text-gray-800">Notifications</h3>
                       {notifications.length > 0 && (
                         <button
                           onClick={clearAllNotifications}
                           className="text-xs text-gray-500 hover:text-red-500"
                         >
                           Clear All
                         </button>
                       )}
                    </div>
                    <div className="max-h-80 overflow-y-auto">
                       {notifications.length === 0 ? (
                         <div className="p-8 text-center text-gray-500 text-sm">
                           <Bell size={24} className="mx-auto mb-2 text-gray-300" />
                           No new notifications
                         </div>
                       ) : (
                         <div className="divide-y divide-gray-100">
                           {notifications.map((note) => (
                             <div
                               key={note.id}
                               className={`p-4 hover:bg-gray-50 transition-colors flex items-start ${!note.read ? 'bg-blue-50/50' : ''}`}
                               onClick={() => markAsRead(note.id)}
                             >
                                <div className="mt-0.5 mr-3 flex-shrink-0">
                                  {getNotificationIcon(note.type)}
                                </div>
                                <div className="flex-1">
                                   <div className="flex justify-between items-start">
                                      <p className={`text-sm ${!note.read ? 'font-semibold text-gray-900' : 'font-medium text-gray-700'}`}>
                                        {note.title}
                                      </p>
                                      <span className="text-[10px] text-gray-400 whitespace-nowrap ml-2">{note.timestamp}</span>
                                   </div>
                                   <p className="text-xs text-gray-500 mt-1">{note.message}</p>
                                </div>
                                {!note.read && (
                                  <div className="ml-2 w-2 h-2 bg-blue-500 rounded-full mt-1.5"></div>
                                )}
                             </div>
                           ))}
                         </div>
                       )}
                    </div>
                    <div className="p-2 border-t border-gray-100 bg-gray-50 text-center">
                      <button className="text-xs font-medium text-fidelity-green hover:underline">View All Notifications</button>
                    </div>
                 </div>
               )}
             </div>

             {/* Settings */}
             <div className="relative" ref={settingsDropdownRef}>
               <button
                 onClick={() => setIsSettingsOpen(!isSettingsOpen)}
                 className={`p-2 text-gray-500 hover:text-fidelity-green hover:bg-gray-50 rounded-full transition-colors ${isSettingsOpen ? 'bg-gray-50 text-fidelity-green' : ''}`}
               >
                 <Settings size={20} />
               </button>

               {isSettingsOpen && (
                 <div className="absolute top-full right-0 mt-2 w-64 bg-white rounded-xl shadow-lg border border-gray-200 z-50 animate-fadeIn overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
                       <h3 className="text-sm font-semibold text-gray-800">Settings</h3>
                    </div>
                    <div className="p-2 space-y-1">
                       <button className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg flex items-center justify-between group">
                          <span className="flex items-center">
                            <Activity size={16} className="mr-3 text-gray-400 group-hover:text-fidelity-green" />
                            System Preferences
                          </span>
                       </button>
                       <button
                         onClick={() => setIsDarkMode(!isDarkMode)}
                         className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg flex items-center justify-between group"
                       >
                          <span className="flex items-center">
                            {isDarkMode ? <Moon size={16} className="mr-3 text-gray-400" /> : <Sun size={16} className="mr-3 text-gray-400" />}
                            Theme: {isDarkMode ? 'Dark' : 'Light'}
                          </span>
                       </button>
                    </div>

                    <div className="border-t border-gray-100 p-2 space-y-1">
                       <button className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-lg flex items-center">
                          <HelpCircle size={16} className="mr-3 text-gray-400" />
                          Help & Support
                       </button>
                    </div>

                    <div className="bg-gray-50 px-4 py-3 border-t border-gray-100 text-center">
                       <p className="text-xs font-medium text-gray-500">{APP_NAME}</p>
                       <p className="text-[10px] text-gray-400">v{APP_VERSION}</p>
                    </div>
                 </div>
               )}
             </div>
          </div>
        </header>

        {/* Scrollable Content Area */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-8">
          {/* Pass workspace context to all child routes */}
          <Outlet context={contextValue} />
        </main>
      </div>
    </div>
  );
}
