import React, { useState, useRef } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import {
  Briefcase, Search, Plus, Trash2, Edit2, Check, X,
  ArrowRight, Layout, Calendar, Download, Upload, AlertCircle, Loader2
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import { Workspace } from '../types';
import * as api from '../services/api';

export default function WorkspaceManager() {
  const navigate = useNavigate();
  const {
    workspaces,
    activeWorkspace,
    setActiveWorkspace,
    updateWorkspace,
    deleteWorkspace,
    addWorkspace
  } = useOutletContext<LayoutContextType>();

  const [searchQuery, setSearchQuery] = useState('');
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

  const filteredWorkspaces = workspaces.filter(ws =>
    ws.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (ws.description ?? '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  const startEditing = (ws: Workspace) => {
    setEditingId(ws.id);
    setEditName(ws.name);
    setEditDesc(ws.description ?? '');
  };

  const saveEdit = (id: string) => {
    if (!editName.trim()) return;
    updateWorkspace(id, { name: editName, description: editDesc });
    setEditingId(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const handleDelete = (id: string) => {
    if (confirm('Are you sure you want to delete this workspace? This action cannot be undone.')) {
      deleteWorkspace(id);
    }
  };

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;

    const newWorkspace: Workspace = {
      id: `ws_${Math.floor(Math.random() * 10000)}`,
      name: newName,
      description: newDesc || 'No description provided.',
      scenarios: [],
      lastRun: 'Never',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      base_config: {},
    };

    addWorkspace(newWorkspace);
    setIsCreateOpen(false);
    setNewName('');
    setNewDesc('');
  };

  const switchToWorkspace = (ws: Workspace) => {
    setActiveWorkspace(ws);
    navigate('/');
  };

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
      </div>

      {/* Workspaces Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredWorkspaces.map(ws => (
          <div
            key={ws.id}
            className={`bg-surface-raised rounded-xl border p-6 flex flex-col transition-all ${activeWorkspace.id === ws.id ? 'border-fidelity-green shadow-md ring-1 ring-fidelity-green' : 'border-border shadow-sm hover:shadow-md'}`}
          >
            {editingId === ws.id ? (
              // Editing Mode
              <div className="space-y-3 flex-1">
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
                <div className="flex justify-end space-x-2 pt-2">
                  <button onClick={cancelEdit} className="p-1 text-ink-muted hover:text-ink-muted">
                    <X size={20} />
                  </button>
                  <button onClick={() => saveEdit(ws.id)} className="p-1 text-success-ink hover:text-success-ink">
                    <Check size={20} />
                  </button>
                </div>
              </div>
            ) : (
              // View Mode
              <div className="flex-1">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center">
                    <div className={`p-2 rounded-lg mr-3 ${activeWorkspace.id === ws.id ? 'bg-success-surface text-success-ink' : 'bg-surface-subtle text-ink-muted'}`}>
                      <Briefcase size={20} />
                    </div>
                    <div>
                      <h3 className="font-bold text-ink">{ws.name}</h3>
                      <span className="text-xs text-ink-subtle font-mono">{ws.id}</span>
                    </div>
                  </div>
                  {activeWorkspace.id === ws.id && (
                    <span className="px-2 py-1 bg-success-surface text-success-ink text-xs font-medium rounded-full">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-sm text-ink-muted mb-4 line-clamp-2 min-h-[40px]">
                  {ws.description || 'No description'}
                </p>
                <div className="flex items-center text-xs text-ink-muted mb-4 space-x-4">
                  <span className="flex items-center">
                    <Layout size={14} className="mr-1" />
                    {ws.scenarios.length} Scenarios
                  </span>
                  <span className="flex items-center">
                    <Calendar size={14} className="mr-1" />
                    Last run: {ws.lastRun || 'Never'}
                  </span>
                </div>
              </div>
            )}

            {/* Actions Footer */}
            <div className="pt-4 border-t border-border flex justify-between items-center mt-auto">
              {editingId !== ws.id && (
                <>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => startEditing(ws)}
                      className="p-1.5 text-ink-subtle hover:text-ink-muted hover:bg-surface-subtle rounded-md transition-colors"
                      title="Edit"
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => handleExport(ws.id)}
                      disabled={exportingId === ws.id}
                      className="p-1.5 text-ink-subtle hover:text-info-ink hover:bg-info-surface rounded-md transition-colors disabled:opacity-50"
                      title="Export"
                    >
                      {exportingId === ws.id ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Download size={16} />
                      )}
                    </button>
                    {workspaces.length > 1 && (
                      <button
                        onClick={() => handleDelete(ws.id)}
                        className="p-1.5 text-ink-subtle hover:text-danger-ink hover:bg-danger-surface rounded-md transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                  {activeWorkspace.id !== ws.id && (
                    <button
                      onClick={() => switchToWorkspace(ws)}
                      className="text-sm font-medium text-fidelity-green hover:text-fidelity-dark flex items-center"
                    >
                      Switch to <ArrowRight size={14} className="ml-1" />
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        ))}

        {/* Empty State / Add New Card */}
        <button
          onClick={() => setIsCreateOpen(true)}
          className="border-2 border-dashed border-border-strong rounded-xl p-6 flex flex-col items-center justify-center text-ink-subtle hover:border-fidelity-green hover:text-fidelity-green hover:bg-success-surface/30 transition-all group min-h-[200px]"
        >
           <div className="p-3 bg-surface-subtle rounded-full mb-3 group-hover:bg-surface-raised group-hover:shadow-sm transition-colors">
             <Plus size={24} />
           </div>
           <span className="font-medium">Create Workspace</span>
        </button>
      </div>

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
