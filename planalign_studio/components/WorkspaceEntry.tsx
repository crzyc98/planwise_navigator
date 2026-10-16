import React from 'react';
import { useNavigate } from 'react-router-dom';
import { WorkspaceManagerContent, WorkspaceManagerContext } from './WorkspaceManager';
import * as api from '../services/api';

/** Workspace management before an active workspace exists. */
export default function WorkspaceEntry() {
  const navigate = useNavigate();
  const openWorkspace = (id: string) => navigate(`/w/${id}/import`);
  const context: WorkspaceManagerContext = {
    activeWorkspace: null,
    setActiveWorkspace: async workspace => { openWorkspace(workspace.id); },
    addWorkspace: async workspace => {
      const created = await api.createWorkspace({ name: workspace.name, description: workspace.description });
      openWorkspace(created.id);
      return { ...workspace, ...created };
    },
    updateWorkspace: async (id, updates) => {
      const updated = await api.updateWorkspace(id, {
        name: updates.name, description: updates.description, lifecycle: updates.lifecycle,
      });
      if (updates.lifecycle === 'active') openWorkspace(updated.id);
    },
    deleteWorkspace: async id => { await api.deleteWorkspace(id); },
  };

  return (
    <main className="min-h-screen bg-surface-subtle p-8">
      <p className="mx-auto mb-6 max-w-6xl text-ink-muted">
        No active workspace is available. Create a workspace, import an archive, or restore one using the Archived filter to continue.
      </p>
      <WorkspaceManagerContent {...context} />
    </main>
  );
}
