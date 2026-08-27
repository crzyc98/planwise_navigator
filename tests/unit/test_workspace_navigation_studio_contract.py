"""Studio workspace-navigation acceptance contract for issues #619-#621."""

from pathlib import Path

import pytest


pytestmark = pytest.mark.fast

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = (ROOT / "planalign_studio/components/Layout.tsx").read_text()
API = (ROOT / "planalign_studio/services/api.ts").read_text()
MANAGER = (ROOT / "planalign_studio/components/WorkspaceManager.tsx").read_text()
APP = (ROOT / "planalign_studio/App.tsx").read_text()


def test_workspace_search_is_controlled_and_filters_name_and_description() -> None:
    assert "const [workspaceQuery, setWorkspaceQuery] = useState('')" in LAYOUT
    assert "value={workspaceQuery}" in LAYOUT
    assert "onChange={(event) => setWorkspaceQuery(event.target.value)}" in LAYOUT
    assert (
        "workspace.name.toLocaleLowerCase().includes(normalizedWorkspaceQuery)"
        in LAYOUT
    )
    assert "(workspace.description ?? '').toLocaleLowerCase().includes" in LAYOUT
    assert "No workspaces match “{workspaceQuery}”" in LAYOUT
    assert "autoFocus" in LAYOUT


def test_escape_clears_query_before_closing_palette() -> None:
    escape_branch = LAYOUT.split("if (event.key === 'Escape')", maxsplit=1)[1]
    assert "if (workspaceQuery)" in escape_branch
    assert "setWorkspaceQuery('')" in escape_branch
    assert "setIsWorkspaceMenuOpen(false)" in escape_branch


def test_active_workspace_and_recents_are_persisted() -> None:
    assert "planalign.activeWorkspaceId" in LAYOUT
    assert "planalign.recentWorkspaceIds" in LAYOUT
    assert "window.localStorage.getItem('planalign.activeWorkspaceId')" in APP
    assert "window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY" in LAYOUT
    assert ".slice(0, MAX_RECENT_WORKSPACES)" in LAYOUT
    assert "listWorkspaces({ lifecycle: 'active', limit: 1, sort: 'name' })" in APP
    assert "sortWorkspacesByName" in LAYOUT
    assert "The remembered workspace is unavailable" in APP


def test_palette_is_keyboard_first_compact_and_visually_distinct() -> None:
    assert "event.metaKey || event.ctrlKey" in LAYOUT
    assert "=== 'k' ||" in LAYOUT
    assert "=== 'o'" in LAYOUT
    for key in ("ArrowDown", "ArrowUp", "Enter"):
        assert f"event.key === '{key}'" in LAYOUT
    assert "Recent</p>" in LAYOUT
    assert "h-10 text-left" in LAYOUT
    assert "workspaceIdentity(activeWorkspace).initials" in LAYOUT
    assert "<HighlightedName name={workspace.name}" in LAYOUT


def test_list_uses_summary_contract_and_loads_selected_workspace_detail() -> None:
    assert "export interface WorkspaceSummary" in API
    assert (
        "listWorkspaces(options: WorkspaceListOptions = {}): Promise<WorkspacePage>"
        in API
    )
    assert "await apiGetWorkspace(routeWorkspaceId)" in LAYOUT
    assert "await apiGetWorkspace(workspace.id)" in LAYOUT


def test_archived_workspaces_are_managed_but_excluded_from_palette() -> None:
    assert "workspace.lifecycle === 'active'" in LAYOUT
    assert "'active' | 'archived'" in API
    assert "setLifecycleFilter" in MANAGER
    assert "['active', 'archived', 'all']" in MANAGER
    assert "toggleArchive" in MANAGER
    assert "<Archive size={16}" in MANAGER
    assert "<RotateCcw size={16}" in MANAGER


def test_workspace_route_is_authoritative_and_legacy_paths_redirect_once() -> None:
    assert '<Route path="/w/:workspaceId" element={<Layout />}>' in APP
    assert '<Route path="*" element={<LegacyWorkspaceRedirect />} />' in APP
    assert "workspace.id === routeWorkspaceId" not in LAYOUT
    assert "await apiGetWorkspace(routeWorkspaceId)" in LAYOUT
    assert "The URL was not redirected to a different client" in LAYOUT
    assert "routedWorkspace.lifecycle === 'archived'" in LAYOUT
    assert "location.pathname.replace(/^\\/w\\/[^/]+/" in LAYOUT


def test_large_workspace_sets_cut_over_to_debounced_server_search() -> None:
    assert "const SERVER_SEARCH_CUTOVER = 200" in LAYOUT
    assert "workspaceTotal <= SERVER_SEARCH_CUTOVER" in LAYOUT
    assert "q: workspaceQuery.trim()" in LAYOUT
    assert "}, 250)" in LAYOUT


def test_manager_uses_server_paging_and_dense_accessible_rows() -> None:
    assert "api.listWorkspaces({" in MANAGER
    assert "offset: page * pageSize" in MANAGER
    assert "q: debouncedSearch || undefined" in MANAGER
    assert "25 workspaces" not in MANAGER
    assert "of ${total} workspaces" in MANAGER
    assert 'aria-label="Workspace pagination"' in MANAGER
    assert "No matching workspaces" in MANAGER
    assert ">Current</span>" in MANAGER
    for action in ("Edit", "Export", "Delete"):
        assert f"{action} ${{ws.name}}" in MANAGER
    assert "'Archive' : 'Restore'} ${ws.name}" in MANAGER
