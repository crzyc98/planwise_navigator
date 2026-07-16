"""HTTP contract tests for the read-only timeline router."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.routers.timeline import get_storage, get_timeline_service, router
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.timeline_service import TimelineService

pytest_plugins = ["tests.fixtures.database"]


class _Storage:
    def get_workspace(self, workspace_id: str):
        return object() if workspace_id == "ws" else None

    def get_scenario(self, workspace_id: str, scenario_id: str):
        return object() if workspace_id == "ws" and scenario_id == "scenario" else None


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve(self, workspace_id: str, scenario_id: str) -> ResolvedDatabasePath:
        return ResolvedDatabasePath(path=self.path, source="scenario")


@pytest.fixture
def client(timeline_db: Path) -> TestClient:
    storage = _Storage()
    service = TimelineService(storage, _Resolver(timeline_db))  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(router, prefix="/api/workspaces")
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_timeline_service] = lambda: service
    return TestClient(app)


@pytest.mark.fast
def test_search_and_timeline_contract(client: TestClient) -> None:
    search = client.get(
        "/api/workspaces/ws/scenarios/scenario/employees", params={"q": "emp_"}
    )
    timeline = client.get(
        "/api/workspaces/ws/scenarios/scenario/employees/emp_a/timeline"
    )

    assert search.status_code == 200
    assert search.json()["total"] == 2
    assert timeline.status_code == 200
    body = timeline.json()
    assert body["employee"]["employee_id"] == "EMP_A"
    assert body["available_years"] == [2025, 2026, 2027]
    assert body["years"][0]["events"][0]["event_id"] == "e-hire"


@pytest.mark.fast
def test_not_found_is_200_and_invalid_scope_is_404(client: TestClient) -> None:
    missing_employee = client.get(
        "/api/workspaces/ws/scenarios/scenario/employees/missing/timeline"
    )
    missing_workspace = client.get(
        "/api/workspaces/nope/scenarios/scenario/employees", params={"q": "EMP"}
    )

    assert missing_employee.status_code == 200
    assert missing_employee.json()["employee"] is None
    assert missing_workspace.status_code == 404


@pytest.mark.fast
def test_parameter_bounds_and_read_only_surface(client: TestClient) -> None:
    assert (
        client.get(
            "/api/workspaces/ws/scenarios/scenario/employees", params={"page_size": 201}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/workspaces/ws/scenarios/scenario/employees").status_code
        == 405
    )
