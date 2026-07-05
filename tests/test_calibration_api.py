"""Fast API tests for the calibration router (Feature 105, US3; issue #380).

Exercises the background-job contract (POST 202 + poll) and error mapping
(guard -> failed job with 409, validation -> 422 at POST) with the
CalibrationRunner mocked, so no dbt build runs.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from planalign_api.routers import calibration as calibration_router
from planalign_orchestrator.calibration_runner import PerYearCompensationResult
from planalign_orchestrator.exceptions import ConfigurationError

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(calibration_router.router, prefix="/api")
    return TestClient(app)


def _await_job(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    """Poll the job endpoint until the background thread reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/calibration/runs/{run_id}")
        assert resp.status_code == 200
        job = resp.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"Calibration job {run_id} did not finish in {timeout}s")


_SAMPLE = [
    PerYearCompensationResult(
        simulation_year=2025,
        avg_compensation=92153.87,
        yoy_growth_pct=None,
        target_growth_pct=3.0,
        growth_delta_pct=None,
        headcount=6967,
        new_hire_avg_comp=70000.0,
        existing_avg_comp=95000.0,
        new_hire_gap=-25000.0,
    ),
    PerYearCompensationResult(
        simulation_year=2026,
        avg_compensation=95884.11,
        yoy_growth_pct=4.0,
        target_growth_pct=3.0,
        growth_delta_pct=1.0,
        headcount=7176,
        new_hire_avg_comp=71000.0,
        existing_avg_comp=96000.0,
        new_hire_gap=-25000.0,
    ),
]


def test_run_returns_per_year_results(client, monkeypatch) -> None:
    monkeypatch.setattr(
        calibration_router.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )
    monkeypatch.setattr(
        calibration_router.CalibrationRunner,
        "run_calibration",
        lambda self: _SAMPLE,
    )

    resp = client.post(
        "/api/calibration/run",
        json={"start_year": 2025, "end_year": 2026, "params": {"cola_rate": 0.03}},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"].startswith("cal_")
    assert body["status"] == "queued"

    job = _await_job(client, body["run_id"])
    assert job["status"] == "completed"
    results = job["results"]
    assert [r["simulation_year"] for r in results] == [2025, 2026]
    assert results[0]["yoy_growth_pct"] is None
    assert results[1]["growth_delta_pct"] == pytest.approx(1.0)


def test_missing_prerequisites_fails_job_with_409(client, monkeypatch) -> None:
    monkeypatch.setattr(
        calibration_router.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )

    def _boom(self):
        raise ConfigurationError("missing DC tables; run a full simulation first")

    monkeypatch.setattr(calibration_router.CalibrationRunner, "run_calibration", _boom)

    resp = client.post(
        "/api/calibration/run", json={"start_year": 2025, "end_year": 2026}
    )
    assert resp.status_code == 202

    job = _await_job(client, resp.json()["run_id"])
    assert job["status"] == "failed"
    assert job["error_status"] == 409
    assert "missing DC tables" in job["error"]


def test_unexpected_failure_fails_job_with_500(client, monkeypatch) -> None:
    monkeypatch.setattr(
        calibration_router.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )

    def _boom(self):
        raise RuntimeError("dbt exploded")

    monkeypatch.setattr(calibration_router.CalibrationRunner, "run_calibration", _boom)

    resp = client.post(
        "/api/calibration/run", json={"start_year": 2025, "end_year": 2026}
    )
    assert resp.status_code == 202

    job = _await_job(client, resp.json()["run_id"])
    assert job["status"] == "failed"
    assert job["error_status"] == 500
    assert "dbt exploded" in job["error"]


def test_unknown_run_id_returns_404(client) -> None:
    resp = client.get("/api/calibration/runs/cal_does_not_exist")
    assert resp.status_code == 404


def test_bad_year_range_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/run", json={"start_year": 2029, "end_year": 2025}
    )
    assert resp.status_code == 422


def test_negative_cola_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/run",
        json={"start_year": 2025, "end_year": 2026, "params": {"cola_rate": -0.1}},
    )
    assert resp.status_code == 422


def test_new_levers_accepted(client, monkeypatch) -> None:
    # workforce_growth_rate + new_hire_age_distribution are real levers now.
    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "__init__", lambda self, run, **kw: None
    )
    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "run_calibration", lambda self: _SAMPLE
    )
    resp = client.post(
        "/api/calibration/run",
        json={
            "start_year": 2025,
            "end_year": 2026,
            "params": {
                "workforce_growth_rate": 0.03,
                "new_hire_age_distribution": [
                    {"age": 25, "weight": 0.5},
                    {"age": 40, "weight": 0.5},
                ],
            },
        },
    )
    assert resp.status_code == 202
    assert _await_job(client, resp.json()["run_id"])["status"] == "completed"


def test_bad_age_distribution_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/run",
        json={
            "start_year": 2025,
            "end_year": 2026,
            "params": {"new_hire_age_distribution": [{"age": 25, "weight": -1.0}]},
        },
    )
    assert resp.status_code == 422


def test_unknown_workspace_returns_404(client, monkeypatch) -> None:
    class _NoWorkspaceStorage:
        def get_workspace(self, workspace_id):
            return None

    client.app.dependency_overrides[
        calibration_router.get_storage
    ] = lambda: _NoWorkspaceStorage()
    try:
        resp = client.post(
            "/api/calibration/run",
            json={"start_year": 2025, "end_year": 2026, "workspace_id": "nope"},
        )
        assert resp.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_workspace_config_flows_to_runner(client, monkeypatch, tmp_path) -> None:
    # A workspace_id (and no explicit config_path) must materialize the
    # workspace base_config as the runner's config file.
    class _Workspace:
        base_config = {
            "simulation": {"target_growth_rate": 0.03},
            "compensation": {"cola_rate": 0.02},
        }

    class _Storage:
        def get_workspace(self, workspace_id):
            return _Workspace()

        def _workspace_path(self, workspace_id):
            return tmp_path

    captured = {}

    def _fake_init(self, run, **kw):
        # Read the materialized config NOW: the worker deletes the temp file
        # once the run completes (issue #379).
        import yaml

        captured["config_path"] = run.config_path
        with open(run.config_path) as f:
            captured["config"] = yaml.safe_load(f)

    monkeypatch.setattr(calibration_router.CalibrationRunner, "__init__", _fake_init)
    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "run_calibration", lambda self: _SAMPLE
    )
    client.app.dependency_overrides[calibration_router.get_storage] = lambda: _Storage()
    try:
        resp = client.post(
            "/api/calibration/run",
            json={"start_year": 2025, "end_year": 2026, "workspace_id": "ws1"},
        )
        assert resp.status_code == 202
        assert _await_job(client, resp.json()["run_id"])["status"] == "completed"
        assert captured["config_path"] is not None
        assert captured["config"]["simulation"]["target_growth_rate"] == 0.03
        # Regression for #379: the materialized temp config must be cleaned up.
        assert not captured["config_path"].exists()
    finally:
        client.app.dependency_overrides.clear()


def test_concurrent_runs_on_same_db_serialize(client, monkeypatch, tmp_path) -> None:
    """Issue #380: two jobs on the same explicit DB queue instead of colliding."""
    import threading

    db_path = tmp_path / "target.duckdb"
    active = {"count": 0, "max": 0}
    gate = threading.Lock()

    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "__init__", lambda self, run, **kw: None
    )

    def _slow_build(self):
        with gate:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
        time.sleep(0.1)
        with gate:
            active["count"] -= 1
        return _SAMPLE

    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "run_calibration", _slow_build
    )

    body = {"start_year": 2025, "end_year": 2026, "database_path": str(db_path)}
    r1 = client.post("/api/calibration/run", json=body)
    r2 = client.post("/api/calibration/run", json=body)
    assert r1.status_code == 202 and r2.status_code == 202

    j1 = _await_job(client, r1.json()["run_id"])
    j2 = _await_job(client, r2.json()["run_id"])
    assert j1["status"] == j2["status"] == "completed"
    # The per-DB lock must have prevented overlapping builds.
    assert active["max"] == 1


def test_optimize_returns_outcome(client, monkeypatch) -> None:
    from planalign_orchestrator.calibration_optimizer import (
        AutoCalibrationResult,
        OptimizationIteration,
    )
    from planalign_orchestrator.calibration_runner import CalibrationParameterSet

    outcome = AutoCalibrationResult(
        converged=True,
        message="Converged in 3 iteration(s)",
        best_params=CalibrationParameterSet(cola_rate=0.028, merit_budget=0.043),
        achieved_comp_growth_pct=4.01,
        target_comp_growth_pct=4.0,
        iterations=[
            OptimizationIteration(
                iteration=1,
                cola_rate=0.02,
                merit_budget=0.035,
                achieved_growth_pct=3.2,
                error_pct=-0.8,
            )
        ],
        results=_SAMPLE,
    )
    monkeypatch.setattr(
        calibration_router.AutoCalibrator,
        "__init__",
        lambda self, run, settings, **kw: None,
    )
    monkeypatch.setattr(
        calibration_router.AutoCalibrator, "optimize", lambda self: outcome
    )

    resp = client.post(
        "/api/calibration/optimize",
        json={
            "start_year": 2025,
            "end_year": 2026,
            "settings": {
                "target_workforce_growth": 0.03,
                "target_comp_growth": 0.04,
            },
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"].startswith("autocal_")

    job = _await_job(client, body["run_id"])
    assert job["status"] == "completed"
    assert job["outcome"]["converged"] is True
    assert job["outcome"]["best_params"]["cola_rate"] == pytest.approx(0.028)


def test_optimize_single_year_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/optimize",
        json={
            "start_year": 2025,
            "end_year": 2025,
            "settings": {
                "target_workforce_growth": 0.03,
                "target_comp_growth": 0.04,
            },
        },
    )
    assert resp.status_code == 422
    assert "two-year range" in resp.json()["detail"]


def test_job_level_compensation_with_name_is_accepted(client, monkeypatch) -> None:
    # Regression: ranges include a string `name`; must not 422 (was Dict[str,float]).
    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "__init__", lambda self, run, **kw: None
    )
    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "run_calibration", lambda self: _SAMPLE
    )
    resp = client.post(
        "/api/calibration/run",
        json={
            "start_year": 2025,
            "end_year": 2026,
            "params": {
                "job_level_compensation": [
                    {
                        "level": 1,
                        "name": "Staff",
                        "min_compensation": 60000,
                        "max_compensation": 90000,
                    }
                ]
            },
        },
    )
    assert resp.status_code == 202
    assert _await_job(client, resp.json()["run_id"])["status"] == "completed"
