import React, { useEffect, useState, useRef } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Briefcase, Search, Plus, Trash2, Edit2, Check, X,
  ArrowRight, Layout, Calendar, Download, Upload, AlertCircle, Loader2,
  Archive, RotateCcw
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import { Workspace } from '../types';
import * as api from '../services/api';

export default function WorkspaceManager() {
  const {
    activeWorkspace,
    setActiveWorkspace,
    updateWorkspace,
    deleteWorkspace,
    addWorkspace
  } = useOutletContext<LayoutContextType>();

  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [lifecycleFilter, setLifecycleFilter] = useState<'active' | 'archived' | 'all'>('active');
  const [sort, setSort] = useState<'name' | 'updated' | 'last_activity'>('name');
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(0);
  const [managedWorkspaces, setManagedWorkspaces] = useState<Array<Workspace & { scenarioCount: number }>>([]);
  const [total, setTotal] = useState(0);
  const [activeWorkspaceCount, setActiveWorkspaceCount] = useState(0);
  const [allWorkspaceCount, setAllWorkspaceCount] = useState(0);
  const [isLoadingWorkspaces, setIsLoadingWorkspaces] = useState(true);
  const [workspaceListError, setWorkspaceListError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');

  // Create Modal state for this page specifically
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');

  // Export/Import state
  const [exportingId, setExportingId] = useState<string | null>(null);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importValidation, setImportValidation] = useState<api.ImportValidationResponse | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [conflictResolution, setConflictResolution] = useState<'rename' | 'replace'>('rename');
  const [customName, setCustomName] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedSearch(searchQuery.trim()), 250);
    return () => window.clearTimeout(timeout);
  }, [searchQuery]);

  useEffect(() => {
    setPage(0);
  }, [debouncedSearch, lifecycleFilter, pageSize, sort]);

  useEffect(() => {
    let cancelled = false;
    setIsLoadingWorkspaces(true);
    setWorkspaceListError(null);

    void Promise.all([
      api.listWorkspaces({
        q: debouncedSearch || undefined,
        lifecycle: lifecycleFilter,
        limit: pageSize,
        offset: page * pageSize,
        sort,
      }),
      api.listWorkspaces({ lifecycle: 'active', limit: 1 }),
      api.listWorkspaces({ lifecycle: 'all', limit: 1 }),
    ]).then(([workspacePage, activePage, allPage]) => {
      if (cancelled) return;
      if (workspacePage.total > 0 && page * pageSize >= workspacePage.total) {
        setPage(Math.max(0, Math.ceil(workspacePage.total / pageSize) - 1));
        return;
      }
      setManagedWorkspaces(workspacePage.items.map(ws => ({
        id: ws.id,
        name: ws.name,
        description: ws.description,
        lifecycle: ws.lifecycle,
        scenarios: [],
        scenarioCount: ws.scenario_count,
        lastRun: ws.last_run_at ? new Date(ws.last_run_at).toLocaleDateString() : 'Never',
        lastRunAt: ws.last_run_at,
        created_at: ws.created_at,
        updated_at: ws.updated_at,
        base_config: {},
      })));
      setTotal(workspacePage.total);
      setActiveWorkspaceCount(activePage.total);
      setAllWorkspaceCount(allPage.total);
    }).catch(err => {
      if (!cancelled) {
        setWorkspaceListError(err instanceof Error ? err.message : 'Unable to load workspaces');
      }
    }).finally(() => {
      if (!cancelled) setIsLoadingWorkspaces(false);
    });

    return () => { cancelled = true; };
  }, [debouncedSearch, lifecycleFilter, page, pageSize, refreshVersion, sort]);

  const refreshWorkspacePage = () => setRefreshVersion(version => version + 1);

  const startEditing = (ws: Workspace) => {
    setEditingId(ws.id);
    setEditName(ws.name);
    setEditDesc(ws.description ?? '');
  };

  const saveEdit = async (id: string) => {
    if (!editName.trim()) return;
    await updateWorkspace(id, { name: editName, description: editDesc });
    setEditingId(null);
    refreshWorkspacePage();
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this workspace? This action cannot be undone.')) {
      await deleteWorkspace(id);
      refreshWorkspacePage();
    }
  };

  const toggleArchive = async (workspace: Workspace) => {
    const lifecycle = workspace.lifecycle === 'active' ? 'archived' : 'active';
    await updateWorkspace(workspace.id, { lifecycle });
    refreshWorkspacePage();
  };

  const isArchiveCandidate = (workspace: Workspace) => {
    if (workspace.lifecycle !== 'active') return false;
    const activityDate = new Date(workspace.lastRunAt ?? workspace.created_at);
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    return !Number.isNaN(activityDate.getTime()) && activityDate < sixMonthsAgo;
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;

    const newWorkspace: Workspace = {
      id: `ws_${Math.floor(Math.random() * 10000)}`,
      name: newName,
      description: newDesc || 'No description provided.',
      lifecycle: 'active',
      scenarios: [],
      lastRun: 'Never',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      base_config: {},
    };

    await addWorkspace(newWorkspace);
    setIsCreateOpen(false);
    setNewName('');
    setNewDesc('');
    setLifecycleFilter('active');
    setPage(0);
    refreshWorkspacePage();
  };

  const switchToWorkspace = (ws: Workspace) => void setActiveWorkspace(ws);

  // Export a single workspace
  const handleExport = async (workspaceId: string) => {
    setExportingId(workspaceId);
    try {
      await api.exportWorkspace(workspaceId);
    } catch (err) {
      console.error('Export failed:', err);
      alert(`Export failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setExportingId(null);
    }
  };

  // Handle file selection for import
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImportFile(file);
    setImportValidation(null);
    setImportError(null);
    setIsValidating(true);

    try {
      const validation = await api.validateImport(file);
      setImportValidation(validation);
      if (validation.conflict) {
        setCustomName(validation.conflict.suggested_name);
      }
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Validation failed');
    } finally {
      setIsValidating(false);
    }
  };

  // Execute import
  const handleImport = async () => {
    if (!importFile || !importValidation?.valid) return;

    setIsImporting(true);
    try {
      const resolution = importValidation.conflict ? conflictResolution : undefined;
      const newWorkspaceName = conflictResolution === 'rename' ? customName : undefined;

      await api.importWorkspace(importFile, resolution, newWorkspaceName);

      // Refresh workspace list (handled by parent context)
      window.location.reload();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setIsImporting(false);
    }
  };

  // Reset import dialog
  const closeImportDialog = () => {
    setIsImportOpen(false);
    setImportFile(null);
    setImportValidation(null);
    setImportError(null);
    setIsValidating(false);
    setIsImporting(false);
    setConflictResolution('rename');
    setCustomName('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="max-w-6xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">Manage Workspaces</h1>
          <p className="text-ink-muted mt-1">Organize your simulation environments and projects.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setIsImportOpen(true)}
            className="flex items-center px-4 py-2 bg-surface-raised border border-border-strong text-ink-muted rounded-lg hover:bg-surface-subtle transition-colors shadow-sm"
          >
            <Upload size={20} className="mr-2" />
            Import
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="flex items-center px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg hover:bg-fidelity-dark transition-colors shadow-sm"
          >
            <Plus size={20} className="mr-2" />
            Create New Workspace
          </button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="bg-surface-raised p-4 rounded-xl shadow-sm border border-border mb-6">
        <div className="relative">
          <Search size={20} className="absolute left-3 top-2.5 text-ink-subtle" />
          <input
            type="text"
            placeholder="Search workspaces by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
          />
        </div>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-1" role="group" aria-label="Workspace lifecycle filter">
            {(['active', 'archived', 'all'] as const).map(filter => (
              <button
                key={filter}
                type="button"
                onClick={() => setLifecycleFilter(filter)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium capitalize ${lifecycleFilter === filter ? 'bg-fidelity-green text-ink-inverse' : 'text-ink-muted hover:bg-surface-subtle'}`}
              >
                {filter}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-ink-muted">
            <label className="flex items-center gap-2">
              Sort
              <select
                value={sort}
                onChange={event => setSort(event.target.value as typeof sort)}
                className="rounded-md border border-border-strong bg-surface-raised px-2 py-1.5 text-ink"
              >
                <option value="name">Name</option>
                <option value="last_activity">Last activity</option>
                <option value="updated">Recently updated</option>
              </select>
            </label>
            <label className="flex items-center gap-2">
              Per page
              <select
                value={pageSize}
                onChange={event => setPageSize(Number(event.target.value))}
                className="rounded-md border border-border-strong bg-surface-raised px-2 py-1.5 text-ink"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
          </div>
        </div>
      </div>

      <div className="mb-3 flex items-center justify-between text-sm text-ink-muted" aria-live="polite">
        <span>
          {total === 0 ? '0 workspaces' : `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, total)} of ${total} workspaces`}
        </span>
        {isLoadingWorkspaces && <Loader2 size={16} className="animate-spin" aria-label="Loading workspaces" />}
      </div>

      {workspaceListError && (
        <div className="mb-4 rounded-lg border border-danger-border bg-danger-surface p-4 text-sm text-danger-ink" role="alert">
          {workspaceListError}
        </div>
      )}

      {/* Dense workspace list */}
      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised shadow-sm">
        <div className="hidden grid-cols-[minmax(0,2fr)_110px_100px_130px_180px] gap-4 border-b border-border bg-surface-subtle px-4 py-2 text-xs font-semibold uppercase tracking-wide text-ink-subtle md:grid">
          <span>Workspace</span>
          <span>Status</span>
          <span>Scenarios</span>
          <span>Last activity</span>
          <span className="text-right">Actions</span>
        </div>
        {managedWorkspaces.map(ws => (
          <div
            key={ws.id}
            className={`border-b border-border px-4 py-3 last:border-b-0 ${activeWorkspace.id === ws.id ? 'bg-success-surface/40' : 'hover:bg-surface-subtle/60'}`}
          >
            {editingId === ws.id ? (
              <div className="space-y-3">
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-2 py-1 border border-border-strong rounded focus:ring-fidelity-green focus:border-fidelity-green text-lg font-bold"
                  autoFocus
                />
                <textarea
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full px-2 py-1 border border-border-strong rounded focus:ring-fidelity-green focus:border-fidelity-green text-sm"
                  rows={2}
                />
                <div className="flex justify-end space-x-2">
                  <button onClick={cancelEdit} className="p-1 text-ink-muted hover:text-ink" aria-label={`Cancel editing ${ws.name}`}>
                    <X size={20} />
                  </button>
                  <button onClick={() => void saveEdit(ws.id)} className="p-1 text-success-ink hover:text-success-ink" aria-label={`Save ${ws.name}`}>
                    <Check size={20} />
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_110px_100px_130px_180px] md:items-center md:gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-3">
                    <div className={`rounded-lg p-2 ${activeWorkspace.id === ws.id ? 'bg-success-surface text-success-ink' : 'bg-surface-subtle text-ink-muted'}`}>
                      <Briefcase size={18} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate font-semibold text-ink">{ws.name}</h3>
                        {activeWorkspace.id === ws.id && (
                          <span className="rounded-full bg-success-surface px-2 py-0.5 text-xs font-medium text-success-ink">Current</span>
                        )}
                      </div>
                      <p className="truncate text-sm text-ink-muted">{ws.description || 'No description'}</p>
                      <span className="font-mono text-[11px] text-ink-subtle" title={ws.id}>{ws.id.slice(0, 8)}</span>
                    </div>
                  </div>
                </div>
                <div>
                  <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${ws.lifecycle === 'active' ? 'bg-success-surface text-success-ink' : 'bg-surface-subtle text-ink-muted'}`}>
                    {ws.lifecycle === 'active' ? 'Active' : 'Archived'}
                  </span>
                </div>
                <span className="flex items-center text-sm text-ink-muted"><Layout size={14} className="mr-1" />{ws.scenarioCount}</span>
                <div className="text-sm text-ink-muted">
                  <span className="flex items-center"><Calendar size={14} className="mr-1" />{ws.lastRun || 'Never'}</span>
                  {isArchiveCandidate(ws) && <span className="text-xs text-warning-ink">Consider archiving</span>}
                </div>
                <div className="flex items-center justify-start gap-1 md:justify-end">
                  {activeWorkspace.id !== ws.id && ws.lifecycle === 'active' && (
                    <button
                      onClick={() => switchToWorkspace(ws)}
                      className="mr-1 inline-flex items-center rounded-md px-2 py-1.5 text-sm font-medium text-fidelity-green hover:bg-success-surface"
                      aria-label={`Switch to ${ws.name}`}
                    >
                      Switch <ArrowRight size={14} className="ml-1" />
                    </button>
                  )}
                    <button
                      onClick={() => startEditing(ws)}
                      className="p-1.5 text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle rounded-md transition-colors"
                      title="Edit"
                      aria-label={`Edit ${ws.name}`}
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => void toggleArchive(ws)}
                      disabled={ws.lifecycle === 'active' && activeWorkspaceCount <= 1}
                      className="p-1.5 text-ink-subtle hover:text-info-ink hover:bg-info-surface rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      title={ws.lifecycle === 'active' ? 'Archive' : 'Restore'}
                      aria-label={`${ws.lifecycle === 'active' ? 'Archive' : 'Restore'} ${ws.name}`}
                    >
                      {ws.lifecycle === 'active' ? <Archive size={16} /> : <RotateCcw size={16} />}
                    </button>
                    <button
                      onClick={() => handleExport(ws.id)}
                      disabled={exportingId === ws.id}
                      className="p-1.5 text-ink-subtle hover:text-info-ink hover:bg-info-surface rounded-md transition-colors disabled:opacity-50"
                      title="Export"
                      aria-label={`Export ${ws.name}`}
                    >
                      {exportingId === ws.id ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Download size={16} />
                      )}
                    </button>
                    {allWorkspaceCount > 1 && (
                      <button
                        onClick={() => void handleDelete(ws.id)}
                        className="p-1.5 text-ink-subtle hover:text-danger-ink hover:bg-danger-surface rounded-md transition-colors"
                        title="Delete"
                        aria-label={`Delete ${ws.name}`}
                      >
                        <Trash2 size={16} />
                      </button>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {!isLoadingWorkspaces && !workspaceListError && managedWorkspaces.length === 0 && (
          <div className="px-6 py-12 text-center">
            <Briefcase size={28} className="mx-auto mb-3 text-ink-subtle" />
            <h3 className="font-semibold text-ink">No matching workspaces</h3>
            <p className="mt-1 text-sm text-ink-muted">Adjust the search or lifecycle filter, or create a new workspace.</p>
          </div>
        )}
      </div>

      {total > pageSize && (
        <nav className="mt-4 flex items-center justify-end gap-2" aria-label="Workspace pagination">
          <button
            type="button"
            disabled={page === 0 || isLoadingWorkspaces}
            onClick={() => setPage(current => Math.max(0, current - 1))}
            className="rounded-md border border-border-strong px-3 py-1.5 text-sm text-ink-muted disabled:cursor-not-allowed disabled:opacity-40"
          >
            Previous
          </button>
          <span className="px-2 text-sm text-ink-muted">Page {page + 1} of {Math.ceil(total / pageSize)}</span>
          <button
            type="button"
            disabled={(page + 1) * pageSize >= total || isLoadingWorkspaces}
            onClick={() => setPage(current => current + 1)}
            className="rounded-md border border-border-strong px-3 py-1.5 text-sm text-ink-muted disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next
          </button>
        </nav>
      )}

      {/* Create Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-overlay backdrop-blur-sm" role="presentation" tabIndex={0} onClick={() => setIsCreateOpen(false)} onKeyDown={(e) => { if (e.key === 'Escape' || e.key === 'Enter') setIsCreateOpen(false); }}></div>
          <div className="bg-surface-raised rounded-xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-fadeIn">
            <div className="px-6 py-4 border-b border-border flex justify-between items-center bg-surface-subtle">
              <h3 className="font-semibold text-ink">Create New Workspace</h3>
              <button onClick={() => setIsCreateOpen(false)} className="text-ink-subtle hover:text-ink-muted">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label htmlFor="workspace-create-name" className="block text-sm font-medium text-ink-muted mb-1">Workspace Name</label>
                <input
                  id="workspace-create-name"
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g., Q2 2025 Budgeting"
                  className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                  autoFocus
                />
              </div>
              <div>
                <label htmlFor="workspace-create-description" className="block text-sm font-medium text-ink-muted mb-1">Description</label>
                <textarea
                  id="workspace-create-description"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Brief description of this workspace's purpose..."
                  rows={3}
                  className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                />
              </div>
              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-ink-muted hover:bg-surface-subtle rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newName.trim()}
                  className={`px-4 py-2 text-sm font-medium text-ink-inverse rounded-lg transition-colors ${!newName.trim() ? 'bg-surface-disabled cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'}`}
                >
                  Create Workspace
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {isImportOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-overlay backdrop-blur-sm" role="presentation" tabIndex={0} onClick={closeImportDialog} onKeyDown={(e) => { if (e.key === 'Escape' || e.key === 'Enter') closeImportDialog(); }}></div>
          <div className="bg-surface-raised rounded-xl shadow-2xl w-full max-w-lg relative z-10 overflow-hidden animate-fadeIn">
            <div className="px-6 py-4 border-b border-border flex justify-between items-center bg-surface-subtle">
              <h3 className="font-semibold text-ink">Import Workspace</h3>
              <button onClick={closeImportDialog} className="text-ink-subtle hover:text-ink-muted">
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              {/* File Selection */}
              <div>
                <label htmlFor="workspace-import-file" className="block text-sm font-medium text-ink-muted mb-2">
                  Select Archive File (.7z)
                </label>
                <input
                  id="workspace-import-file"
                  ref={fileInputRef}
                  type="file"
                  accept=".7z"
                  onChange={handleFileSelect}
                  className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-fidelity-green file:text-ink-inverse hover:file:bg-fidelity-dark"
                />
              </div>

              {/* Validation Status */}
              {isValidating && (
                <div className="flex items-center text-ink-muted">
                  <Loader2 size={16} className="animate-spin mr-2" />
                  Validating archive...
                </div>
              )}

              {/* Validation Error */}
              {importError && (
                <div className="p-3 bg-danger-surface border border-danger-border rounded-lg flex items-start">
                  <AlertCircle size={20} className="text-danger-ink mr-2 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-danger-ink">{importError}</div>
                </div>
              )}

              {/* Validation Results */}
              {importValidation && !importValidation.valid && (
                <div className="p-3 bg-danger-surface border border-danger-border rounded-lg">
                  <div className="font-medium text-danger-ink mb-2">Validation Failed</div>
                  <ul className="text-sm text-danger-ink list-disc list-inside">
                    {importValidation.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}

              {importValidation?.valid && (
                <>
                  {/* Manifest Info */}
                  <div className="p-3 bg-success-surface border border-success-border rounded-lg">
                    <div className="font-medium text-success-ink mb-2">Archive Valid</div>
                    <div className="text-sm text-success-ink space-y-1">
                      <div><span className="font-medium">Name:</span> {importValidation.manifest?.workspace_name}</div>
                      <div><span className="font-medium">Scenarios:</span> {importValidation.manifest?.contents.scenario_count}</div>
                      <div><span className="font-medium">Exported:</span> {importValidation.manifest?.export_date ? new Date(importValidation.manifest.export_date).toLocaleString() : 'Unknown'}</div>
                    </div>
                  </div>

                  {/* Warnings */}
                  {importValidation.warnings.length > 0 && (
                    <div className="p-3 bg-warning-surface border border-warning-border rounded-lg">
                      <div className="font-medium text-warning-ink mb-2">Warnings</div>
                      <ul className="text-sm text-warning-ink list-disc list-inside">
                        {importValidation.warnings.map((warn, i) => (
                          <li key={i}>{warn}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Conflict Resolution */}
                  {importValidation.conflict && (
                    <div className="p-3 bg-warning-surface border border-warning-border rounded-lg">
                      <div className="font-medium text-warning-ink mb-2">Name Conflict</div>
                      <p className="text-sm text-warning-ink mb-3">
                        A workspace named "{importValidation.conflict.existing_workspace_name}" already exists.
                      </p>
                      <div className="space-y-2">
                        <label htmlFor="workspace-conflict-rename" className="flex items-center">
                          <input
                            id="workspace-conflict-rename"
                            type="radio"
                            name="conflict"
                            value="rename"
                            checked={conflictResolution === 'rename'}
                            onChange={() => setConflictResolution('rename')}
                            className="mr-2"
                          />
                          <span className="text-sm text-ink-muted">Rename to:</span>
                        </label>
                        {conflictResolution === 'rename' && (
                          <input
                            type="text"
                            value={customName}
                            onChange={(e) => setCustomName(e.target.value)}
                            className="w-full px-3 py-2 border border-border-strong rounded-lg focus:ring-fidelity-green focus:border-fidelity-green text-sm"
                          />
                        )}
                        <label htmlFor="workspace-conflict-replace" className="flex items-center">
                          <input
                            id="workspace-conflict-replace"
                            type="radio"
                            name="conflict"
                            value="replace"
                            checked={conflictResolution === 'replace'}
                            onChange={() => setConflictResolution('replace')}
                            className="mr-2"
                          />
                          <span className="text-sm text-ink-muted">Replace existing workspace</span>
                        </label>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Actions */}
              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={closeImportDialog}
                  className="px-4 py-2 text-sm font-medium text-ink-muted hover:bg-surface-subtle rounded-lg"
                >
                  Cancel
                </button>
                <button
                  onClick={handleImport}
                  disabled={!importValidation?.valid || isImporting}
                  className={`px-4 py-2 text-sm font-medium text-ink-inverse rounded-lg transition-colors flex items-center ${!importValidation?.valid || isImporting ? 'bg-surface-disabled cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'}`}
                >
                  {isImporting && <Loader2 size={16} className="animate-spin mr-2" />}
                  Import Workspace
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
