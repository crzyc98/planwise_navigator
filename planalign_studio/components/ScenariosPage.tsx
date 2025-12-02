import React, { useState, useEffect } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { Plus, Play, Trash2, Pencil, Check, X, Layers, Settings, Clock, AlertCircle, CheckSquare, Square, PlayCircle } from 'lucide-react';
import { LayoutContextType } from './Layout';
import { listScenarios, createScenario, updateScenario, deleteScenario, Scenario } from '../services/api';

export default function ScenariosPage() {
  const navigate = useNavigate();
  const { activeWorkspace } = useOutletContext<LayoutContextType>();

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
      case 'completed': return 'bg-green-100 text-green-700';
      case 'running': return 'bg-blue-100 text-blue-700';
      case 'failed': return 'bg-red-100 text-red-700';
      case 'queued': return 'bg-yellow-100 text-yellow-700';
      default: return 'bg-gray-100 text-gray-600';
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
    const scenarioParam = Array.from(selectedIds).join(',');
    navigate(`/batch?scenarios=${scenarioParam}`);
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
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

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Scenarios</h1>
          <p className="text-gray-500 text-sm">
            Manage simulation scenarios for <span className="font-medium">{activeWorkspace.name}</span>
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {selectMode ? (
            <>
              <span className="text-sm text-gray-600">
                {selectedIds.size} selected
              </span>
              <button
                onClick={handleRunBatch}
                disabled={selectedIds.size === 0}
                className={`px-4 py-2 rounded-lg flex items-center font-medium shadow-sm transition-colors ${
                  selectedIds.size === 0
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                }`}
              >
                <PlayCircle size={18} className="mr-2" />
                Run as Batch
              </button>
              <button
                onClick={exitSelectMode}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg flex items-center font-medium hover:bg-gray-200 transition-colors"
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
                  className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg flex items-center font-medium hover:bg-gray-50 transition-colors"
                >
                  <CheckSquare size={18} className="mr-2" />
                  Select for Batch
                </button>
              )}
              <button
                onClick={() => setShowCreateForm(true)}
                className="px-4 py-2 bg-fidelity-green text-white rounded-lg flex items-center font-medium shadow-sm hover:bg-fidelity-dark transition-colors"
              >
                <Plus size={18} className="mr-2" />
                New Scenario
              </button>
            </>
          )}
        </div>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <h3 className="font-semibold text-gray-900 mb-4">Create New Scenario</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g., Baseline 2025, High Growth"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <input
                type="text"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Brief description..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
              />
            </div>
          </div>
          <div className="flex space-x-3">
            <button
              onClick={handleCreate}
              disabled={!newName.trim() || creating}
              className="px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center"
            >
              {creating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
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
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fidelity-green mx-auto mb-3"></div>
              <p className="text-sm text-gray-500">Loading scenarios...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
              <p className="text-sm text-red-600">{error}</p>
            </div>
          </div>
        ) : scenarios.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <Layers className="w-12 h-12 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-1">No scenarios yet</h3>
              <p className="text-sm text-gray-500 mb-4">Create your first scenario to get started.</p>
              <button
                onClick={() => setShowCreateForm(true)}
                className="px-4 py-2 bg-fidelity-green text-white rounded-lg text-sm font-medium hover:bg-fidelity-dark inline-flex items-center"
              >
                <Plus size={16} className="mr-2" />
                Create Scenario
              </button>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {/* Select All header when in select mode */}
            {selectMode && scenarios.length > 0 && (
              <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 flex items-center">
                <button
                  onClick={selectAll}
                  className="flex items-center text-sm text-gray-600 hover:text-gray-900"
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
                className={`p-4 hover:bg-gray-50 transition-colors ${
                  selectMode && selectedIds.has(scenario.id) ? 'bg-blue-50' : ''
                }`}
                onClick={selectMode ? () => toggleSelection(scenario.id) : undefined}
              >
                {editingId === scenario.id ? (
                  // Edit mode
                  <div className="space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                          autoFocus
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                        <input
                          type="text"
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-fidelity-green focus:border-fidelity-green"
                        />
                      </div>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={handleSaveEdit}
                        disabled={!editName.trim()}
                        className="px-3 py-1.5 bg-fidelity-green text-white rounded-lg text-sm hover:bg-fidelity-dark flex items-center disabled:bg-gray-300"
                      >
                        <Check size={14} className="mr-1" />
                        Save
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 flex items-center"
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
                          <Square size={20} className="text-gray-400" />
                        )}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center">
                        <h3 className="font-medium text-gray-900 truncate">{scenario.name}</h3>
                        <span className={`ml-3 px-2 py-0.5 text-xs rounded-full ${getStatusColor(scenario.status)}`}>
                          {getStatusLabel(scenario.status)}
                        </span>
                      </div>
                      {scenario.description && (
                        <p className="text-sm text-gray-500 mt-1 truncate">{scenario.description}</p>
                      )}
                      <div className="flex items-center text-xs text-gray-400 mt-1 space-x-4">
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
                        className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 flex items-center"
                        title="Configure scenario"
                      >
                        <Settings size={14} className="mr-1" />
                        Configure
                      </button>
                      <button
                        onClick={() => navigate(`/simulate?scenario=${scenario.id}`)}
                        className="px-3 py-1.5 bg-fidelity-green text-white rounded-lg text-sm hover:bg-fidelity-dark flex items-center"
                        title="Run simulation"
                      >
                        <Play size={14} className="mr-1" />
                        Run
                      </button>
                      <button
                        onClick={() => handleStartEdit(scenario)}
                        className="p-1.5 text-gray-400 hover:text-blue-500 rounded"
                        title="Edit scenario"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        onClick={() => handleDelete(scenario.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 rounded"
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
      <div className="mt-6 bg-blue-50 rounded-xl p-4 border border-blue-100">
        <div className="flex items-start">
          <Layers className="w-5 h-5 text-blue-500 mr-3 mt-0.5 flex-shrink-0" />
          <div>
            <h4 className="font-semibold text-blue-900 mb-1">How Scenarios Work</h4>
            <ul className="text-sm text-blue-700 space-y-1">
              <li>Each scenario inherits the workspace's base configuration</li>
              <li>Configure scenario-specific overrides by clicking "Configure"</li>
              <li>Run simulations independently and compare results across scenarios</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
