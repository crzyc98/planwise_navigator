"""Managed batch attempts preserve SimulationService terminal outcomes."""

from pathlib import Path

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import batch as batch_router
from planalign_api.storage.workspace_storage import WorkspaceStorage


class RecordingSimulationService:
    run_directories: list[Path] = []

    def __init__(self, storage):
        self.storage = storage

    async def execute_simulation(
        self, *, workspace_id, scenario_id, run_id, config, resume_from_checkpoint
    ):
        run_dir = self.storage.allocate_run_directory(workspace_id, scenario_id, run_id)
        self.run_directories.append(run_dir)
        scenario = self.storage.get_scenario(workspace_id, scenario_id)
        outcome = "failed" if scenario and scenario.name == "Fails" else "completed"
        self.storage.update_scenario_status(workspace_id, scenario_id, outcome, run_id)


def test_batch_uses_service_outcome_and_distinct_run_databases(
    tmp_path, monkeypatch, client_factory
):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    successful = storage.create_scenario(workspace.id, ScenarioCreate(name="Succeeds"))
    failed = storage.create_scenario(workspace.id, ScenarioCreate(name="Fails"))
    assert successful and failed
    RecordingSimulationService.run_directories = []
    monkeypatch.setattr(batch_router, "SimulationService", RecordingSimulationService)
    client = client_factory("secret")

    created = client.post(
        f"/api/workspaces/{workspace.id}/run-all",
        json={"scenario_ids": [successful.id, failed.id], "parallel": False},
        headers={"Authorization": "Bearer secret"},
    )
    status = client.get(
        f"/api/batches/{created.json()['id']}/status",
        headers={"Authorization": "Bearer secret"},
    )

    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "failed"
    outcomes = {item["name"]: item["status"] for item in body["scenarios"]}
    assert outcomes == {"Succeeds": "completed", "Fails": "failed"}
    run_dirs = RecordingSimulationService.run_directories
    assert len(run_dirs) == 2
    assert run_dirs[0] != run_dirs[1]
    assert run_dirs[0].parent.parent != run_dirs[1].parent.parent
