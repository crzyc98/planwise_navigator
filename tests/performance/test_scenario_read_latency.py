"""Representative pointer-enriched scenario reads stay below the API target."""

import json
import statistics
import time
import uuid

import duckdb
import pytest
from fastapi.testclient import TestClient

import planalign_api.config as api_config
from planalign_api.main import create_app
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.performance


def _p95(samples):
    return statistics.quantiles(samples, n=20, method="inclusive")[18]


def _measure(client, path, headers):
    samples = []
    for _ in range(25):
        started = time.perf_counter()
        response = client.get(path, headers=headers)
        samples.append(time.perf_counter() - started)
        assert response.status_code == 200
    return _p95(samples)


def test_idle_and_active_scenario_reads_have_sub_two_second_p95(tmp_path, monkeypatch):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="S"))
    assert scenario is not None
    run_id = str(uuid.uuid4())
    run_dir = storage.allocate_run_directory(workspace.id, scenario.id, run_id)
    duckdb.connect(str(run_dir / "simulation.duckdb")).close()
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": run_id, "status": "completed"})
    )
    storage.publish_current_result(workspace.id, scenario.id, run_id)
    monkeypatch.setenv("PLANALIGN_API_TOKEN", "secret")
    monkeypatch.setattr(
        api_config,
        "settings",
        api_config.APISettings(workspaces_root=tmp_path / "workspaces"),
    )
    client = TestClient(create_app())
    path = f"/api/workspaces/{workspace.id}/scenarios/{scenario.id}"
    headers = {"Authorization": "Bearer secret"}

    idle_p95 = _measure(client, path, headers)
    storage.update_scenario_status(
        workspace.id, scenario.id, "running", str(uuid.uuid4())
    )
    active_p95 = _measure(client, path, headers)

    assert idle_p95 <= 2.0
    assert active_p95 <= 2.0
