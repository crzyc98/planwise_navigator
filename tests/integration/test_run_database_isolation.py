"""Run databases remain immutable across failure, cancellation, and promotion."""

import hashlib
import json
import uuid

import duckdb
import pytest

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.database_path_resolver import (
    DatabasePathResolver,
    IsolationMode,
)
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.integration


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _completed_run(storage, workspace_id, scenario_id, marker):
    run_id = str(uuid.uuid4())
    run_dir = storage.allocate_run_directory(workspace_id, scenario_id, run_id)
    with duckdb.connect(str(run_dir / "simulation.duckdb")) as connection:
        connection.execute("CREATE TABLE marker (value VARCHAR)")
        connection.execute("INSERT INTO marker VALUES (?)", [marker])
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
    storage.publish_current_result(workspace_id, scenario_id, run_id)
    return run_id, run_dir


def test_latest_success_survives_partial_failure_and_cancellation(tmp_path):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="S"))
    assert scenario is not None
    resolver = DatabasePathResolver(
        storage, isolation_mode=IsolationMode.MULTI_TENANT, project_root=tmp_path
    )
    shared = tmp_path / "shared.duckdb"
    shared.write_bytes(b"shared-dev-signature")
    shared_digest = _digest(shared)

    first_id, first_dir = _completed_run(storage, workspace.id, scenario.id, "first")
    first_digest = _digest(first_dir / "simulation.duckdb")

    failed_id = str(uuid.uuid4())
    failed_dir = storage.allocate_run_directory(workspace.id, scenario.id, failed_id)
    duckdb.connect(str(failed_dir / "simulation.duckdb")).close()
    failed_digest = _digest(failed_dir / "simulation.duckdb")
    storage.update_scenario_status(workspace.id, scenario.id, "running", failed_id)
    during = resolver.resolve(workspace.id, scenario.id)
    assert during.run_id == first_id
    assert during.active_run_id == failed_id
    assert during.run_warning == "run_in_progress"
    storage.update_scenario_status(workspace.id, scenario.id, "failed", failed_id)

    cancelled_id = str(uuid.uuid4())
    cancelled_dir = storage.allocate_run_directory(
        workspace.id, scenario.id, cancelled_id
    )
    duckdb.connect(str(cancelled_dir / "simulation.duckdb")).close()
    storage.update_scenario_status(workspace.id, scenario.id, "cancelled", cancelled_id)
    assert resolver.resolve(workspace.id, scenario.id).run_id == first_id

    second_id, second_dir = _completed_run(storage, workspace.id, scenario.id, "second")
    assert len({first_dir, failed_dir, cancelled_dir, second_dir}) == 4
    assert all(path.name for path in (first_dir, failed_dir, cancelled_dir, second_dir))
    selected = resolver.resolve(workspace.id, scenario.id)
    assert selected.run_id == second_id
    assert selected.path == second_dir / "simulation.duckdb"
    assert _digest(first_dir / "simulation.duckdb") == first_digest
    assert _digest(failed_dir / "simulation.duckdb") == failed_digest
    assert (cancelled_dir / "simulation.duckdb").is_file()
    assert _digest(shared) == shared_digest
