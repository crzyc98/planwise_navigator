import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import WorkspaceEntry from './WorkspaceEntry';
import { WorkspaceManagerContent, WorkspaceManagerContext } from './WorkspaceManager';
import * as api from '../services/api';
import { Workspace } from '../types';

const navigate = vi.hoisted(() => vi.fn());
vi.mock('react-router-dom', async importOriginal => ({
  ...await importOriginal<typeof import('react-router-dom')>(),
  useNavigate: () => navigate,
}));
vi.mock('../services/api', () => ({
  createWorkspace: vi.fn(), updateWorkspace: vi.fn(), deleteWorkspace: vi.fn(),
}));
vi.mock('./WorkspaceManager', async importOriginal => ({
  ...await importOriginal<typeof import('./WorkspaceManager')>(),
  WorkspaceManagerContent: vi.fn(() => null),
}));

const workspace: Workspace = {
  id: 'archived', name: 'Synthetic workspace', description: '', lifecycle: 'active',
  scenarios: [], lastRun: 'Never', created_at: '', updated_at: '', base_config: {},
};

function entryContext(): WorkspaceManagerContext {
  renderToStaticMarkup(<WorkspaceEntry />);
  return vi.mocked(WorkspaceManagerContent).mock.calls.at(-1)![0];
}

describe('Workspace entry without an active workspace', () => {
  it('exposes existing creation, import, and archived restore controls', async () => {
    const actual = await vi.importActual<typeof import('./WorkspaceManager')>('./WorkspaceManager');
    const html = renderToStaticMarkup(<actual.WorkspaceManagerContent {...entryContext()} />);
    expect(html).toContain('Create New Workspace');
    expect(html).toContain('Import');
    expect(html).toContain('Workspace lifecycle filter');
    expect(html).toContain('archived');
    expect(entryContext().activeWorkspace).toBeNull();
  });

  it('creates through the API and opens census import using the server ID', async () => {
    vi.mocked(api.createWorkspace).mockResolvedValue({ ...workspace, id: 'created' } as api.Workspace);
    const created = await entryContext().addWorkspace(workspace);
    expect(api.createWorkspace).toHaveBeenCalledWith({ name: workspace.name, description: '' });
    expect(created.id).toBe('created');
    expect(navigate).toHaveBeenLastCalledWith('/w/created/import');
  });

  it('restores an archived workspace and opens census import', async () => {
    vi.mocked(api.updateWorkspace).mockResolvedValue(workspace as api.Workspace);
    await entryContext().updateWorkspace('archived', { lifecycle: 'active' });
    expect(api.updateWorkspace).toHaveBeenLastCalledWith('archived', {
      name: undefined, description: undefined, lifecycle: 'active',
    });
    expect(navigate).toHaveBeenLastCalledWith('/w/archived/import');
  });
});
