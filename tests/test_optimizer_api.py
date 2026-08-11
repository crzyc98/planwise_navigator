"""Fast API tests for the plan-design optimizer router (issue #557).

Exercises the background-job contract (POST 202 + poll), fail-fast spec/
directory validation (422/409), and the fresh-directory reservation set, with
``run_optimizer`` mocked so no real ``ScenarioRunPool``/multiprocessing runs.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from planalign_api.routers import optimizer as optimizer_router
from planalign_optimizer.models import (
    Candidate,
    DesignSpaceSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerRun,
)

pytestmark = [pytest.mark.fast]

BASELINE_CONFIG = "config/simulation_config.yaml"


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(optimizer_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_reservations():
    optimizer_router._reserved_dirs.clear()
    yield
    optimizer_router._reserved_dirs.clear()


def _await_job(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/optimizer/runs/{run_id}")
        assert resp.status_code == 200
        job = resp.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"Optimizer job {run_id} did not finish in {timeout}s")


def _valid_spec() -> dict:
    return {
        "design_space": {
            "levers": [
                {
                    "name": "auto_enrollment.default_deferral_rate",
                    "kind": "continuous",
                    "bounds": [0.03, 0.08],
                }
            ]
        },
        "objective": {
            "objectives": [{"metric": "participation_rate", "direction": "maximize"}]
        },
        "baseline": {"config_path": BASELINE_CONFIG},
    }


def _sample_run(**overrides) -> OptimizerRun:
    defaults = dict(
        run_id="run-0000",
        design_space=DesignSpaceSpec(
            levers=(
                LeverSpec(
                    name="auto_enrollment.default_deferral_rate",
                    kind="continuous",
                    bounds=(0.03, 0.08),
                ),
            )
        ),
        objective_constraint_spec=ObjectiveConstraintSpec(
            objectives=(
                ObjectiveTerm(metric="participation_rate", direction="maximize"),
            )
        ),
        max_runs=3,
        search_seed=0,
        baseline_config_fingerprint="fp-abc123",
        candidates=(
            Candidate(
                candidate_id="candidate-0000",
                lever_values={"auto_enrollment.default_deferral_rate": 0.05},
                status="feasible",
                objective_values={"participation_rate": 0.87},
            ),
        ),
        ranked_feasible=("candidate-0000",),
        pareto_frontier=None,
        binding_infeasible_constraints=None,
    )
    defaults.update(overrides)
    return OptimizerRun(**defaults)


def test_run_returns_completed_job_with_candidates(
    client, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        optimizer_router, "run_optimizer", lambda *a, **kw: (_sample_run(), None)
    )
    db_dir = tmp_path / "db"

    resp = client.post(
        "/api/optimizer/run",
        json={
            "spec": _valid_spec(),
            "max_runs": 3,
            "database_dir": str(db_dir),
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"].startswith("opt_")
    assert body["status"] == "queued"

    job = _await_job(client, body["run_id"])
    assert job["status"] == "completed"
    assert job["result"]["candidates"][0]["candidate_id"] == "candidate-0000"
    assert job["result"]["ranked_feasible"] == ["candidate-0000"]
    assert Path(job["output_dir"]).exists()
    assert (Path(job["output_dir"]) / "optimizer_results.json").exists()


def test_run_rejects_invalid_spec_yaml(client) -> None:
    bad_spec = _valid_spec()
    bad_spec["design_space"]["levers"][0]["name"] = "not_a_real_lever"
    resp = client.post("/api/optimizer/run", json={"spec": bad_spec, "max_runs": 3})
    assert resp.status_code == 422
    assert "not_a_real_lever" in resp.json()["detail"]


def test_run_rejects_lever_count_over_max(client) -> None:
    spec = _valid_spec()
    spec["design_space"]["levers"] = [
        {
            "name": "auto_enrollment.default_deferral_rate",
            "kind": "continuous",
            "bounds": [0.03, 0.08],
        }
    ] * 9
    resp = client.post("/api/optimizer/run", json={"spec": spec, "max_runs": 3})
    assert resp.status_code == 422


def test_run_rejects_dirty_output_dir(client, tmp_path) -> None:
    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "leftover.txt").write_text("stale")

    resp = client.post(
        "/api/optimizer/run",
        json={"spec": _valid_spec(), "max_runs": 3, "database_dir": str(dirty)},
    )
    assert resp.status_code == 409


def test_concurrent_runs_same_directory_conflict(client, monkeypatch, tmp_path) -> None:
    gate = threading.Event()
    started = threading.Event()

    def _slow_optimizer(*a, **kw):
        started.set()
        gate.wait(timeout=5.0)
        return _sample_run(), None

    monkeypatch.setattr(optimizer_router, "run_optimizer", _slow_optimizer)
    db_dir = tmp_path / "shared"

    r1 = client.post(
        "/api/optimizer/run",
        json={"spec": _valid_spec(), "max_runs": 3, "database_dir": str(db_dir)},
    )
    assert r1.status_code == 202
    assert started.wait(timeout=2.0)

    r2 = client.post(
        "/api/optimizer/run",
        json={"spec": _valid_spec(), "max_runs": 3, "database_dir": str(db_dir)},
    )
    assert r2.status_code == 409

    gate.set()
    job1 = _await_job(client, r1.json()["run_id"])
    assert job1["status"] == "completed"


def test_run_surfaces_binding_infeasible_constraints(
    client, monkeypatch, tmp_path
) -> None:
    infeasible_run = _sample_run(
        ranked_feasible=(),
        pareto_frontier=None,
        binding_infeasible_constraints=("participation_rate",),
        candidates=(
            Candidate(
                candidate_id="candidate-0000",
                lever_values={"auto_enrollment.default_deferral_rate": 0.05},
                status="infeasible",
                objective_values={"participation_rate": 0.5},
            ),
        ),
    )
    monkeypatch.setattr(
        optimizer_router, "run_optimizer", lambda *a, **kw: (infeasible_run, None)
    )
    resp = client.post(
        "/api/optimizer/run",
        json={
            "spec": _valid_spec(),
            "max_runs": 3,
            "database_dir": str(tmp_path / "db"),
        },
    )
    assert resp.status_code == 202
    job = _await_job(client, resp.json()["run_id"])
    assert job["status"] == "completed"
    assert job["result"]["binding_infeasible_constraints"] == ["participation_rate"]
    assert job["result"]["ranked_feasible"] == []


def test_validate_endpoint_returns_seed_preview_for_valid_spec(client) -> None:
    resp = client.post(
        "/api/optimizer/validate",
        json={"spec": _valid_spec(), "max_runs": 4},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["resolved_spec"] is not None
    assert body["seed_phase_count"] >= 1
    assert len(body["seed_phase_candidates"]) == body["seed_phase_count"]


def test_validate_endpoint_returns_error_for_invalid_spec(client) -> None:
    bad_spec = _valid_spec()
    bad_spec["objective"]["objectives"][0]["metric"] = "not_a_real_metric"
    resp = client.post("/api/optimizer/validate", json={"spec": bad_spec})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "not_a_real_metric" in body["error"]


def test_validate_endpoint_requires_exactly_one_input(client) -> None:
    resp = client.post("/api/optimizer/validate", json={})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False

    resp = client.post(
        "/api/optimizer/validate",
        json={"spec": _valid_spec(), "spec_yaml": "design_space: {}"},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_candidate_detail_returns_single_candidate(
    client, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        optimizer_router, "run_optimizer", lambda *a, **kw: (_sample_run(), None)
    )
    resp = client.post(
        "/api/optimizer/run",
        json={
            "spec": _valid_spec(),
            "max_runs": 3,
            "database_dir": str(tmp_path / "db"),
        },
    )
    run_id = resp.json()["run_id"]
    _await_job(client, run_id)

    detail = client.get(f"/api/optimizer/runs/{run_id}/candidates/candidate-0000")
    assert detail.status_code == 200
    assert detail.json()["status"] == "feasible"

    missing = client.get(f"/api/optimizer/runs/{run_id}/candidates/nope")
    assert missing.status_code == 404


def test_get_run_404_for_unknown_run_id(client) -> None:
    resp = client.get("/api/optimizer/runs/opt_does_not_exist")
    assert resp.status_code == 404


def test_build_failure_maps_to_500_with_logged_exception(
    client, monkeypatch, tmp_path
) -> None:
    def _boom(*a, **kw):
        raise RuntimeError("scenario pool exploded")

    monkeypatch.setattr(optimizer_router, "run_optimizer", _boom)
    resp = client.post(
        "/api/optimizer/run",
        json={
            "spec": _valid_spec(),
            "max_runs": 3,
            "database_dir": str(tmp_path / "db"),
        },
    )
    assert resp.status_code == 202
    job = _await_job(client, resp.json()["run_id"])
    assert job["status"] == "failed"
    assert job["error_status"] == 500
    assert "scenario pool exploded" in job["error"]
