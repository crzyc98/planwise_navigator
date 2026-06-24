"""Integration tests for simulation log endpoints (001-sim-job-logs).

Tests cover:
- US1: GET /{scenario_id}/runs/{run_id}/logs — paginated log viewer
- US2: SimulationTelemetry.recent_log_lines field
"""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from planalign_api.services.simulation.log_writer import SimulationLogWriter


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANALIGN_API_WORKSPACES_ROOT", str(tmp_path / "workspaces"))
    from importlib import reload
    import planalign_api.config as api_config

    reload(api_config)
    import planalign_api.main as api_main

    reload(api_main)
    from planalign_api.main import app

    return TestClient(app)


@pytest.fixture()
def scenario_with_log(tmp_path, monkeypatch, client):
    """Create a workspace, scenario, and a pre-populated simulation.log."""
    # Create workspace
    ws = client.post("/api/workspaces", json={"name": "Test WS"}).json()
    ws_id = ws["id"]

    # Create scenario
    sc = client.post(
        f"/api/workspaces/{ws_id}/scenarios",
        json={"name": "test-scenario"},
    ).json()
    sc_id = sc["id"]

    # Resolve scenario path and write a fake run with simulation.log
    workspaces_root = Path(tmp_path / "workspaces")
    run_id = str(uuid.uuid4())
    run_dir = workspaces_root / ws_id / "scenarios" / sc_id / "runs" / run_id
    run_dir.mkdir(parents=True)

    # Write metadata so listRuns works
    import json as _json
    from datetime import datetime

    (run_dir / "run_metadata.json").write_text(
        _json.dumps(
            {
                "run_id": run_id,
                "scenario_id": sc_id,
                "scenario_name": "test-scenario",
                "workspace_id": ws_id,
                "started_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
                "duration_seconds": 5.0,
                "start_year": 2025,
                "end_year": 2026,
                "events_generated": 100,
                "seed": 42,
                "status": "completed",
            }
        )
    )

    # Write simulation.log with known content
    writer = SimulationLogWriter(run_dir)
    for i in range(1, 11):
        writer.write_line("debug", f"Log line {i}")
    writer.write_line("warning", "A warning line")
    writer.write_line("error", "An error line")
    writer.close()

    return {"ws_id": ws_id, "sc_id": sc_id, "run_id": run_id}


class TestLogViewerEndpoint:
    def test_returns_200_with_log_lines(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["log_available"] is True
        assert len(body["lines"]) == 12
        assert body["total_lines"] == 12

    def test_lines_have_required_fields(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs")
        first = resp.json()["lines"][0]
        assert "sequence" in first
        assert "timestamp" in first
        assert "severity" in first
        assert "message" in first
        assert first["sequence"] == 1

    def test_log_not_available_for_unknown_run(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(f"/api/scenarios/{r['sc_id']}/runs/nonexistent-run-id/logs")
        assert resp.status_code == 200
        assert resp.json()["log_available"] is False
        assert resp.json()["lines"] == []

    def test_404_for_unknown_scenario(self, client):
        resp = client.get("/api/scenarios/no-such-scenario/runs/some-run/logs")
        assert resp.status_code == 404

    def test_pagination_page_size(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(
            f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs?page=1&page_size=5"
        )
        body = resp.json()
        assert body["page_size"] == 5
        assert len(body["lines"]) == 5
        assert body["has_more"] is True
        assert body["total_lines"] == 12

    def test_pagination_second_page(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(
            f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs?page=2&page_size=5"
        )
        body = resp.json()
        assert len(body["lines"]) == 5
        assert body["lines"][0]["sequence"] == 6

    def test_pagination_last_page(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(
            f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs?page=3&page_size=5"
        )
        body = resp.json()
        assert len(body["lines"]) == 2
        assert body["has_more"] is False

    def test_severity_filter_error_only(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(
            f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs?severity=ERROR"
        )
        body = resp.json()
        assert all(line["severity"] == "ERROR" for line in body["lines"])
        assert len(body["lines"]) == 1

    def test_severity_filter_warning_only(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(
            f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs?severity=WARNING"
        )
        body = resp.json()
        assert all(line["severity"] == "WARNING" for line in body["lines"])

    def test_is_running_false_for_completed(self, client, scenario_with_log):
        r = scenario_with_log
        resp = client.get(f"/api/scenarios/{r['sc_id']}/runs/{r['run_id']}/logs")
        assert resp.json()["is_running"] is False
