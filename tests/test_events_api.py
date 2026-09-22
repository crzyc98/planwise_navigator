"""HTTP contract tests for the read-only event explorer router."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.routers.events import get_events_service, get_storage, router
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.events_service import EventExplorerService

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
        return ResolvedDatabasePath(path=self.path, source="run", run_id="run-123")


@pytest.fixture
def client(events_explorer_db: Path) -> TestClient:
    storage = _Storage()
    service = EventExplorerService(storage, _Resolver(events_explorer_db))  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(router, prefix="/api/workspaces")
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_events_service] = lambda: service
    return TestClient(app)


def _url() -> str:
    return "/api/workspaces/ws/scenarios/scenario/events"


@pytest.mark.fast
def test_lists_events_in_deterministic_order_with_resolved_database_metadata(
    client: TestClient,
) -> None:
    response = client.get(_url())

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 8
    assert body["run_id"] == "run-123"
    assert body["database_source"] == "run"
    assert [event["event_id"] for event in body["events"]] == [
        "evt-a-elig",
        "evt-a-hire",
        "evt-b-hire",
        "evt-a-enroll",
        "evt-b-raise",
        "evt-a-escalate",
        "evt-c-term",
        "evt-a-raise",
    ]


@pytest.mark.fast
def test_filters_events_with_and_semantics(client: TestClient) -> None:
    assertions = [
        ({"simulation_year": 2027}, ["evt-a-raise"]),
        ({"event_type": "HIRE"}, ["evt-a-hire", "evt-b-hire"]),
        ({"event_category": "COMPENSATION"}, ["evt-b-raise", "evt-a-raise"]),
        ({"employee_id": "emp_b"}, ["evt-b-hire", "evt-b-raise"]),
        (
            {
                "simulation_year": 2026,
                "event_type": "deferral_escalation",
                "employee_id": "EMP_A",
            },
            ["evt-a-escalate"],
        ),
    ]

    for params, event_ids in assertions:
        response = client.get(_url(), params=params)
        assert response.status_code == 200
        assert [event["event_id"] for event in response.json()["events"]] == event_ids


@pytest.mark.fast
def test_no_matching_events_is_empty_success(client: TestClient) -> None:
    response = client.get(_url(), params={"event_type": "unknown"})

    assert response.status_code == 200
    assert response.json()["events"] == []
    assert response.json()["total"] == 0


@pytest.mark.fast
def test_invalid_scope_is_not_found(client: TestClient) -> None:
    missing_workspace = client.get("/api/workspaces/nope/scenarios/scenario/events")
    missing_scenario = client.get("/api/workspaces/ws/scenarios/nope/events")

    assert missing_workspace.status_code == 404
    assert missing_scenario.status_code == 404


@pytest.mark.fast
def test_parameter_bounds_and_read_only_surface(client: TestClient) -> None:
    assert client.get(_url(), params={"page_size": 0}).status_code == 422
    assert client.get(_url(), params={"page_size": 201}).status_code == 422
    assert client.get(_url(), params={"page": 0}).status_code == 422
    assert client.post(_url()).status_code == 405


@pytest.mark.fast
def test_pagination_has_no_gaps_or_overlaps(client: TestClient) -> None:
    unpaged = client.get(_url()).json()
    pages = [
        client.get(_url(), params={"page_size": 2, "page": page}).json()
        for page in (1, 2, 3, 4)
    ]

    assert all(page["total"] == unpaged["total"] for page in pages)
    paged_ids = [event["event_id"] for page in pages for event in page["events"]]
    assert len(paged_ids) == len(set(paged_ids))
    assert paged_ids == [event["event_id"] for event in unpaged["events"]]


@pytest.mark.fast
def test_event_response_includes_unredacted_pii(client: TestClient) -> None:
    response = client.get(_url(), params={"event_type": "hire"})

    assert response.status_code == 200
    event = response.json()["events"][0]
    assert event["employee_ssn"] == "123-45-6789"
    assert event["compensation_amount"] == 80000.0
