"""Fast API tests for the calibration router (Feature 105, US3; issue #380).

Exercises the background-job contract (POST 202 + poll) and error mapping
(guard -> failed job with 409, validation -> 422 at POST) with the
CalibrationRunner mocked, so no dbt build runs.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from planalign_api.routers import calibration as calibration_router
from planalign_api.services.calibration_jobs import JobRunner, JobStore
from planalign_api.services.calibration_process import ProcessRegistry
from planalign_api.services.provenance.capture import config_fingerprint, sha256_file
from planalign_orchestrator import calibration_worker
from planalign_orchestrator.calibration_runner import PerYearCompensationResult
from planalign_orchestrator.exceptions import ConfigurationError

pytestmark = [pytest.mark.fast]


def _make_workspace_storage(
    root: Path,
    *,
    workspace_id: str = "ws1",
    start_year: int = 2025,
    end_year: int = 2026,
) -> object:
    ws_dir = root / workspace_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    census = ws_dir / "census.parquet"
    census.write_bytes(b"pii-safe-test-census")
    run_id = str(uuid4())
    source_db = ws_dir / "source.duckdb"
    source_db.write_bytes(b"source-db")
    base_config = {
        "setup": {"census_parquet_path": "census.parquet"},
        "simulation": {
            "start_year": start_year,
            "end_year": end_year,
            "random_seed": 42,
            "target_growth_rate": 0.03,
        },
        "compensation": {"cola_rate": 0.02},
    }
    effective = {**base_config, "setup": {"census_parquet_path": str(census.resolve())}}
    (ws_dir / "provenance.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "capture_state": "completed",
                "run_identity": {
                    "workspace_id": workspace_id,
                    "intended_start_year": start_year,
                    "intended_end_year": end_year,
                },
                "configuration": {"fingerprint": config_fingerprint(effective)},
                "random_seed": 42,
                "census_input": {"sha256": sha256_file(census)[0]},
            }
        ),
        encoding="utf-8",
    )

    class _Storage:
        workspaces_root = root

        def get_workspace(self, wid: str):
            return (
                SimpleNamespace(base_config=base_config)
                if wid == workspace_id
                else None
            )

        def _workspace_path(self, wid: str) -> Path:
            return root / wid

        def get_merged_config(self, wid: str, sid: str):
            return dict(base_config) if wid == workspace_id else None

        def get_scenario(self, wid: str, sid: str):
            return SimpleNamespace(id=sid) if wid == workspace_id else None

        def list_scenarios(self, wid: str):
            return [SimpleNamespace(id="scenario-1")] if wid == workspace_id else []

        def get_scenario_read_context(self, wid: str, sid: str):
            return SimpleNamespace(database_path=source_db, result_run_id=run_id)

    return _Storage()


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    from fastapi import FastAPI

    store = JobStore(tmp_path / "jobs")
    storage = _make_workspace_storage(tmp_path / "workspaces")

    def command(directory: Path) -> list[str]:
        # Existing engine mocks exercise JSON transport without invoking dbt.
        code = calibration_worker.main(directory)
        return [sys.executable, "-c", f"raise SystemExit({code})"]

    runner = JobRunner(store, ProcessRegistry(), command)
    monkeypatch.setattr(calibration_router, "get_job_store", lambda: store)
    monkeypatch.setattr(calibration_router, "get_job_runner", lambda: runner)
    app = FastAPI()
    app.include_router(calibration_router.router, prefix="/api")
    app.dependency_overrides[calibration_router.get_storage] = lambda: storage
    return TestClient(app)


def _await_job(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
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
        calibration_worker.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner,
        "run_calibration",
        lambda self: _SAMPLE,
    )

    resp = client.post(
        "/api/calibration/run",
        json={
            "workspace_id": "ws1",
            "start_year": 2025,
            "end_year": 2026,
            "params": {"cola_rate": 0.03},
        },
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
        calibration_worker.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )

    def _boom(self):
        raise ConfigurationError("missing DC tables; run a full simulation first")

    monkeypatch.setattr(calibration_worker.CalibrationRunner, "run_calibration", _boom)

    resp = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    )
    assert resp.status_code == 202

    job = _await_job(client, resp.json()["run_id"])
    assert job["status"] == "failed"
    assert job["error_status"] == 409
    assert "missing DC tables" in job["error"]


def test_unexpected_failure_fails_job_with_500(client, monkeypatch) -> None:
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )

    def _boom(self):
        raise RuntimeError("dbt exploded")

    monkeypatch.setattr(calibration_worker.CalibrationRunner, "run_calibration", _boom)

    resp = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2025, "end_year": 2026},
    )
    assert resp.status_code == 202

    job = _await_job(client, resp.json()["run_id"])
    assert job["status"] == "failed"
    assert job["error_status"] == 500
    # Raw exception text is never exposed; only a stable message + error ID.
    assert "dbt exploded" not in job["error"]
    assert "error_id:" in job["error"]


def test_unknown_run_id_returns_404(client) -> None:
    resp = client.get("/api/calibration/runs/cal_does_not_exist")
    assert resp.status_code == 404


def test_bad_year_range_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/run",
        json={"workspace_id": "ws1", "start_year": 2029, "end_year": 2025},
    )
    assert resp.status_code == 422


def test_negative_cola_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/run",
        json={
            "workspace_id": "ws1",
            "start_year": 2025,
            "end_year": 2026,
            "params": {"cola_rate": -0.1},
        },
    )
    assert resp.status_code == 422


def test_new_levers_accepted(client, monkeypatch) -> None:
    # workforce_growth_rate + new_hire_age_distribution are real levers now.
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner, "__init__", lambda self, run, **kw: None
    )
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner, "run_calibration", lambda self: _SAMPLE
    )
    resp = client.post(
        "/api/calibration/run",
        json={
            "workspace_id": "ws1",
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
            "workspace_id": "ws1",
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

    client.app.dependency_overrides[calibration_router.get_storage] = (
        lambda: _NoWorkspaceStorage()
    )
    try:
        resp = client.post(
            "/api/calibration/run",
            json={"start_year": 2025, "end_year": 2026, "workspace_id": "nope"},
        )
        assert resp.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "stale_scenario,stale_source", [(False, False), (True, False), (True, True)]
)
def test_workspace_config_flows_to_runner(
    client, monkeypatch, tmp_path, stale_scenario, stale_source
) -> None:
    # A workspace target materializes its config and copies only a completed
    # run whose config/census/seed/horizon provenance matches.
    import json
    from types import SimpleNamespace
    from uuid import uuid4

    from planalign_api.services.provenance.capture import (
        config_fingerprint,
        sha256_file,
    )

    census = tmp_path / "census.parquet"
    census.write_bytes(b"pii-safe-test-census")
    run_id = str(uuid4())
    source_db = tmp_path / "source.duckdb"
    source_db.write_bytes(b"source-db")

    class _Workspace:
        base_config = {
            "setup": {"census_parquet_path": "census.parquet"},
            "simulation": {
                "start_year": 2025,
                "end_year": 2026,
                "random_seed": 42,
                "target_growth_rate": 0.03,
            },
            "compensation": {"cola_rate": 0.02},
        }

    effective = dict(_Workspace.base_config)
    effective["setup"] = {"census_parquet_path": str(census.resolve())}
    (tmp_path / "provenance.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "capture_state": "completed",
                "run_identity": {
                    "workspace_id": "ws1",
                    "intended_start_year": 2025,
                    "intended_end_year": 2026,
                },
                "configuration": {"fingerprint": config_fingerprint(effective)},
                "random_seed": 42,
                "census_input": {"sha256": sha256_file(census)[0]},
            }
        )
    )

    if stale_source:
        census.write_bytes(b"replacement-census-after-source-run")

    class _Storage:
        def get_workspace(self, workspace_id):
            return _Workspace()

        def _workspace_path(self, workspace_id):
            return tmp_path

        def get_merged_config(self, workspace_id, scenario_id):
            return {
                **_Workspace.base_config,
                "setup": {"census_parquet_path": str(tmp_path / "old-import.parquet")},
            }

        def get_scenario(self, workspace_id, scenario_id):
            return SimpleNamespace(id="scenario-1")

        def list_scenarios(self, workspace_id):
            return [SimpleNamespace(id="scenario-1")]

        def get_scenario_read_context(self, workspace_id, scenario_id):
            return SimpleNamespace(
                database_path=source_db,
                result_run_id=run_id,
            )

    captured = {}

    def _fake_init(self, run, **kw):
        # Read the materialized config NOW: the worker deletes the temp file
        # once the run completes (issue #379).
        import yaml

        captured["config_path"] = run.config_path
        captured["database_path"] = run.database_path
        with open(run.config_path) as f:
            captured["config"] = yaml.safe_load(f)

    monkeypatch.setattr(calibration_worker.CalibrationRunner, "__init__", _fake_init)
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner, "run_calibration", lambda self: _SAMPLE
    )
    client.app.dependency_overrides[calibration_router.get_storage] = lambda: _Storage()
    try:
        resp = client.post(
            "/api/calibration/run",
            json={
                "start_year": 2025,
                "end_year": 2026,
                "workspace_id": "ws1",
                "scenario_id": "scenario-1" if stale_scenario else None,
            },
        )
        if stale_source:
            assert resp.status_code == 409
            assert "No completed simulation matches" in resp.json()["detail"]
            assert not captured
            return
        assert resp.status_code == 202
        assert _await_job(client, resp.json()["run_id"])["status"] == "completed"
        assert captured["config_path"] is not None
        assert captured["config"]["simulation"]["target_growth_rate"] == 0.03
        assert captured["config"]["setup"]["census_parquet_path"] == str(
            census.resolve()
        )
        # Regression for #379: the materialized temp config must be cleaned up.
        assert not captured["config_path"].exists()
        assert not captured["database_path"].exists()
    finally:
        client.app.dependency_overrides.clear()


def test_provenance_match_rejects_other_workspace_and_stale_census(tmp_path) -> None:
    import json

    manifest = tmp_path / "provenance.json"
    manifest.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "capture_state": "completed",
                "run_identity": {
                    "workspace_id": "workspace-b",
                    "intended_start_year": 2025,
                    "intended_end_year": 2026,
                },
                "configuration": {"fingerprint": "a" * 64},
                "random_seed": 42,
                "census_input": {"sha256": "old-census"},
            }
        )
    )

    matches, _ = calibration_router._manifest_matches(
        manifest,
        workspace_id="workspace-a",
        expected_config="a" * 64,
        expected_census="new-census",
        expected_seed=42,
        start_year=2025,
        end_year=2026,
    )

    assert not matches

    horizon_matches, _ = calibration_router._manifest_matches(
        manifest,
        workspace_id="workspace-b",
        expected_config="a" * 64,
        expected_census="old-census",
        expected_seed=42,
        start_year=2025,
        end_year=2027,
    )
    assert not horizon_matches


def test_scenario_target_uses_merged_config() -> None:
    class _Storage:
        def get_workspace(self, workspace_id):
            return object()

        def get_merged_config(self, workspace_id, scenario_id):
            return {"scenario_marker": scenario_id}

    config = calibration_router._effective_workspace_config(
        "workspace", "scenario-override", _Storage()
    )

    assert config == {"scenario_marker": "scenario-override"}


def test_concurrent_workspace_runs_serialize(client, monkeypatch) -> None:
    """Concurrent calibration runs queue cleanly without overlapping."""
    import threading

    active = {"count": 0, "max": 0}
    gate = threading.Lock()

    monkeypatch.setattr(
        calibration_worker.CalibrationRunner, "__init__", lambda self, run, **kw: None
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
        calibration_worker.CalibrationRunner, "run_calibration", _slow_build
    )

    body = {"workspace_id": "ws1", "start_year": 2025, "end_year": 2026}
    r1 = client.post("/api/calibration/run", json=body)
    r2 = client.post("/api/calibration/run", json=body)
    assert r1.status_code == 202 and r2.status_code == 202

    j1 = _await_job(client, r1.json()["run_id"])
    j2 = _await_job(client, r2.json()["run_id"])
    assert j1["status"] == j2["status"] == "completed"
    assert active["max"] == 1


@pytest.mark.parametrize(
    "endpoint", ["/api/calibration/run", "/api/calibration/optimize"]
)
@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"workspace_id": None},
        {"workspace_id": ""},
        {"config_path": "/tmp/custom.yaml", "database_path": "/tmp/custom.duckdb"},
    ],
)
def test_calibration_requires_workspace_id(client, endpoint: str, extra: dict) -> None:
    payload: dict = {"start_year": 2025, "end_year": 2026, **extra}
    if endpoint.endswith("/optimize"):
        payload["settings"] = {
            "target_workforce_growth": 0.03,
            "target_comp_growth": 0.04,
        }
    resp = client.post(endpoint, json=payload)
    assert resp.status_code == 422


@pytest.mark.parametrize("kind", ["run", "optimize"])
def test_client_supplied_paths_are_not_touched(
    client, monkeypatch, tmp_path, kind: str
) -> None:
    from planalign_orchestrator.calibration_optimizer import (
        AutoCalibrationResult,
        AutoCalibrationSettings,
    )
    from planalign_orchestrator.calibration_runner import CalibrationParameterSet

    sentinel_cfg = tmp_path / "external_config.yaml"
    sentinel_cfg.write_text("sentinel: true\n", encoding="utf-8")
    sentinel_db = tmp_path / "external.duckdb"
    sentinel_db.write_bytes(b"sentinel-db")
    captured: dict = {}

    if kind == "run":

        def _fake_run_init(self, run, **kw):
            captured["config_path"] = run.config_path
            captured["database_path"] = run.database_path

        monkeypatch.setattr(
            calibration_worker.CalibrationRunner, "__init__", _fake_run_init
        )
        monkeypatch.setattr(
            calibration_worker.CalibrationRunner,
            "run_calibration",
            lambda self: _SAMPLE,
        )
        endpoint = "/api/calibration/run"
        payload: dict = {
            "workspace_id": "ws1",
            "start_year": 2025,
            "end_year": 2026,
            "config_path": str(sentinel_cfg),
            "database_path": str(sentinel_db),
        }
    else:
        outcome = AutoCalibrationResult(
            settings=AutoCalibrationSettings(
                target_workforce_growth=0.03, target_comp_growth=0.04
            ),
            starting_params=CalibrationParameterSet(),
            converged=True,
            status="converged",
            reason="done",
            message="done",
            best_params=CalibrationParameterSet(),
            achieved_comp_growth_pct=4.0,
            target_comp_growth_pct=4.0,
            max_abs_error_pct=0.0,
            start_year=2025,
            end_year=2026,
            iterations=[],
            results=_SAMPLE,
        )

        def _fake_opt_init(self, run, settings, **kw):
            captured["config_path"] = run.config_path
            captured["database_path"] = run.database_path

        monkeypatch.setattr(
            calibration_worker.AutoCalibrator, "__init__", _fake_opt_init
        )
        monkeypatch.setattr(
            calibration_worker.AutoCalibrator, "optimize", lambda self: outcome
        )
        endpoint = "/api/calibration/optimize"
        payload = {
            "workspace_id": "ws1",
            "start_year": 2025,
            "end_year": 2026,
            "config_path": str(sentinel_cfg),
            "database_path": str(sentinel_db),
            "settings": {
                "target_workforce_growth": 0.03,
                "target_comp_growth": 0.04,
            },
        }

    resp = client.post(endpoint, json=payload)
    assert resp.status_code == 202
    assert _await_job(client, resp.json()["run_id"])["status"] == "completed"
    assert captured["config_path"] != sentinel_cfg
    assert captured["database_path"] != sentinel_db
    assert sentinel_cfg.read_text(encoding="utf-8") == "sentinel: true\n"
    assert sentinel_db.read_bytes() == b"sentinel-db"


@pytest.mark.parametrize("status", ["converged", "not_converged", "infeasible"])
def test_optimize_returns_outcome(client, monkeypatch, status: str) -> None:
    from planalign_orchestrator.calibration_optimizer import (
        AutoCalibrationResult,
        AutoCalibrationSettings,
        OptimizationIteration,
    )
    from planalign_orchestrator.calibration_runner import CalibrationParameterSet

    outcome = AutoCalibrationResult(
        settings=AutoCalibrationSettings(
            target_workforce_growth=0.03, target_comp_growth=0.04
        ),
        starting_params=CalibrationParameterSet(),
        converged=status == "converged",
        status=status,
        reason="Analyst-facing explanation.",
        message="Converged in 3 iteration(s)",
        best_params=CalibrationParameterSet(cola_rate=0.028, merit_budget=0.043),
        achieved_comp_growth_pct=4.01,
        target_comp_growth_pct=4.0,
        max_abs_error_pct=0.8,
        start_year=2025,
        end_year=2026,
        iterations=[
            OptimizationIteration(
                iteration=1,
                cola_rate=0.02,
                merit_budget=0.035,
                achieved_growth_pct=3.2,
                error_pct=-0.8,
                max_abs_error_pct=0.8,
            )
        ],
        results=_SAMPLE,
    )
    monkeypatch.setattr(
        calibration_worker.AutoCalibrator,
        "__init__",
        lambda self, run, settings, **kw: None,
    )
    monkeypatch.setattr(
        calibration_worker.AutoCalibrator, "optimize", lambda self: outcome
    )

    resp = client.post(
        "/api/calibration/optimize",
        json={
            "workspace_id": "ws1",
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
    assert job["outcome"]["converged"] == (status == "converged")
    assert job["outcome"]["status"] == status
    assert job["outcome"]["reason"] == "Analyst-facing explanation."
    assert job["outcome"]["best_params"]["cola_rate"] == pytest.approx(0.028)


def test_optimize_single_year_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/optimize",
        json={
            "workspace_id": "ws1",
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


def test_apply_persists_exact_ranges_and_reports_partial_failures(
    client, monkeypatch
) -> None:
    from types import SimpleNamespace

    exact_ranges = [
        {
            "level": 1,
            "name": "Staff",
            "min_compensation": 61234.567,
            "max_compensation": 98765.432,
        }
    ]
    captured = {}

    class _Storage:
        def get_workspace(self, workspace_id):
            return SimpleNamespace(base_config={"unrelated": {"keep": True}})

        def update_workspace(self, workspace_id, *, base_config):
            captured["base"] = base_config
            return SimpleNamespace(id=workspace_id)

        def list_scenarios(self, workspace_id):
            return [
                SimpleNamespace(id="ok", config_overrides={}),
                SimpleNamespace(id="failed", config_overrides={}),
            ]

        def update_scenario(self, workspace_id, scenario_id, *, config_overrides):
            if scenario_id == "failed":
                raise OSError("write failed")
            captured["scenario"] = config_overrides
            return SimpleNamespace(id=scenario_id)

    monkeypatch.setattr(calibration_router, "_verify_apply_context", lambda *a: {})
    client.app.dependency_overrides[calibration_router.get_storage] = lambda: _Storage()
    try:
        response = client.post(
            "/api/calibration/apply",
            json={
                "context": {
                    "workspace_id": "ws",
                    "scenario_id": None,
                    "source_scenario_id": "source",
                    "source_run_id": "run",
                    "config_fingerprint": "a" * 64,
                    "census_fingerprint": "b" * 64,
                    "random_seed": 42,
                    "start_year": 2025,
                    "end_year": 2027,
                },
                "best_params": {
                    "cola_rate": 0.021234,
                    "merit_budget": 0.034567,
                    "workforce_growth_rate": 0.03,
                    "job_level_compensation": exact_ranges,
                },
                "target_comp_growth_pct": 3.5,
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total_applied"] == 1
    assert response.json()["total_failed"] == 1
    assert captured["base"]["new_hire"]["job_level_compensation"] == exact_ranges
    assert captured["scenario"]["new_hire"]["job_level_compensation"] == exact_ranges
    assert captured["base"]["unrelated"] == {"keep": True}


def test_job_level_compensation_with_name_is_accepted(client, monkeypatch) -> None:
    # Regression: ranges include a string `name`; must not 422 (was Dict[str,float]).
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner, "__init__", lambda self, run, **kw: None
    )
    monkeypatch.setattr(
        calibration_worker.CalibrationRunner, "run_calibration", lambda self: _SAMPLE
    )
    resp = client.post(
        "/api/calibration/run",
        json={
            "workspace_id": "ws1",
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


@pytest.mark.parametrize("rate", [0.0, 0.042345, None])
def test_merge_candidate_salary_growth(rate) -> None:
    request = calibration_router.CalibrationApplyRequest(
        context=calibration_router.CalibrationContext(
            workspace_id="workspace",
            source_scenario_id="scenario",
            source_run_id="run",
            config_fingerprint="config",
            census_fingerprint="census",
            random_seed=42,
            start_year=2025,
            end_year=2027,
        ),
        best_params={"new_hire_salary_growth_rate": rate},
        target_comp_growth_pct=4,
    )
    original = {"new_hire": {"salary_growth_rate": 0.03, "other": "preserved"}}
    merged = calibration_router._merge_calibration_candidate(original, request)
    assert merged["new_hire"] == {
        "salary_growth_rate": 0.03 if rate is None else rate,
        "other": "preserved",
    }
    assert original["new_hire"]["salary_growth_rate"] == 0.03


@pytest.mark.parametrize("shared", [None, False])
def test_horizon_without_shared_pay_scale_returns_409_before_lookup(
    client, shared
) -> None:
    # Saved workspaces keep the shared pay scale off (#1075). Refuse before the
    # matching-run lookup, so the analyst isn't sent to re-run first.
    class _OldWorkspaceStorage:
        def get_workspace(self, workspace_id):
            return SimpleNamespace(base_config={})

        def get_merged_config(self, workspace_id, scenario_id):
            return {"new_hire": {"shared_pay_scale": shared}}

    client.app.dependency_overrides[calibration_router.get_storage] = (
        lambda: _OldWorkspaceStorage()
    )
    try:
        resp = client.post(
            "/api/calibration/optimize",
            json={
                "workspace_id": "ws",
                "scenario_id": "baseline",
                "settings": {
                    "target_workforce_growth": 0.03,
                    "target_comp_growth": 0.04,
                    "search_mode": "horizon",
                },
            },
        )
        assert resp.status_code == 409
        assert "existing staff too" in resp.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()
