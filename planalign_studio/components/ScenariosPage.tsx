import React, { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Plus, Play, Trash2, Pencil, Check, X, Layers, Settings, Clock, AlertCircle, CheckSquare, Square, PlayCircle, Eye, Loader2, ArrowLeftRight } from 'lucide-react';
import { LayoutContextType } from './Layout';
import { listScenarios, createScenario, updateScenario, deleteScenario, Scenario } from '../services/api';
import { useWorkspaceNavigate } from '../hooks/useWorkspaceNavigation';

export default function ScenariosPage() {
  const navigate = useWorkspaceNavigate();
  const { activeWorkspace, isSimulationRunning, runningScenarioId } = useOutletContext<LayoutContextType>();

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create scenario state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  // Edit scenario state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');

  // Batch selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectMode, setSelectMode] = useState(false);

  // Load scenarios
  useEffect(() => {
    const loadScenarios = async () => {
      if (!activeWorkspace?.id) return;
      setLoading(true);
      setError(null);
      try {
        const data = await listScenarios(activeWorkspace.id);
        setScenarios(data);
      } catch (err) {
        setError('Failed to load scenarios');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    loadScenarios();
  }, [activeWorkspace?.id]);

  // Create scenario
  const handleCreate = async () => {
    if (!activeWorkspace?.id || !newName.trim()) return;
    setCreating(true);
    try {
      const created = await createScenario(activeWorkspace.id, {
        name: newName.trim(),
        description: newDesc.trim() || undefined,
      });
      setScenarios(prev => [...prev, created]);
      setNewName('');
      setNewDesc('');
      setShowCreateForm(false);
    } catch (err) {
      console.error('Failed to create scenario:', err);
    } finally {
      setCreating(false);
    }
  };

  // Start editing
  const handleStartEdit = (scenario: Scenario) => {
    setEditingId(scenario.id);
    setEditName(scenario.name);
    setEditDesc(scenario.description || '');
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setEditingId(null);
    setEditName('');
    setEditDesc('');
  };

  // Save edit
  const handleSaveEdit = async () => {
    if (!activeWorkspace?.id || !editingId || !editName.trim()) return;
    try {
      const updated = await updateScenario(activeWorkspace.id, editingId, {
        name: editName.trim(),
        description: editDesc.trim() || undefined,
      });
      setScenarios(prev => prev.map(s => s.id === editingId ? updated : s));
      handleCancelEdit();
    } catch (err) {
      console.error('Failed to update scenario:', err);
    }
  };

  // Delete scenario
  const handleDelete = async (scenarioId: string) => {
    if (!activeWorkspace?.id) return;
    if (!confirm('Are you sure you want to delete this scenario? This cannot be undone.')) return;
    try {
      await deleteScenario(activeWorkspace.id, scenarioId);
      setScenarios(prev => prev.filter(s => s.id !== scenarioId));
    } catch (err) {
      console.error('Failed to delete scenario:', err);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-success-surface text-success-ink';
      case 'running': return 'bg-info-surface text-info-ink';
      case 'failed': return 'bg-danger-surface text-danger-ink';
      case 'queued': return 'bg-warning-surface text-warning-ink';
      default: return 'bg-surface-subtle text-ink-muted';
    }
  };

  const getStatusLabel = (status: string) => {
    if (status === 'not_run') return 'Not Run';
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  // Batch selection functions
  const toggleSelection = (id: string) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  const selectAll = () => {
    if (selectedIds.size === scenarios.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(scenarios.map(s => s.id)));
    }
  };

  const handleRunBatch = () => {
    if (selectedIds.size === 0) return;
    const scenarioParam = [...selectedIds].map(String).join(',');
    navigate(`/batch?scenarios=${scenarioParam}`);
  };

  const selectedScenarios = [...selectedIds]
    .map(id => scenarios.find(scenario => scenario.id === id))
    .filter((scenario): scenario is Scenario => scenario !== undefined);
  const canDiff = selectedScenarios.length === 2
    && selectedScenarios.every(scenario => scenario.status === 'completed');

  const handleDiff = () => {
    if (!canDiff) return;
    navigate(`/analytics/diff?a=${selectedScenarios[0].id}&b=${selectedScenarios[1].id}`);
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
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

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">Scenarios</h1>
          <p className="text-ink-muted text-sm">
            Manage simulation scenarios for <span className="font-medium">{activeWorkspace.name}</span>
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {selectMode ? (
            <>
              <span className="text-sm text-ink-muted">
                {selectedIds.size} selected
              </span>
              <button
                onClick={handleDiff}
                disabled={!canDiff}
                title={canDiff ? 'Open focused scenario diff' : 'Select exactly two completed scenarios'}
                className={`px-4 py-2 rounded-lg flex items-center font-medium shadow-sm transition-colors ${canDiff ? 'bg-fidelity-green text-ink-inverse hover:bg-fidelity-dark' : 'bg-surface-disabled text-ink-subtle cursor-not-allowed'}`}
              >
                <ArrowLeftRight size={18} className="mr-2" />
                Diff A vs B
              </button>
              <button
                onClick={handleRunBatch}
                disabled={selectedIds.size === 0}
                className={`px-4 py-2 rounded-lg flex items-center font-medium shadow-sm transition-colors ${selectedIds.size === 0 ? 'bg-surface-disabled text-ink-subtle cursor-not-allowed' : 'bg-info-solid text-ink-inverse hover:bg-info-solid-hover'}`}
              >
                <PlayCircle size={18} className="mr-2" />
                Run as Batch
              </button>
              <button
                onClick={exitSelectMode}
                className="px-4 py-2 bg-surface-subtle text-ink-muted rounded-lg flex items-center font-medium hover:bg-surface-disabled transition-colors"
              >
                <X size={18} className="mr-2" />
                Cancel
              </button>
            </>
          ) : (
            <>
              {scenarios.length >= 2 && (
                <button
                  onClick={() => setSelectMode(true)}
                  className="px-4 py-2 bg-surface-raised border border-border-strong text-ink-muted rounded-lg flex items-center font-medium hover:bg-surface-subtle transition-colors"
                >
                  <CheckSquare size={18} className="mr-2" />
                  Select for Batch
                </button>
              )}
              <button
                onClick={() => setShowCreateForm(true)}
                className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg flex items-center font-medium shadow-sm hover:bg-fidelity-dark transition-colors"
              >
                <Plus size={18} className="mr-2" />
                New Scenario
              </button>
            </>
          )}
        </div>
      </div>

      {/* Scrollable content area */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* Create Form */}
        {showCreateForm && (
          <div className="bg-surface-raised rounded-xl shadow-sm border border-border p-6 mb-6">
          <h3 className="font-semibold text-ink mb-4">Create New Scenario</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label htmlFor="scenario-create-name" className="block text-sm font-medium text-ink-muted mb-1">Name *</label>
              <input
                id="scenario-create-name"
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g., Baseline 2025, High Growth"
                className="w-full px-3 py-2 border border-border-strong rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                autoFocus
              />
            </div>
            <div>
              <label htmlFor="scenario-create-desc" className="block text-sm font-medium text-ink-muted mb-1">Description</label>
              <input
                id="scenario-create-desc"
                type="text"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Brief description..."
                className="w-full px-3 py-2 border border-border-strong rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
              />
            </div>
          </div>
          <div className="flex space-x-3">
            <button
              onClick={handleCreate}
              disabled={!newName.trim() || creating}
              className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark disabled:bg-surface-disabled disabled:cursor-not-allowed flex items-center"
            >
              {creating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-border mr-2"></div>
                  Creating...
                </>
              ) : (
                <>
                  <Plus size={16} className="mr-2" />
                  Create
                </>
              )}
            </button>
            <button
              onClick={() => {
                setShowCreateForm(false);
                setNewName('');
                setNewDesc('');
              }}
              className="px-4 py-2 bg-surface-subtle text-ink-muted rounded-lg text-sm font-medium hover:bg-surface-disabled"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

        {/* Content */}
        <div className="bg-surface-raised rounded-xl shadow-sm border border-border flex flex-col overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
              <p className="text-sm text-ink-muted">Loading scenarios...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <AlertCircle className="w-10 h-10 text-danger-ink mx-auto mb-3" />
              <p className="text-sm text-danger-ink">{error}</p>
            </div>
          </div>
        ) : scenarios.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <Layers className="w-12 h-12 text-ink-subtle mx-auto mb-4" />
              <h3 className="text-lg font-medium text-ink mb-1">No scenarios yet</h3>
              <p className="text-sm text-ink-muted mb-4">Create your first scenario to get started.</p>
              <button
                onClick={() => setShowCreateForm(true)}
                className="px-4 py-2 bg-fidelity-green text-ink-inverse rounded-lg text-sm font-medium hover:bg-fidelity-dark inline-flex items-center"
              >
                <Plus size={16} className="mr-2" />
                Create Scenario
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto divide-y divide-border">
            {/* Select All header when in select mode */}
            {selectMode && scenarios.length > 0 && (
              <div className="px-4 py-2 bg-surface-subtle border-b border-border flex items-center">
                <button
                  onClick={selectAll}
                  className="flex items-center text-sm text-ink-muted hover:text-ink"
                >
                  {selectedIds.size === scenarios.length ? (
                    <CheckSquare size={18} className="mr-2 text-fidelity-green" />
                  ) : (
                    <Square size={18} className="mr-2" />
                  )}
                  {selectedIds.size === scenarios.length ? 'Deselect All' : 'Select All'}
                </button>
              </div>
            )}
            {scenarios.map((scenario) => (
              <div
                key={scenario.id}
                role={selectMode ? "checkbox" : undefined}
                aria-checked={selectMode ? selectedIds.has(scenario.id) : undefined}
                tabIndex={selectMode ? 0 : undefined}
                className={`p-4 hover:bg-surface-subtle transition-colors ${selectMode && selectedIds.has(scenario.id) ? 'bg-info-surface' : ''} ${selectMode ? 'cursor-pointer' : ''}`}
                onClick={selectMode ? () => toggleSelection(scenario.id) : undefined}
                onKeyDown={selectMode ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSelection(scenario.id); } } : undefined}
              >
                {editingId === scenario.id ? (
                  // Edit mode
                  <div className="space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label htmlFor="scenario-edit-name" className="block text-sm font-medium text-ink-muted mb-1">Name</label>
                        <input
                          id="scenario-edit-name"
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="w-full px-3 py-2 border border-border-strong rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                          autoFocus
                        />
                      </div>
                      <div>
                        <label htmlFor="scenario-edit-desc" className="block text-sm font-medium text-ink-muted mb-1">Description</label>
                        <input
                          id="scenario-edit-desc"
                          type="text"
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                          className="w-full px-3 py-2 border border-border-strong rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                        />
                      </div>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={handleSaveEdit}
                        disabled={!editName.trim()}
                        className="px-3 py-1.5 bg-fidelity-green text-ink-inverse rounded-lg text-sm hover:bg-fidelity-dark flex items-center disabled:bg-surface-disabled"
                      >
                        <Check size={14} className="mr-1" />
                        Save
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        className="px-3 py-1.5 bg-surface-subtle text-ink-muted rounded-lg text-sm hover:bg-surface-disabled flex items-center"
                      >
                        <X size={14} className="mr-1" />
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  // View mode
                  <div className="flex items-center justify-between">
                    {/* Checkbox for select mode */}
                    {selectMode && (
                      <div className="mr-4">
                        {selectedIds.has(scenario.id) ? (
                          <CheckSquare size={20} className="text-fidelity-green" />
                        ) : (
                          <Square size={20} className="text-ink-subtle" />
                        )}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center">
                        <h3 className="font-medium text-ink truncate">{scenario.name}</h3>
                        <span className={`ml-3 px-2 py-0.5 text-xs rounded-full ${getStatusColor(scenario.status)}`}>
                          {getStatusLabel(scenario.status)}
                        </span>
                      </div>
                      {scenario.description && (
                        <p className="text-sm text-ink-muted mt-1 truncate">{scenario.description}</p>
                      )}
                      <div className="flex items-center text-xs text-ink-subtle mt-1 space-x-4">
                        <span className="flex items-center">
                          <Clock size={12} className="mr-1" />
                          Created {new Date(scenario.created_at).toLocaleDateString()}
                        </span>
                        {scenario.last_run_at && (
                          <span>Last run: {new Date(scenario.last_run_at).toLocaleDateString()}</span>
                        )}
                      </div>
                    </div>
                    {/* Hide action buttons when in select mode */}
                    {!selectMode && (
                    <div className="flex items-center space-x-2 ml-4">
                      <button
                        onClick={() => navigate(`/config/${scenario.id}`)}
                        className="px-3 py-1.5 bg-surface-subtle text-ink-muted rounded-lg text-sm hover:bg-surface-disabled flex items-center"
                        title="Configure scenario"
                      >
                        <Settings size={14} className="mr-1" />
                        Configure
                      </button>
                      <button
                        onClick={() => navigate(`/simulate?scenario=${scenario.id}`)}
                        disabled={isSimulationRunning}
                        className={`px-3 py-1.5 rounded-lg text-sm flex items-center ${isSimulationRunning ? 'bg-surface-disabled text-ink-muted cursor-not-allowed' : 'bg-fidelity-green text-ink-inverse hover:bg-fidelity-dark'}`}
                        title={isSimulationRunning ? 'A simulation is already running' : 'Run simulation'}
                      >
                        {isSimulationRunning && scenario.id === runningScenarioId ? (
                          <>
                            <Loader2 size={14} className="mr-1 animate-spin" />
                            Running...
                          </>
                        ) : isSimulationRunning ? (
                          <>
                            <Play size={14} className="mr-1" />
                            Busy
                          </>
                        ) : (
                          <>
                            <Play size={14} className="mr-1" />
                            Run
                          </>
                        )}
                      </button>
                      {scenario.last_run_at && (
                        <button
                          onClick={() => navigate(`/simulate/${scenario.id}`)}
                          className="px-3 py-1.5 bg-info-surface text-info-ink rounded-lg text-sm hover:bg-info-surface flex items-center"
                          title="View last run results"
                        >
                          <Eye size={14} className="mr-1" />
                          Results
                        </button>
                      )}
                      <button
                        onClick={() => handleStartEdit(scenario)}
                        className="p-1.5 text-ink-subtle hover:text-info-ink rounded"
                        title="Edit scenario"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        onClick={() => handleDelete(scenario.id)}
                        className="p-1.5 text-ink-subtle hover:text-danger-ink rounded"
                        title="Delete scenario"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        </div>

        {/* Info Box */}
        <div className="mt-6 bg-info-surface rounded-xl p-4 border border-info-border flex-shrink-0">
          <div className="flex items-start">
            <Layers className="w-5 h-5 text-info-ink mr-3 mt-0.5 flex-shrink-0" />
            <div>
              <h4 className="font-semibold text-info-ink mb-1">How Scenarios Work</h4>
              <ul className="text-sm text-info-ink space-y-1">
                <li>Each scenario inherits the workspace's base configuration</li>
                <li>Configure scenario-specific overrides by clicking "Configure"</li>
                <li>Run simulations independently and compare results across scenarios</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
