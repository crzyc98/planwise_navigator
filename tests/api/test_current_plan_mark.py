"""The current-plan mark: at most one scenario per workspace models the current plan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.scenario_service import ScenarioService
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.fast


def _workspace(root: Path) -> tuple[WorkspaceStorage, str, list[str]]:
    storage = WorkspaceStorage(root)
    workspace = storage.create_workspace(WorkspaceCreate(name="Workspace"), {})
    ids = []
    for name in ("Baseline", "Richer match", "No core"):
        scenario = storage.create_scenario(workspace.id, ScenarioCreate(name=name))
        assert scenario is not None
        ids.append(scenario.id)
    return storage, workspace.id, ids


def _marked(storage: WorkspaceStorage, workspace_id: str) -> list[str]:
    return [
        s.name for s in storage.list_scenarios(workspace_id) if s.models_current_plan
    ]


def test_marking_one_scenario_unmarks_the_others(tmp_path: Path) -> None:
    storage, workspace_id, (first, second, _) = _workspace(tmp_path)

    marked = storage.update_scenario(workspace_id, first, models_current_plan=True)
    assert marked is not None and marked.models_current_plan
    storage.update_scenario(workspace_id, second, models_current_plan=True)

    assert _marked(storage, workspace_id) == ["Richer match"]
    # It is persisted, so it survives a restart (a fresh storage instance).
    assert _marked(WorkspaceStorage(tmp_path), workspace_id) == ["Richer match"]

    storage.update_scenario(workspace_id, second, models_current_plan=False)
    assert _marked(storage, workspace_id) == []


def test_other_updates_leave_the_mark_alone(tmp_path: Path) -> None:
    storage, workspace_id, (first, _, _) = _workspace(tmp_path)
    storage.update_scenario(workspace_id, first, models_current_plan=True)

    storage.update_scenario(workspace_id, first, name="Current plan")

    assert _marked(storage, workspace_id) == ["Current plan"]


def test_scenario_files_without_the_field_load_unmarked(tmp_path: Path) -> None:
    storage, workspace_id, (first, _, _) = _workspace(tmp_path)
    path = tmp_path / workspace_id / "scenarios" / first / "scenario.json"
    data = json.loads(path.read_text())
    assert "models_current_plan" not in data

    scenario = storage.get_scenario(workspace_id, first)

    assert scenario is not None and scenario.models_current_plan is False


def test_a_copy_does_not_carry_the_mark(tmp_path: Path) -> None:
    storage, workspace_id, (first, _, _) = _workspace(tmp_path)
    storage.update_scenario(workspace_id, first, models_current_plan=True)

    copy = ScenarioService(storage).duplicate_scenario(workspace_id, first, "Copy")

    assert copy is not None and copy.models_current_plan is False
    assert _marked(storage, workspace_id) == ["Baseline"]


def test_mark_is_set_through_the_scenario_update_endpoint(client_factory) -> None:
    client = client_factory(None)
    workspace = client.post("/api/workspaces", json={"name": "Workspace"}).json()
    base = f"/api/workspaces/{workspace['id']}/scenarios"
    first = client.post(base, json={"name": "Baseline"}).json()
    # Creating can't set the mark, so a copy posted with it still starts unmarked.
    second = client.post(
        base, json={"name": "Copy", "models_current_plan": True}
    ).json()
    assert second["models_current_plan"] is False

    for scenario in (first, second):
        response = client.put(
            f"{base}/{scenario['id']}", json={"models_current_plan": True}
        )
        assert response.status_code == 200
        assert response.json()["models_current_plan"] is True

    listed = client.get(base).json()
    assert [s["name"] for s in listed if s["models_current_plan"]] == ["Copy"]
