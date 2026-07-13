"""Contract and router tests for two-scenario configuration diffs."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.models.comparison import (
    ConfigDelta,
    ConfigDiffResponse,
    ScenarioProvenance,
    WorkforceMetrics,
)
from planalign_api.models.scenario import Scenario
from planalign_api.routers import comparison as comparison_router


def test_comparison_contract_models() -> None:
    workforce = WorkforceMetrics(
        headcount=2,
        active=2,
        terminated=0,
        new_hires=0,
        growth_pct=0.0,
        avg_compensation=105_000.0,
    )
    provenance = ScenarioProvenance(available=False)
    response = ConfigDiffResponse(
        scenario_a="a",
        scenario_b="b",
        scenario_names={"a": "A", "b": "B"},
        differences=[ConfigDelta(path="simulation.x", a=1, b=2, status="changed")],
        unchanged_count=3,
        provenance={"a": provenance, "b": provenance},
        seeds_match=None,
        drift_warning=False,
    )
    assert workforce.avg_compensation == 105_000.0
    assert response.differences[0].status == "changed"
    assert response.provenance["a"].drift_reasons == []


def _scenario(scenario_id: str, status: str = "completed") -> Scenario:
    return Scenario(
        id=scenario_id,
        workspace_id="ws",
        name=scenario_id.upper(),
        status=status,
        created_at=datetime.now(timezone.utc),
    )


def _client(storage: MagicMock, service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(comparison_router.router, prefix="/api/workspaces")
    app.dependency_overrides[comparison_router.get_storage] = lambda: storage
    app.dependency_overrides[
        comparison_router.get_config_diff_service
    ] = lambda: service
    return TestClient(app)


def test_config_diff_endpoint_success() -> None:
    storage = MagicMock()
    storage.get_workspace.return_value = object()
    storage.get_scenario.side_effect = lambda _, scenario_id: _scenario(scenario_id)
    service = MagicMock()
    service.compare.return_value = ConfigDiffResponse(
        scenario_a="a",
        scenario_b="b",
        scenario_names={"a": "A", "b": "B"},
        differences=[],
        unchanged_count=2,
        provenance={
            "a": ScenarioProvenance(available=False),
            "b": ScenarioProvenance(available=False),
        },
        seeds_match=None,
        drift_warning=False,
    )
    response = _client(storage, service).get(
        "/api/workspaces/ws/comparison/config-diff?scenario_a=a&scenario_b=b"
    )
    assert response.status_code == 200
    assert response.json()["scenario_a"] == "a"


def test_config_diff_endpoint_rejects_duplicate_and_incomplete() -> None:
    storage = MagicMock()
    storage.get_workspace.return_value = object()
    storage.get_scenario.side_effect = lambda _, scenario_id: _scenario(
        scenario_id, "failed"
    )
    service = MagicMock()
    client = _client(storage, service)
    duplicate = client.get(
        "/api/workspaces/ws/comparison/config-diff?scenario_a=a&scenario_b=a"
    )
    incomplete = client.get(
        "/api/workspaces/ws/comparison/config-diff?scenario_a=a&scenario_b=b"
    )
    assert duplicate.status_code == 400
    assert incomplete.status_code == 400


def test_config_diff_endpoint_returns_not_found() -> None:
    storage = MagicMock()
    storage.get_workspace.return_value = object()
    storage.get_scenario.return_value = None
    response = _client(storage, MagicMock()).get(
        "/api/workspaces/ws/comparison/config-diff?scenario_a=a&scenario_b=b"
    )
    assert response.status_code == 404


def test_config_diff_endpoint_returns_workspace_not_found() -> None:
    storage = MagicMock()
    storage.get_workspace.return_value = None
    response = _client(storage, MagicMock()).get(
        "/api/workspaces/missing/comparison/config-diff?scenario_a=a&scenario_b=b"
    )
    assert response.status_code == 404
