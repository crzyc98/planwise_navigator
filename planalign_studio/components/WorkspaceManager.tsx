import React, { useState } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import {
  Briefcase, Search, Plus, Trash2, Edit2, Check, X,
  ArrowRight, Layout, Calendar
} from 'lucide-react';
import { LayoutContextType } from './Layout';
import { Workspace } from '../types';

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

  const filteredWorkspaces = workspaces.filter(ws =>
    ws.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ws.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const startEditing = (ws: Workspace) => {
    setEditingId(ws.id);
    setEditName(ws.name);
    setEditDesc(ws.description);
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
      storage_path: '',
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

  return (
    <div className="max-w-6xl mx-auto animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Manage Workspaces</h1>
          <p className="text-gray-500 mt-1">Organize your simulation environments and projects.</p>
        </div>
        <button
          onClick={() => setIsCreateOpen(true)}
          className="flex items-center px-4 py-2 bg-fidelity-green text-white rounded-lg hover:bg-fidelity-dark transition-colors shadow-sm"
        >
          <Plus size={20} className="mr-2" />
          Create New Workspace
        </button>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200 mb-6">
        <div className="relative">
          <Search size={20} className="absolute left-3 top-2.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search workspaces by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
          />
        </div>
      </div>

      {/* Workspaces Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredWorkspaces.map(ws => (
          <div
            key={ws.id}
            className={`bg-white rounded-xl border p-6 flex flex-col transition-all ${
              activeWorkspace.id === ws.id
                ? 'border-fidelity-green shadow-md ring-1 ring-fidelity-green'
                : 'border-gray-200 shadow-sm hover:shadow-md'
            }`}
          >
            {editingId === ws.id ? (
              // Editing Mode
              <div className="space-y-3 flex-1">
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-2 py-1 border border-gray-300 rounded focus:ring-fidelity-green focus:border-fidelity-green text-lg font-bold"
                  autoFocus
                />
                <textarea
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full px-2 py-1 border border-gray-300 rounded focus:ring-fidelity-green focus:border-fidelity-green text-sm"
                  rows={2}
                />
                <div className="flex justify-end space-x-2 pt-2">
                  <button onClick={cancelEdit} className="p-1 text-gray-500 hover:text-gray-700">
                    <X size={20} />
                  </button>
                  <button onClick={() => saveEdit(ws.id)} className="p-1 text-green-600 hover:text-green-800">
                    <Check size={20} />
                  </button>
                </div>
              </div>
            ) : (
              // View Mode
              <div className="flex-1">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center">
                    <div className={`p-2 rounded-lg mr-3 ${
                      activeWorkspace.id === ws.id ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                    }`}>
                      <Briefcase size={20} />
                    </div>
                    <div>
                      <h3 className="font-bold text-gray-900">{ws.name}</h3>
                      <span className="text-xs text-gray-400 font-mono">{ws.id}</span>
                    </div>
                  </div>
                  {activeWorkspace.id === ws.id && (
                    <span className="px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-600 mb-4 line-clamp-2 min-h-[40px]">
                  {ws.description}
                </p>
                <div className="flex items-center text-xs text-gray-500 mb-4 space-x-4">
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
            <div className="pt-4 border-t border-gray-100 flex justify-between items-center mt-auto">
              {editingId !== ws.id && (
                <>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => startEditing(ws)}
                      className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
                      title="Edit"
                    >
                      <Edit2 size={16} />
                    </button>
                    {workspaces.length > 1 && (
                      <button
                        onClick={() => handleDelete(ws.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
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
          className="border-2 border-dashed border-gray-300 rounded-xl p-6 flex flex-col items-center justify-center text-gray-400 hover:border-fidelity-green hover:text-fidelity-green hover:bg-green-50/30 transition-all group min-h-[200px]"
        >
           <div className="p-3 bg-gray-50 rounded-full mb-3 group-hover:bg-white group-hover:shadow-sm transition-colors">
             <Plus size={24} />
           </div>
           <span className="font-medium">Create Workspace</span>
        </button>
      </div>

      {/* Create Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsCreateOpen(false)}></div>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-fadeIn">
            <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
              <h3 className="font-semibold text-gray-800">Create New Workspace</h3>
              <button onClick={() => setIsCreateOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Workspace Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g., Q2 2025 Budgeting"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Brief description of this workspace's purpose..."
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-fidelity-green focus:border-fidelity-green"
                />
              </div>
              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newName.trim()}
                  className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
                    !newName.trim() ? 'bg-gray-300 cursor-not-allowed' : 'bg-fidelity-green hover:bg-fidelity-dark'
                  }`}
                >
                  Create Workspace
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
