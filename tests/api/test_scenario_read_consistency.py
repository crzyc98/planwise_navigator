"""Scenario reads expose one latest-success/active-attempt contract."""

import json
import uuid

import duckdb

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.current_result import publish_current_result
from planalign_api.storage.workspace_storage import WorkspaceStorage


def _scenario(tmp_path):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="S"))
    assert scenario is not None
    return storage, workspace.id, scenario.id


def _publish_success(storage, workspace_id, scenario_id, run_id):
    run_dir = storage.allocate_run_directory(workspace_id, scenario_id, run_id)
    duckdb.connect(str(run_dir / "simulation.duckdb")).close()
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "completed",
                "start_year": 2025,
                "end_year": 2027,
            }
        )
    )
    publish_current_result(storage._scenario_path(workspace_id, scenario_id), run_id)


def test_running_read_keeps_body_and_exposes_previous_success(tmp_path, client_factory):
    storage, workspace_id, scenario_id = _scenario(tmp_path)
    successful_run = str(uuid.uuid4())
    active_run = str(uuid.uuid4())
    _publish_success(storage, workspace_id, scenario_id, successful_run)
    storage.update_scenario_status(workspace_id, scenario_id, "running", active_run)
    client = client_factory("secret")

    response = client.get(
        f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}",
        headers={
            "Authorization": "Bearer secret",
            "Origin": "http://localhost:5173",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.headers["X-PlanAlign-Run-Warning"] == "run_in_progress"
    assert response.headers["X-PlanAlign-Active-Run-Id"] == active_run
    assert response.headers["X-PlanAlign-Result-Run-Id"] == successful_run
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "x-planalign-run-warning" in exposed
    assert "x-planalign-active-run-id" in exposed
    assert "x-planalign-result-run-id" in exposed


def test_failed_attempt_keeps_success_without_warning(tmp_path, client_factory):
    storage, workspace_id, scenario_id = _scenario(tmp_path)
    successful_run = str(uuid.uuid4())
    _publish_success(storage, workspace_id, scenario_id, successful_run)
    storage.update_scenario_status(
        workspace_id, scenario_id, "failed", str(uuid.uuid4())
    )
    client = client_factory("secret")

    response = client.get(
        f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}",
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    assert "X-PlanAlign-Run-Warning" not in response.headers
    assert "X-PlanAlign-Active-Run-Id" not in response.headers
    assert response.headers["X-PlanAlign-Result-Run-Id"] == successful_run


def test_corrupt_pointer_fails_closed(tmp_path, client_factory):
    storage, workspace_id, scenario_id = _scenario(tmp_path)
    scenario_path = storage._scenario_path(workspace_id, scenario_id)
    (scenario_path / "current_result.json").write_text("not-json")
    client = client_factory("secret", raise_server_exceptions=False)

    response = client.get(
        f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}",
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 500
    assert "integrity failure" in response.json()["detail"].lower()
