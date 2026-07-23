"""Fast tests for GET /api/scenarios/{scenario_id}/run/telemetry (feature 094).

Contract: specs/094-live-run-dashboard/contracts/rest-telemetry-snapshot.md
"""

import pytest
from fastapi.testclient import TestClient

import planalign_api.services.telemetry_service as telemetry_module
from planalign_api.services.telemetry_service import TelemetryService

pytestmark = [pytest.mark.fast]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANALIGN_API_WORKSPACES_ROOT", str(tmp_path / "workspaces"))
    from importlib import reload

    import planalign_api.config as api_config

    reload(api_config)
    import planalign_api.main as api_main

    reload(api_main)
    from planalign_api.main import app

    # Fresh telemetry singleton per test
    telemetry_module._telemetry_service = TelemetryService()
    return TestClient(app)


@pytest.fixture()
def scenario(client):
    ws = client.post("/api/workspaces", json={"name": "Test WS"}).json()
    sc = client.post(
        f"/api/workspaces/{ws['id']}/scenarios", json={"name": "test-scenario"}
    ).json()
    return {"workspace_id": ws["id"], "scenario_id": sc["id"]}


def test_unknown_scenario_returns_404(client):
    response = client.get("/api/scenarios/does-not-exist/run/telemetry")
    assert response.status_code == 404


def test_not_run_scenario_returns_null_telemetry(client, scenario):
    response = client.get(f"/api/scenarios/{scenario['scenario_id']}/run/telemetry")
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["run_id"] is None
    assert body["run"]["status"] == "not_run"
    assert body["telemetry"] is None


def test_active_run_returns_full_snapshot(client, scenario):
    svc = telemetry_module.get_telemetry_service()
    svc.start_run(
        "run-1",
        scenario_id=scenario["scenario_id"],
        start_year=2025,
        total_years=3,
    )
    svc.apply_update(
        "run-1", progress=42, current_stage="EVENT_GENERATION", current_year=2026
    )
    svc.apply_structured_record(
        "run-1",
        {
            "record": "year_completed",
            "year": 2025,
            "duration_seconds": 10.0,
            "event_counts": {"HIRE": 5},
            "cumulative_counts": {"HIRE": 5},
        },
    )

    response = client.get(f"/api/scenarios/{scenario['scenario_id']}/run/telemetry")
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["run_id"] == "run-1"
    assert body["run"]["status"] == "running"
    snap = body["telemetry"]
    assert snap["progress"] == 42
    assert snap["event_counts"]["by_type"] == {"HIRE": 5}
    assert snap["milestones"][0]["kind"] == "run_started"
    assert any(m["kind"] == "year_completed" for m in snap["milestones"])


def test_terminal_state_still_served(client, scenario):
    svc = telemetry_module.get_telemetry_service()
    svc.start_run(
        "run-2", scenario_id=scenario["scenario_id"], start_year=2025, total_years=1
    )
    svc.set_terminal("run-2", "failed", message="boom")

    body = client.get(f"/api/scenarios/{scenario['scenario_id']}/run/telemetry").json()
    assert body["run"]["status"] == "failed"
    assert body["telemetry"]["status"] == "failed"
    assert body["telemetry"]["milestones"][-1]["kind"] == "terminal"


def test_api_restart_returns_status_without_telemetry(client, scenario, tmp_path):
    """Scenario marked running on disk but no in-memory state (API restarted)."""
    import uuid

    from planalign_api.storage.workspace_storage import WorkspaceStorage
    import planalign_api.config as api_config

    storage = WorkspaceStorage(api_config.get_settings().workspaces_root)
    run_id = str(uuid.uuid4())
    storage.update_scenario_status(
        scenario["workspace_id"], scenario["scenario_id"], "running", run_id
    )

    body = client.get(f"/api/scenarios/{scenario['scenario_id']}/run/telemetry").json()
    assert body["run"]["status"] == "running"
    assert body["run"]["run_id"] == run_id
    assert body["telemetry"] is None
