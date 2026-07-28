"""API contract tests for the multi-year forfeitures endpoint (issue #489)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pytest

from planalign_api import config as api_config
from planalign_api.constants import MAX_SCENARIO_COMPARISON
from planalign_api.main import create_app
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import vesting as vesting_router
from planalign_api.services.vesting_service import VestingService
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = [pytest.mark.fast]

ENDPOINT = "/api/workspaces/{workspace_id}/analytics/vesting/forfeitures"

SNAPSHOT_DDL = """
    CREATE TABLE fct_workforce_snapshot (
        employee_id VARCHAR,
        simulation_year INTEGER,
        employment_status VARCHAR,
        employee_hire_date DATE,
        termination_date DATE,
        current_tenure INTEGER,
        tenure_band VARCHAR,
        annual_hours_worked INTEGER,
        total_employer_contributions DECIMAL(12, 2)
    )
"""

ROWS = """
    INSERT INTO fct_workforce_snapshot VALUES
        ('e1', 2025, 'ACTIVE',     DATE '2022-01-01', NULL,              3, '2-4', 2080, 1000.00),
        ('e1', 2026, 'TERMINATED', DATE '2022-01-01', DATE '2026-06-30', 4, '2-4', 2080,    0.00)
"""


@dataclass
class _Resolved:
    path: Path
    exists: bool


class _StubResolver:
    def __init__(self, paths: dict[str, Path]):
        self._paths = paths

    def resolve(self, workspace_id: str, scenario_id: str) -> _Resolved:
        path = self._paths.get(scenario_id, Path("/nonexistent.duckdb"))
        return _Resolved(path=path, exists=path.exists())


def _build_db(path: Path) -> Path:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(SNAPSHOT_DDL)
        conn.execute(ROWS)
    finally:
        conn.close()
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Workspace with two completed scenarios, each backed by its own database."""
    from fastapi.testclient import TestClient

    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)

    storage = WorkspaceStorage(settings.workspaces_root)
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    scenarios = []
    paths: dict[str, Path] = {}
    for name in ("Baseline", "High Growth"):
        scenario = storage.create_scenario(workspace.id, ScenarioCreate(name=name))
        storage.update_scenario_status(workspace.id, scenario.id, "completed")
        paths[scenario.id] = _build_db(tmp_path / f"{scenario.id}.duckdb")
        scenarios.append(scenario)

    app = create_app()

    def _service() -> VestingService:
        service = VestingService(storage=storage)
        service.db_resolver = _StubResolver(paths)
        return service

    app.dependency_overrides[vesting_router.get_vesting_service] = _service
    return TestClient(app), workspace, scenarios


def test_multi_scenario_multi_year_response_shape(env):
    """Two scenarios, every year, one schedule — the shape the Vesting page needs."""
    client, workspace, scenarios = env
    ids = ",".join(s.id for s in scenarios)

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": ids, "schedule_type": "graded_5_year"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schedule"]["schedule_type"] == "graded_5_year"
    assert body["years"] == [2025, 2026]
    assert body["skipped"] == []
    assert len(body["scenarios"]) == 2

    series = body["scenarios"][0]
    assert {"scenario_id", "scenario_name", "years"} <= set(series)
    assert [row["simulation_year"] for row in series["years"]] == [2025, 2026]
    assert series["total_forfeited"] == 200.0


def test_first_year_flagged_in_the_payload(env):
    """The first year must be distinguishable from a measured zero over the wire."""
    client, workspace, scenarios = env

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": scenarios[0].id, "schedule_type": "graded_5_year"},
    )

    rows = response.json()["scenarios"][0]["years"]
    assert rows[0]["has_prior_year_basis"] is False
    assert rows[1]["has_prior_year_basis"] is True


def test_single_scenario_is_allowed(env):
    """Unlike dc-plan/compare, one scenario is the primary use case, not an error."""
    client, workspace, scenarios = env

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": scenarios[0].id, "schedule_type": "cliff_1_year"},
    )

    assert response.status_code == 200
    assert len(response.json()["scenarios"]) == 1


def test_hours_credit_parameters_are_accepted(env):
    client, workspace, scenarios = env

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={
            "scenarios": scenarios[0].id,
            "schedule_type": "graded_5_year",
            "require_hours_credit": "true",
            "hours_threshold": 1500,
        },
    )

    assert response.status_code == 200
    schedule = response.json()["schedule"]
    assert schedule["require_hours_credit"] is True
    assert schedule["hours_threshold"] == 1500


def test_unknown_workspace_is_404(env):
    client, _workspace, scenarios = env

    response = client.get(
        ENDPOINT.format(workspace_id="nope"),
        params={"scenarios": scenarios[0].id, "schedule_type": "graded_5_year"},
    )

    assert response.status_code == 404


def test_unknown_scenario_is_404(env):
    client, workspace, _scenarios = env

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": "missing-scenario", "schedule_type": "graded_5_year"},
    )

    assert response.status_code == 404


def test_incomplete_scenario_is_400(env, tmp_path):
    """Mirrors the Cost Comparison contract: non-completed scenarios are rejected."""
    client, workspace, _scenarios = env
    storage = WorkspaceStorage(api_config.settings.workspaces_root)
    pending = storage.create_scenario(workspace.id, ScenarioCreate(name="Pending"))

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": pending.id, "schedule_type": "graded_5_year"},
    )

    assert response.status_code == 400


def test_empty_selection_is_400(env):
    client, workspace, _scenarios = env

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": " , ", "schedule_type": "graded_5_year"},
    )

    assert response.status_code == 400


def test_duplicate_scenarios_are_400(env):
    client, workspace, scenarios = env
    duplicated = f"{scenarios[0].id},{scenarios[0].id}"

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": duplicated, "schedule_type": "graded_5_year"},
    )

    assert response.status_code == 400


def test_too_many_scenarios_is_400(env):
    client, workspace, scenarios = env
    too_many = ",".join(f"s{index}" for index in range(MAX_SCENARIO_COMPARISON + 1))

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": too_many, "schedule_type": "graded_5_year"},
    )

    assert response.status_code == 400


def test_invalid_schedule_type_is_422(env):
    client, workspace, scenarios = env

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={"scenarios": scenarios[0].id, "schedule_type": "not_a_schedule"},
    )

    assert response.status_code == 422


def test_unbuilt_scenario_database_is_skipped_not_fatal(env, tmp_path):
    """A completed scenario whose database is missing must not fail the request."""
    client, workspace, scenarios = env
    storage = WorkspaceStorage(api_config.settings.workspaces_root)
    ghost = storage.create_scenario(workspace.id, ScenarioCreate(name="Ghost"))
    storage.update_scenario_status(workspace.id, ghost.id, "completed")

    response = client.get(
        ENDPOINT.format(workspace_id=workspace.id),
        params={
            "scenarios": f"{scenarios[0].id},{ghost.id}",
            "schedule_type": "graded_5_year",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["scenario_id"] for item in body["scenarios"]] == [scenarios[0].id]
    assert [item["scenario_id"] for item in body["skipped"]] == [ghost.id]
    assert body["skipped"][0]["reason"]
