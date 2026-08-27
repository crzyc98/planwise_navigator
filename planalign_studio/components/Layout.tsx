import React, { useState, useRef, useEffect, useCallback } from 'react';
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  LayoutDashboard, PlayCircle, BarChart3, Settings, Database,
  Activity, Bell, ChevronDown, Check, Search, Briefcase,
  X, Info, AlertTriangle, AlertCircle, CheckCircle, Moon, Sun, HelpCircle,
  Plus, Loader2, Layers, PieChart, Scale, Shield, Menu, PanelLeftClose, PanelLeftOpen, ArrowLeftRight, FileUp, SlidersHorizontal, Users, Target
} from 'lucide-react';
import { APP_NAME, MOCK_NOTIFICATIONS, APP_VERSION } from '../constants';
import { Workspace, Notification } from '../types';
import {
  listWorkspaces,
  getWorkspace as apiGetWorkspace,
  createWorkspace as apiCreateWorkspace,
  updateWorkspace as apiUpdateWorkspace,
  deleteWorkspace as apiDeleteWorkspace,
  getActiveSimulations,
  RUN_CONSISTENCY_EVENT,
  RunConsistencyDetail,
  Workspace as ApiWorkspace,
  WorkspaceSummary as ApiWorkspaceSummary,
} from '../services/api';
import { useTheme } from '../hooks/useTheme';

export interface LayoutContextType {
  activeWorkspace: Workspace;
  setActiveWorkspace: (ws: Workspace) => Promise<void>;
  workspaces: Workspace[];
  addWorkspace: (ws: Workspace) => Promise<Workspace>;
  updateWorkspace: (id: string, updates: Partial<Workspace>) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;
  // Refetch the active workspace from the API and refresh shared state. Used after
  // side-effecting flows (e.g. census import) that mutate base_config server-side so
  // downstream pages (Configure) re-hydrate instead of reading a stale copy.
  refreshActiveWorkspace: () => Promise<void>;
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

const NavItem = ({ to, icon, label, end, collapsed }: Readonly<{ to: string; icon: React.ReactNode; label: string; end?: boolean; collapsed?: boolean }>) => (
  <NavLink
    to={to}
    end={end}
    title={collapsed ? label : undefined}
    className={({ isActive }) =>
      `flex items-center ${collapsed ? 'justify-center px-2' : 'px-4'} py-3 text-sm font-medium transition-colors rounded-lg mb-1 ${isActive ? 'bg-fidelity-green text-ink-inverse shadow-md' : 'text-ink-muted hover:bg-surface-subtle hover:text-fidelity-green'}`
    }
  >
    <span className={collapsed ? '' : 'mr-3'}>{icon}</span>
    {!collapsed && label}
  </NavLink>
);

// Sidebar nav grouped by workflow: setup → run → analyze. Dashboard stands alone at top.
const NAV_SECTIONS: ReadonlyArray<{
  heading: string | null;
  items: ReadonlyArray<{ to: string; icon: React.ReactNode; label: string; end?: boolean }>;
}> = [
  {
    heading: null,
    items: [{ to: '/', icon: <LayoutDashboard size={20} />, label: 'Dashboard', end: true }],
  },
  {
    heading: 'Setup',
    items: [
      { to: '/import', icon: <FileUp size={20} />, label: 'Import Data' },
      { to: '/scenarios', icon: <Layers size={20} />, label: 'Scenarios' },
    ],
  },
  {
    heading: 'Run',
    items: [
      { to: '/simulate', icon: <PlayCircle size={20} />, label: 'Simulate' },
      { to: '/batch', icon: <Database size={20} />, label: 'Batch Processing' },
      { to: '/timeline', icon: <Users size={20} />, label: 'Timeline' },
      { to: '/calibrate', icon: <SlidersHorizontal size={20} />, label: 'Calibration' },
      { to: '/optimize', icon: <Target size={20} />, label: 'Optimizer' },
    ],
  },
  {
    heading: 'Analyze',
    items: [
      { to: '/analytics', icon: <BarChart3 size={20} />, label: 'Overview', end: true },
      { to: '/analytics/dc-plan', icon: <PieChart size={20} />, label: 'DC Plan' },
      { to: '/analytics/vesting', icon: <Scale size={20} />, label: 'Vesting' },
      { to: '/analytics/ndt', icon: <Shield size={20} />, label: 'NDT Testing' },
      { to: '/analytics/winners-losers', icon: <ArrowLeftRight size={20} />, label: 'Winners & Losers' },
      { to: '/compare', icon: <BarChart3 size={20} />, label: 'Cost Comparison' },
    ],
  },
];

const ACTIVE_WORKSPACE_STORAGE_KEY = 'planalign.activeWorkspaceId';
const RECENT_WORKSPACES_STORAGE_KEY = 'planalign.recentWorkspaceIds';
const MAX_RECENT_WORKSPACES = 5;
const SERVER_SEARCH_CUTOVER = 200;
const WORKSPACE_CHIP_COLORS = [
  'bg-info-surface text-info-ink',
  'bg-success-surface text-success-ink',
  'bg-warning-surface text-warning-ink',
  'bg-danger-surface text-danger-ink',
] as const;

function readRecentWorkspaceIds(): string[] {
  try {
    const value = window.localStorage.getItem(RECENT_WORKSPACES_STORAGE_KEY);
    if (!value) return [];
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

function rememberWorkspace(workspaceId: string): string[] {
  const recentIds = [
    workspaceId,
    ...readRecentWorkspaceIds().filter(id => id !== workspaceId),
  ].slice(0, MAX_RECENT_WORKSPACES);
  try {
    window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, workspaceId);
    window.localStorage.setItem(RECENT_WORKSPACES_STORAGE_KEY, JSON.stringify(recentIds));
  } catch {
    // Storage can be unavailable in locked-down browser contexts. The current
    // session still works; persistence gracefully becomes best-effort.
  }
  return recentIds;
}

function sortWorkspacesByName(workspaces: Workspace[]): Workspace[] {
  return [...workspaces].sort((left, right) =>
    left.name.localeCompare(right.name, undefined, { sensitivity: 'base' })
  );
}

function workspaceIdentity(workspace: Workspace): { initials: string; color: string } {
  const initials = workspace.name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase() ?? '')
    .join('') || 'WS';
  const hash = [...workspace.id].reduce((total, char) => total + char.charCodeAt(0), 0);
  return { initials, color: WORKSPACE_CHIP_COLORS[hash % WORKSPACE_CHIP_COLORS.length] };
}

function HighlightedName({ name, query }: Readonly<{ name: string; query: string }>) {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const matchIndex = name.toLocaleLowerCase().indexOf(normalizedQuery);
  if (!normalizedQuery || matchIndex < 0) return <>{name}</>;
  const matchEnd = matchIndex + normalizedQuery.length;
  return (
    <>
      {name.slice(0, matchIndex)}
      <mark className="bg-warning-surface text-inherit rounded-sm">{name.slice(matchIndex, matchEnd)}</mark>
      {name.slice(matchEnd)}
    </>
  );
}

// Helper to convert API workspace to frontend workspace type
const toFrontendWorkspace = (ws: ApiWorkspace | ApiWorkspaceSummary): Workspace => ({
  id: ws.id,
  name: ws.name,
  description: ws.description,
  lifecycle: ws.lifecycle,
  scenarios: [], // Scenarios loaded separately
  lastRun: ('last_run_at' in ws ? ws.last_run_at : ws.updated_at)
    ? new Date(('last_run_at' in ws ? ws.last_run_at : ws.updated_at) as string).toLocaleDateString()
    : 'Never',
  lastRunAt: 'last_run_at' in ws ? ws.last_run_at : null,
  created_at: ws.created_at,
  updated_at: 'updated_at' in ws ? ws.updated_at : ws.created_at,
  base_config: 'base_config' in ws ? ws.base_config : {},
});

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { workspaceId: routeWorkspaceId } = useParams<{ workspaceId: string }>();
  const workspaceBase = routeWorkspaceId ? `/w/${routeWorkspaceId}` : '';
  const { preference, setPreference } = useTheme();

  // Global Workspace State
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceTotal, setWorkspaceTotal] = useState(0);
  const [serverSearchWorkspaces, setServerSearchWorkspaces] = useState<Workspace[] | null>(null);
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace | null>(null);
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [workspaceQuery, setWorkspaceQuery] = useState('');
  const [highlightedWorkspaceIndex, setHighlightedWorkspaceIndex] = useState(0);
  const [recentWorkspaceIds, setRecentWorkspaceIds] = useState<string[]>(readRecentWorkspaceIds);
  const [workspaceNotice, setWorkspaceNotice] = useState<string | null>(null);
  const [workspaceRouteError, setWorkspaceRouteError] = useState<string | null>(null);
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
  const [runConsistency, setRunConsistency] = useState<RunConsistencyDetail | null>(null);

  useEffect(() => {
    const handleRunConsistency = (event: Event) => {
      const detail = (event as CustomEvent<RunConsistencyDetail>).detail;
      setRunConsistency(detail.warning ? detail : null);
    };
    window.addEventListener(RUN_CONSISTENCY_EVENT, handleRunConsistency);
    return () => window.removeEventListener(RUN_CONSISTENCY_EVENT, handleRunConsistency);
  }, []);

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

  const workspaceDropdownRef = useRef<HTMLDivElement>(null);
  const notificationDropdownRef = useRef<HTMLDivElement>(null);
  const settingsDropdownRef = useRef<HTMLDivElement>(null);

  // Load workspaces from API on mount
  const loadWorkspaces = useCallback(async () => {
    try {
      setIsWorkspaceLoading(true);
      setWorkspaceError(null);
      setWorkspaceRouteError(null);
      const workspacePage = await listWorkspaces({
        limit: 500,
        lifecycle: 'all',
        sort: 'name',
      });
      const apiWorkspaces = workspacePage.items;
      setWorkspaceTotal(workspacePage.total);
      const frontendWorkspaces = sortWorkspacesByName(apiWorkspaces.map(toFrontendWorkspace));
      setWorkspaces(frontendWorkspaces);

      if (!routeWorkspaceId) {
        setWorkspaceRouteError(
          'The workspace id is missing from the URL. No client was selected implicitly.'
        );
        setActiveWorkspace(null);
        return;
      }

      let routedWorkspace: Workspace;
      try {
        routedWorkspace = toFrontendWorkspace(await apiGetWorkspace(routeWorkspaceId));
      } catch {
        setWorkspaceRouteError(
          `Workspace ${routeWorkspaceId} was not found. The URL was not redirected to a different client.`
        );
        setActiveWorkspace(null);
        return;
      }

      if (routedWorkspace.lifecycle === 'archived') {
        setWorkspaceRouteError(
          `${routedWorkspace.name} is archived. Restore it from Workspace Manager before opening its analysis pages.`
        );
        setActiveWorkspace(null);
      } else {
        setWorkspaces(current => current.some(workspace => workspace.id === routedWorkspace.id)
          ? current.map(workspace => workspace.id === routedWorkspace.id ? routedWorkspace : workspace)
          : sortWorkspacesByName([...current, routedWorkspace]));
        setActiveWorkspace(routedWorkspace);
        setRecentWorkspaceIds(rememberWorkspace(routedWorkspace.id));
        const routeState = location.state as { workspaceNotice?: string } | null;
        if (routeState?.workspaceNotice) setWorkspaceNotice(routeState.workspaceNotice);
      }
    } catch (err) {
      setWorkspaceError(err instanceof Error ? err.message : 'Failed to load workspaces');
    } finally {
      setIsWorkspaceLoading(false);
    }
  }, [location.state, routeWorkspaceId]);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  const normalizedWorkspaceQuery = workspaceQuery.trim().toLocaleLowerCase();
  const matchingWorkspaces = (serverSearchWorkspaces ?? workspaces).filter(workspace =>
    workspace.lifecycle === 'active'
      && (workspace.name.toLocaleLowerCase().includes(normalizedWorkspaceQuery)
        || (workspace.description ?? '').toLocaleLowerCase().includes(normalizedWorkspaceQuery))
  );
  const recentWorkspaces = recentWorkspaceIds
    .map(id => matchingWorkspaces.find(workspace => workspace.id === id))
    .filter((workspace): workspace is Workspace => Boolean(workspace));
  const recentIdSet = new Set(recentWorkspaces.map(workspace => workspace.id));
  const remainingWorkspaces = sortWorkspacesByName(
    matchingWorkspaces.filter(workspace => !recentIdSet.has(workspace.id))
  );
  const paletteWorkspaces = [...recentWorkspaces, ...remainingWorkspaces];

  useEffect(() => {
    setHighlightedWorkspaceIndex(0);
  }, [workspaceQuery, isWorkspaceMenuOpen]);

  useEffect(() => {
    if (workspaceTotal <= SERVER_SEARCH_CUTOVER || !normalizedWorkspaceQuery) {
      setServerSearchWorkspaces(null);
      return;
    }

    let cancelled = false;
    const timeout = window.setTimeout(() => {
      void listWorkspaces({
        q: workspaceQuery.trim(),
        limit: 50,
        lifecycle: 'active',
        sort: 'name',
      }).then(page => {
        if (!cancelled) setServerSearchWorkspaces(page.items.map(toFrontendWorkspace));
      }).catch(() => {
        if (!cancelled) setServerSearchWorkspaces([]);
      });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [normalizedWorkspaceQuery, workspaceQuery, workspaceTotal]);

  useEffect(() => {
    function handleWorkspaceShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && (event.key.toLocaleLowerCase() === 'k' || event.key.toLocaleLowerCase() === 'o')) {
        event.preventDefault();
        setIsWorkspaceMenuOpen(true);
      }
    }
    window.addEventListener('keydown', handleWorkspaceShortcut);
    return () => window.removeEventListener('keydown', handleWorkspaceShortcut);
  }, []);

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
      setWorkspaces(prev => sortWorkspacesByName([...prev, frontendWs]));
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
        lifecycle: updates.lifecycle,
      });
      const frontendWs = toFrontendWorkspace(updated);
      setWorkspaces(prev => prev.map(w => w.id === id
        ? { ...frontendWs, scenarios: w.scenarios, lastRun: w.lastRun, lastRunAt: w.lastRunAt }
        : w));
      if (activeWorkspace?.id === id) {
        if (frontendWs.lifecycle === 'archived') {
          const fallback = sortWorkspacesByName(workspaces.filter(
            workspace => workspace.id !== id && workspace.lifecycle === 'active'
          ))[0];
          setActiveWorkspace(fallback);
          setRecentWorkspaceIds(rememberWorkspace(fallback.id));
          setWorkspaceNotice(`Archived ${frontendWs.name}. Switched to ${fallback.name}.`);
          navigate(
            location.pathname.replace(/^\/w\/[^/]+/, `/w/${fallback.id}`),
            { replace: true }
          );
        } else {
          setActiveWorkspace(frontendWs);
        }
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

      // If the active workspace was deleted, make the fallback visible and
      // deterministic rather than silently selecting a UUID-ordered entry.
      if (activeWorkspace?.id === id) {
        const fallback = sortWorkspacesByName(newWorkspaces)[0];
        setActiveWorkspace(fallback);
        setRecentWorkspaceIds(rememberWorkspace(fallback.id));
        setWorkspaceNotice(`The active workspace was deleted. Switched to ${fallback.name}.`);
        navigate(`/w/${fallback.id}`, { replace: true });
      }
    } catch (err) {
      console.error('Failed to delete workspace:', err);
      throw err;
    }
  };

  const refreshActiveWorkspace = useCallback(async () => {
    if (!activeWorkspace?.id) return;
    try {
      const updated = await apiGetWorkspace(activeWorkspace.id);
      const frontendWs = toFrontendWorkspace(updated);
      setWorkspaces(prev => prev.map(w => w.id === frontendWs.id ? frontendWs : w));
      setActiveWorkspace(frontendWs);
    } catch (err) {
      console.error('Failed to refresh active workspace:', err);
    }
  }, [activeWorkspace?.id]);

  const handleWorkspaceSelect = async (workspace: Workspace) => {
    if (workspace.id === activeWorkspace?.id) {
      setIsWorkspaceMenuOpen(false);
      setWorkspaceQuery('');
      setRecentWorkspaceIds(rememberWorkspace(workspace.id));
      return;
    }

    setIsWorkspaceMenuOpen(false);
    setWorkspaceQuery('');
    setIsWorkspaceLoading(true);
    try {
      const selectedWorkspace = toFrontendWorkspace(await apiGetWorkspace(workspace.id));
      setWorkspaces(current => current.map(item =>
        item.id === selectedWorkspace.id ? selectedWorkspace : item
      ));
      setActiveWorkspace(selectedWorkspace);
      setRecentWorkspaceIds(rememberWorkspace(selectedWorkspace.id));
      navigate(location.pathname.replace(/^\/w\/[^/]+/, `/w/${selectedWorkspace.id}`));
    } catch (err) {
      setWorkspaceNotice(err instanceof Error ? err.message : 'Failed to switch workspace.');
    } finally {
      setIsWorkspaceLoading(false);
    }
  };

  const handleWorkspacePaletteKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      if (workspaceQuery) {
        setWorkspaceQuery('');
      } else {
        setIsWorkspaceMenuOpen(false);
      }
      return;
    }
    if (paletteWorkspaces.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlightedWorkspaceIndex(index => (index + 1) % paletteWorkspaces.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlightedWorkspaceIndex(index => (index - 1 + paletteWorkspaces.length) % paletteWorkspaces.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      handleWorkspaceSelect(paletteWorkspaces[highlightedWorkspaceIndex] ?? paletteWorkspaces[0]);
    }
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
        lifecycle: 'active',
        scenarios: [],
        lastRun: 'Never',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        base_config: {},
      };

      const created = await addWorkspace(newWorkspace);

      // Switch to new workspace
      setIsCreateModalOpen(false);
      setActiveWorkspace(created);
      setRecentWorkspaceIds(rememberWorkspace(created.id));
      navigate(`/w/${created.id}`);

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
      case 'success': return <CheckCircle size={16} className="text-success-ink" />;
      case 'warning': return <AlertTriangle size={16} className="text-warning-ink" />;
      case 'error': return <AlertCircle size={16} className="text-danger-ink" />;
      default: return <Info size={16} className="text-info-ink" />;
    }
  };

  // Show loading state while fetching workspaces
  if (isWorkspaceLoading && workspaces.length === 0) {
    return (
      <div className="flex h-screen bg-surface-subtle items-center justify-center">
        <div className="flex flex-col items-center">
          <Loader2 className="w-10 h-10 text-fidelity-green animate-spin mb-3" />
          <p className="text-sm font-medium text-ink-muted">Loading workspaces...</p>
        </div>
      </div>
    );
  }

  // Show error state
  if (workspaceError && workspaces.length === 0) {
    return (
      <div className="flex h-screen bg-surface-subtle items-center justify-center">
        <div className="flex flex-col items-center text-center max-w-md">
          <AlertCircle className="w-10 h-10 text-danger-ink mb-3" />
          <p className="text-sm font-medium text-ink mb-2">Failed to load workspaces</p>
          <p className="text-xs text-ink-muted mb-4">{workspaceError}</p>
          <button
            onClick={() => loadWorkspaces()}
            className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (workspaceRouteError) {
    return (
      <div className="flex h-screen bg-surface-subtle items-center justify-center p-6">
        <div className="flex max-w-lg flex-col items-center text-center">
          <AlertTriangle className="mb-3 h-10 w-10 text-warning-ink" />
          <p className="mb-2 text-lg font-semibold text-ink">Workspace unavailable</p>
          <p className="mb-4 text-sm text-ink-muted">{workspaceRouteError}</p>
          <button
            type="button"
            onClick={() => navigate('/', { replace: true })}
            className="rounded-lg bg-fidelity-green px-4 py-2 text-sm font-medium text-ink-inverse"
          >
            Choose an active workspace
          </button>
        </div>
      </div>
    );
  }

  // Show create workspace prompt if no workspaces exist
  if (!activeWorkspace && workspaces.length === 0) {
    return (
      <>
        <div className="flex h-screen bg-surface-subtle items-center justify-center">
          <div className="flex flex-col items-center text-center max-w-md">
            <Briefcase className="w-10 h-10 text-ink-subtle mb-3" />
            <p className="text-lg font-medium text-ink mb-2">No Workspaces Found</p>
            <p className="text-sm text-ink-muted mb-4">Create your first workspace to get started.</p>
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm flex items-center"
            >
              <Plus size={16} className="mr-2" />
              Create Workspace
            </button>
          </div>
        </div>

        {/* Create Workspace Modal */}
        {isCreateModalOpen && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-overlay backdrop-blur-sm" role="presentation" tabIndex={0} onClick={() => setIsCreateModalOpen(false)} onKeyDown={(e) => { if (e.key === 'Escape' || e.key === 'Enter') setIsCreateModalOpen(false); }}></div>
            <div className="bg-surface-raised rounded-xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-fadeIn">
              <div className="px-6 py-4 border-b border-border flex justify-between items-center bg-surface-subtle">
                <h3 className="font-semibold text-ink">Create New Workspace</h3>
                <button onClick={() => setIsCreateModalOpen(false)} className="text-ink-subtle hover:text-ink-muted">
                  <X size={20} />
                </button>
              </div>
              <form onSubmit={(e) => { handleCreateWorkspace(e); }} className="p-6 space-y-4">
                <div>
                  <label htmlFor="layout-empty-workspace-name" className="block text-sm font-medium text-ink-muted mb-1">Workspace Name</label>
                  <input
                    id="layout-empty-workspace-name"
                    type="text"
                    value={newWorkspaceName}
                    onChange={(e) => setNewWorkspaceName(e.target.value)}
                    placeholder="e.g., Q2 2025 Budgeting"
                    className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                    autoFocus
                  />
                </div>
                <div>
                  <label htmlFor="layout-empty-workspace-desc" className="block text-sm font-medium text-ink-muted mb-1">Description (Optional)</label>
                  <textarea
                    id="layout-empty-workspace-desc"
                    value={newWorkspaceDesc}
                    onChange={(e) => setNewWorkspaceDesc(e.target.value)}
                    placeholder="Brief description of this workspace's purpose..."
                    rows={3}
                    className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                  />
                </div>
                <div className="flex justify-end space-x-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsCreateModalOpen(false)}
                    className="px-4 py-2 text-sm font-medium text-ink-muted hover:bg-surface-subtle rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!newWorkspaceName.trim()}
                    className={`px-4 py-2 text-sm font-medium text-ink-inverse rounded-lg transition-colors ${!newWorkspaceName.trim() ? 'bg-surface-disabled cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'}`}
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
    setActiveWorkspace: handleWorkspaceSelect,
    workspaces,
    addWorkspace,
    updateWorkspace,
    deleteWorkspace,
    refreshActiveWorkspace,
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
    <div className="flex h-screen bg-surface-subtle overflow-hidden relative">
      {/* Loading Overlay */}
      {isWorkspaceLoading && workspaces.length > 0 && (
        <div className="absolute inset-0 bg-surface-raised/80 z-50 flex items-center justify-center backdrop-blur-sm animate-fadeIn">
          <div className="flex flex-col items-center">
            <Loader2 className="w-10 h-10 text-fidelity-green animate-spin mb-3" />
            <p className="text-sm font-medium text-ink-muted">Switching Workspace...</p>
          </div>
        </div>
      )}

      {/* Create Workspace Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-overlay backdrop-blur-sm" role="presentation" tabIndex={0} onClick={() => setIsCreateModalOpen(false)} onKeyDown={(e) => { if (e.key === 'Escape' || e.key === 'Enter') setIsCreateModalOpen(false); }}></div>
          <div className="bg-surface-raised rounded-xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-fadeIn">
            <div className="px-6 py-4 border-b border-border flex justify-between items-center bg-surface-subtle">
              <h3 className="font-semibold text-ink">Create New Workspace</h3>
              <button onClick={() => setIsCreateModalOpen(false)} className="text-ink-subtle hover:text-ink-muted">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={(e) => { handleCreateWorkspace(e); }} className="p-6 space-y-4">
              <div>
                <label htmlFor="layout-workspace-name" className="block text-sm font-medium text-ink-muted mb-1">Workspace Name</label>
                <input
                  id="layout-workspace-name"
                  type="text"
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  placeholder="e.g., Q2 2025 Budgeting"
                  className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                  autoFocus
                />
              </div>
              <div>
                <label htmlFor="layout-workspace-desc" className="block text-sm font-medium text-ink-muted mb-1">Description (Optional)</label>
                <textarea
                  id="layout-workspace-desc"
                  value={newWorkspaceDesc}
                  onChange={(e) => setNewWorkspaceDesc(e.target.value)}
                  placeholder="Brief description of this workspace's purpose..."
                  rows={3}
                  className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                />
              </div>
              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-ink-muted hover:bg-surface-subtle rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newWorkspaceName.trim()}
                  className={`px-4 py-2 text-sm font-medium text-ink-inverse rounded-lg transition-colors ${!newWorkspaceName.trim() ? 'bg-surface-disabled cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'}`}
                >
                  Create Workspace
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Sidebar */}
      <aside className={`${sidebarCollapsed ? 'w-16' : 'w-64'} bg-surface-raised border-r border-border flex flex-col z-10 flex-shrink-0 transition-all duration-200`}>
        <div className={`flex items-center ${sidebarCollapsed ? 'justify-center px-2' : 'px-6'} h-16 border-b border-border`}>
          {sidebarCollapsed ? (
            <button
              onClick={() => setSidebarCollapsed(false)}
              className="p-1.5 rounded-lg text-ink-muted hover:bg-surface-subtle hover:text-fidelity-green transition-colors"
              title="Expand sidebar"
            >
              <PanelLeftOpen size={20} />
            </button>
          ) : (
            <>
              <Activity className="w-8 h-8 text-fidelity-green mr-3 flex-shrink-0" />
              <span className="text-lg font-bold text-ink tracking-tight flex-1 truncate">{APP_NAME}</span>
              <button
                onClick={() => setSidebarCollapsed(true)}
                className="p-1.5 rounded-lg text-ink-subtle hover:bg-surface-subtle hover:text-ink-muted transition-colors flex-shrink-0"
                title="Collapse sidebar"
              >
                <PanelLeftClose size={18} />
              </button>
            </>
          )}
        </div>

        <nav className={`flex-1 ${sidebarCollapsed ? 'px-2' : 'px-4'} py-6 overflow-y-auto`}>
          {NAV_SECTIONS.map((section, sectionIndex) => (
            <div key={section.heading ?? 'top'}>
              {sectionIndex > 0 && sidebarCollapsed && (
                <div className="border-t border-border my-2 mx-3" />
              )}
              {!sidebarCollapsed && section.heading && (
                <div className={`${sectionIndex > 0 ? 'mt-6' : ''} mb-2 px-4 text-xs font-semibold text-ink-subtle uppercase tracking-wider`}>
                  {section.heading}
                </div>
              )}
              {section.items.map((item) => (
                <NavItem
                  key={item.to}
                  to={`${workspaceBase}${item.to === '/' ? '' : item.to}`}
                  icon={item.icon}
                  label={item.label}
                  end={item.end}
                  collapsed={sidebarCollapsed}
                />
              ))}
            </div>
          ))}
        </nav>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="h-16 bg-surface-raised border-b border-border flex items-center justify-between px-8 shadow-sm flex-shrink-0 z-20">

          {/* Workspace Selector (Global Context) */}
          <div className="flex items-center" ref={workspaceDropdownRef}>
            <div className="relative">
              <button
                onClick={() => setIsWorkspaceMenuOpen(!isWorkspaceMenuOpen)}
                aria-haspopup="dialog"
                aria-expanded={isWorkspaceMenuOpen}
                className="flex items-center space-x-3 px-3 py-2 rounded-lg hover:bg-surface-subtle transition-colors border border-transparent hover:border-border"
              >
                <div className={`w-8 h-8 flex items-center justify-center text-xs font-bold rounded-md ${workspaceIdentity(activeWorkspace).color}`}>
                  {workspaceIdentity(activeWorkspace).initials}
                </div>
                <div className="text-left hidden sm:block">
                  <p className="text-xs text-ink-muted font-medium">Active Workspace</p>
                  <p className="text-sm font-bold text-ink flex items-center">
                    {activeWorkspace.name}
                    <ChevronDown size={14} className="ml-2 text-ink-subtle" />
                  </p>
                </div>
              </button>

              {/* Dropdown Menu */}
              {isWorkspaceMenuOpen && (
                <div
                  role="dialog"
                  aria-label="Switch workspace"
                  className="absolute top-full left-0 mt-2 w-80 bg-surface-raised rounded-xl shadow-lg border border-border py-2 animate-fadeIn z-50"
                >
                  <div className="px-4 py-2 border-b border-border mb-2">
                    <div className="relative">
                      <Search size={14} className="absolute left-2.5 top-2.5 text-ink-subtle" />
                      <input
                        type="text"
                        placeholder="Switch workspace..."
                        value={workspaceQuery}
                        onChange={(event) => setWorkspaceQuery(event.target.value)}
                        onKeyDown={handleWorkspacePaletteKeyDown}
                        autoFocus
                        role="combobox"
                        aria-label="Search workspaces"
                        aria-expanded="true"
                        aria-controls="workspace-palette-results"
                        className="w-full pl-8 pr-3 py-1.5 text-sm bg-surface-subtle border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-fidelity-green"
                      />
                    </div>
                    <p className="mt-1.5 text-[10px] text-ink-subtle">↑↓ navigate · Enter select · Esc clear/close</p>
                  </div>

                  <div id="workspace-palette-results" role="listbox" className="max-h-80 overflow-y-auto">
                    {paletteWorkspaces.length === 0 && (
                      <p className="px-4 py-6 text-center text-sm text-ink-muted">
                        No workspaces match “{workspaceQuery}”
                      </p>
                    )}
                    {recentWorkspaces.length > 0 && !normalizedWorkspaceQuery && (
                      <p className="px-4 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">Recent</p>
                    )}
                    {paletteWorkspaces.map((workspace, index) => {
                      const identity = workspaceIdentity(workspace);
                      const startsRemainingSection = !normalizedWorkspaceQuery
                        && recentWorkspaces.length > 0
                        && index === recentWorkspaces.length;
                      return (
                        <React.Fragment key={workspace.id}>
                          {startsRemainingSection && (
                            <p className="px-4 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">All workspaces</p>
                          )}
                          <button
                            role="option"
                            aria-selected={activeWorkspace.id === workspace.id}
                            onMouseMove={() => setHighlightedWorkspaceIndex(index)}
                            onClick={() => handleWorkspaceSelect(workspace)}
                            className={`w-full h-10 text-left px-4 flex items-center gap-3 transition-colors ${index === highlightedWorkspaceIndex ? 'bg-surface-subtle' : ''}`}
                          >
                            <span className={`w-7 h-7 flex-shrink-0 flex items-center justify-center rounded text-[10px] font-bold ${identity.color}`}>
                              {identity.initials}
                            </span>
                            <span className={`flex-1 min-w-0 truncate text-sm font-medium ${activeWorkspace.id === workspace.id ? 'text-fidelity-green' : 'text-ink'}`}>
                              <HighlightedName name={workspace.name} query={workspaceQuery} />
                            </span>
                            {activeWorkspace.id === workspace.id && <Check size={14} className="text-fidelity-green flex-shrink-0" />}
                          </button>
                        </React.Fragment>
                      );
                    })}
                  </div>

                  <div className="border-t border-border mt-2 pt-2 px-2 space-y-1">
                    <button
                      onClick={() => {
                        setIsWorkspaceMenuOpen(false);
                        setIsCreateModalOpen(true);
                      }}
                      className="w-full py-2 text-xs font-medium text-ink-inverse bg-fidelity-green hover:bg-fidelity-dark rounded-md transition-colors flex items-center justify-center"
                    >
                      <Plus size={14} className="mr-1.5" /> Create New Workspace
                    </button>
                    <button
                      onClick={() => {
                        setIsWorkspaceMenuOpen(false);
                        navigate(`${workspaceBase}/workspaces`);
                      }}
                      className="w-full py-2 text-xs font-medium text-ink-muted hover:text-ink hover:bg-surface-subtle rounded-md transition-colors flex items-center justify-center"
                    >
                      Manage Workspaces →
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="h-8 w-px bg-surface-disabled mx-4 hidden sm:block"></div>
            <span className="text-xs text-ink-subtle hidden lg:block">Fidelity Internal Use Only</span>
          </div>

          {/* Right Header Controls */}
          <div className="flex items-center space-x-2 sm:space-x-4">
             {/* Notifications */}
             <div className="relative" ref={notificationDropdownRef}>
               <button
                 onClick={() => setIsNotificationsOpen(!isNotificationsOpen)}
                 className={`relative p-2 text-ink-muted hover:text-fidelity-green hover:bg-surface-subtle rounded-full transition-colors ${isNotificationsOpen ? 'bg-surface-subtle text-fidelity-green' : ''}`}
               >
                 <Bell size={20} />
                 {unreadCount > 0 && (
                   <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-danger-solid rounded-full border border-border"></span>
                 )}
               </button>

               {isNotificationsOpen && (
                 <div className="absolute top-full right-0 mt-2 w-80 bg-surface-raised rounded-xl shadow-lg border border-border z-50 animate-fadeIn overflow-hidden">
                    <div className="px-4 py-3 border-b border-border flex justify-between items-center bg-surface-subtle">
                       <h3 className="text-sm font-semibold text-ink">Notifications</h3>
                       {notifications.length > 0 && (
                         <button
                           onClick={clearAllNotifications}
                           className="text-xs text-ink-muted hover:text-danger-ink"
                         >
                           Clear All
                         </button>
                       )}
                    </div>
                    <div className="max-h-80 overflow-y-auto">
                       {notifications.length === 0 ? (
                         <div className="p-8 text-center text-ink-muted text-sm">
                           <Bell size={24} className="mx-auto mb-2 text-ink-subtle" />
                           No new notifications
                         </div>
                       ) : (
                         <div className="divide-y divide-border">
                           {notifications.map((note) => (
                             <div
                               key={note.id}
                               role="button"
                               tabIndex={0}
                               className={`p-4 hover:bg-surface-subtle transition-colors flex items-start ${!note.read ? 'bg-info-surface/50' : ''}`}
                               onClick={() => markAsRead(note.id)}
                               onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); markAsRead(note.id); } }}
                             >
                                <div className="mt-0.5 mr-3 flex-shrink-0">
                                  {getNotificationIcon(note.type)}
                                </div>
                                <div className="flex-1">
                                   <div className="flex justify-between items-start">
                                      <p className={`text-sm ${!note.read ? 'font-semibold text-ink' : 'font-medium text-ink-muted'}`}>
                                        {note.title}
                                      </p>
                                      <span className="text-[10px] text-ink-subtle whitespace-nowrap ml-2">{note.timestamp}</span>
                                   </div>
                                   <p className="text-xs text-ink-muted mt-1">{note.message}</p>
                                </div>
                                {!note.read && (
                                  <div className="ml-2 w-2 h-2 bg-info-solid rounded-full mt-1.5"></div>
                                )}
                             </div>
                           ))}
                         </div>
                       )}
                    </div>
                    <div className="p-2 border-t border-border bg-surface-subtle text-center">
                      <button className="text-xs font-medium text-fidelity-green hover:underline">View All Notifications</button>
                    </div>
                 </div>
               )}
             </div>

             {/* Settings */}
             <div className="relative" ref={settingsDropdownRef}>
               <button
                 onClick={() => setIsSettingsOpen(!isSettingsOpen)}
                 aria-label="Open settings"
                 aria-expanded={isSettingsOpen}
                 className={`p-2 text-ink-muted hover:text-fidelity-green hover:bg-surface-subtle rounded-full transition-colors ${isSettingsOpen ? 'bg-surface-subtle text-fidelity-green' : ''}`}
               >
                 <Settings size={20} />
               </button>

               {isSettingsOpen && (
                 <div className="absolute top-full right-0 mt-2 w-64 bg-surface-raised rounded-xl shadow-lg border border-border z-50 animate-fadeIn overflow-hidden">
                    <div className="px-4 py-3 border-b border-border bg-surface-subtle">
                       <h3 className="text-sm font-semibold text-ink">Settings</h3>
                    </div>
                    <div className="p-2 space-y-1">
                       <button className="w-full text-left px-3 py-2 text-sm text-ink-muted hover:bg-surface-subtle rounded-lg flex items-center justify-between group">
                          <span className="flex items-center">
                            <Activity size={16} className="mr-3 text-ink-subtle group-hover:text-fidelity-green" />
                            System Preferences
                          </span>
                       </button>
                       <div role="radiogroup" aria-label="Theme preference" className="px-1 py-1">
                         <p className="px-2 pb-1 text-xs font-medium text-ink-muted">Theme</p>
                         <button
                           type="button"
                           role="radio"
                           aria-checked={preference === 'system'}
                           onClick={() => setPreference('system')}
                           className="w-full px-2 py-2 text-sm text-ink-muted hover:bg-surface-subtle rounded-lg flex items-center justify-between"
                         >
                           <span className="flex items-center">
                             <Activity size={16} className="mr-3 text-ink-subtle" />
                             System
                           </span>
                           {preference === 'system' && <Check size={16} className="text-fidelity-green" />}
                         </button>
                         <button
                           type="button"
                           role="radio"
                           aria-checked={preference === 'light'}
                           onClick={() => setPreference('light')}
                           className="w-full px-2 py-2 text-sm text-ink-muted hover:bg-surface-subtle rounded-lg flex items-center justify-between"
                         >
                           <span className="flex items-center">
                             <Sun size={16} className="mr-3 text-ink-subtle" />
                             Light
                           </span>
                           {preference === 'light' && <Check size={16} className="text-fidelity-green" />}
                         </button>
                         <button
                           type="button"
                           role="radio"
                           aria-checked={preference === 'dark'}
                           onClick={() => setPreference('dark')}
                           className="w-full px-2 py-2 text-sm text-ink-muted hover:bg-surface-subtle rounded-lg flex items-center justify-between"
                         >
                           <span className="flex items-center">
                             <Moon size={16} className="mr-3 text-ink-subtle" />
                             Dark
                           </span>
                           {preference === 'dark' && <Check size={16} className="text-fidelity-green" />}
                         </button>
                       </div>
                    </div>

                    <div className="border-t border-border p-2 space-y-1">
                       <button className="w-full text-left px-3 py-2 text-sm text-ink-muted hover:bg-surface-subtle rounded-lg flex items-center">
                          <HelpCircle size={16} className="mr-3 text-ink-subtle" />
                          Help & Support
                       </button>
                    </div>

                    <div className="bg-surface-subtle px-4 py-3 border-t border-border text-center">
                       <p className="text-xs font-medium text-ink-muted">{APP_NAME}</p>
                       <p className="text-[10px] text-ink-subtle">v{APP_VERSION}</p>
                    </div>
                 </div>
               )}
             </div>
          </div>
        </header>

        {workspaceNotice && (
          <div
            role="status"
            className="flex items-center gap-3 border-b border-info-border bg-info-surface px-8 py-3 text-sm text-info-ink"
          >
            <Info size={18} className="flex-shrink-0" />
            <span className="flex-1">{workspaceNotice}</span>
            <button
              type="button"
              onClick={() => setWorkspaceNotice(null)}
              className="rounded p-1 hover:bg-surface-subtle"
              aria-label="Dismiss workspace notice"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {runConsistency?.warning === 'run_in_progress' && (
          <div
            role="status"
            className="flex items-center gap-3 border-b border-warning-border bg-warning-surface px-8 py-3 text-sm text-warning-ink"
          >
            <AlertTriangle size={18} className="flex-shrink-0" />
            <span>
              A simulation is in progress. Results remain pinned to the latest successful run until the new run completes.
            </span>
          </div>
        )}

        {/* Scrollable Content Area */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-8">
          {/* Pass workspace context to all child routes */}
          <Outlet context={contextValue} />
        </main>
      </div>
    </div>
  );
}
