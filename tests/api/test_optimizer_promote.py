"""API coverage for promoting completed optimizer candidates into scenarios."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import optimizer as optimizer_router
from planalign_api.storage import workspace_storage
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_optimizer.evaluate import resolve_candidate_config
from planalign_optimizer.models import (
    Candidate,
    DesignSpaceSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerRun,
)
from planalign_orchestrator.config import SimulationConfig, to_dbt_vars

pytestmark = [pytest.mark.fast]


@pytest.fixture(autouse=True)
def _reset_jobs():
    optimizer_router._jobs.clear()
    yield
    optimizer_router._jobs.clear()


@pytest.fixture
def storage_and_source(tmp_path):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    base_config = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    workspace = storage.create_workspace(
        WorkspaceCreate(name="Optimizer promotion workspace"), base_config
    )
    source = storage.create_scenario(
        workspace.id,
        ScenarioCreate(name="Source scenario", config_overrides={}),
    )
    assert source is not None
    return storage, workspace, source


@pytest.fixture
def client(storage_and_source) -> TestClient:
    storage, _, _ = storage_and_source
    app = FastAPI()
    app.include_router(optimizer_router.router, prefix="/api")
    app.dependency_overrides[optimizer_router.get_storage] = lambda: storage
    return TestClient(app)


def _optimizer_run(candidate: Candidate) -> OptimizerRun:
    return OptimizerRun(
        run_id="run-promotion",
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
        max_runs=1,
        search_seed=0,
        baseline_config_fingerprint="promotion-test",
        candidates=(candidate,),
    )


def _seed_completed_job(candidate: Candidate, run_id: str = "opt-promotion") -> None:
    optimizer_router._jobs[run_id] = optimizer_router.OptimizerJob(
        run_id=run_id,
        status="completed",
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        result=_optimizer_run(candidate),
    )


def _promote(client: TestClient, workspace_id: str, source_id: str, **overrides):
    body = {
        "workspace_id": workspace_id,
        "source_scenario_id": source_id,
        "name": "Optimized design",
        **overrides,
    }
    return client.post(
        "/api/optimizer/runs/opt-promotion/candidates/candidate-1/promote",
        json=body,
    )


def test_promote_feasible_candidate_creates_validated_scenario(
    client, storage_and_source
) -> None:
    storage, workspace, source = storage_and_source
    candidate = Candidate(
        candidate_id="candidate-1",
        lever_values={"auto_enrollment.default_deferral_rate": 0.08},
        status="feasible",
    )
    _seed_completed_job(candidate)
    source_scenario_path = (
        storage.workspaces_root / workspace.id / "scenarios" / source.id
    )
    source_overrides_path = source_scenario_path / "overrides.yaml"
    source_overrides_before = source_overrides_path.read_bytes()
    source_json_before = (source_scenario_path / "scenario.json").read_bytes()
    source_config = SimulationConfig.model_validate(
        storage.get_merged_config(workspace.id, source.id)
    )
    expected_config, expected_delta = resolve_candidate_config(
        source_config, candidate.lever_values
    )

    response = _promote(
        client,
        workspace.id,
        source.id,
        description="Created from optimizer candidate",
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Optimized design"
    assert created["description"] == "Created from optimizer candidate"
    assert created["config_overrides"] == expected_config.model_dump(mode="json")
    promoted_config = SimulationConfig.model_validate(
        storage.get_merged_config(workspace.id, created["id"])
    )
    assert to_dbt_vars(promoted_config) == to_dbt_vars(expected_config)
    provenance = created["provenance"]
    assert provenance["source"] == "optimizer_candidate"
    assert provenance["optimizer_run_id"] == "opt-promotion"
    assert provenance["candidate_id"] == "candidate-1"
    assert provenance["source_scenario_id"] == source.id
    assert provenance["candidate_status"] == "feasible"
    assert provenance["override_used"] is False
    assert provenance["applied_lever_values"] == candidate.lever_values
    assert provenance["config_delta"] == expected_delta
    assert datetime.fromisoformat(provenance["promoted_at"])
    assert source_overrides_path.read_bytes() == source_overrides_before
    assert (source_scenario_path / "scenario.json").read_bytes() == source_json_before


def test_promote_name_collision_returns_unused_suffix(
    client, storage_and_source
) -> None:
    storage, workspace, source = storage_and_source
    candidate = Candidate(
        candidate_id="candidate-1",
        lever_values={"auto_enrollment.default_deferral_rate": 0.08},
        status="feasible",
    )
    _seed_completed_job(candidate)

    assert _promote(client, workspace.id, source.id).status_code == 201
    response = _promote(client, workspace.id, source.id)

    assert response.status_code == 409
    body = response.json()
    assert body["detail"] == "scenario name already exists"
    assert body["suggested_name"] == "Optimized design (2)"
    assert body["suggested_name"].lower() not in {
        scenario.name.lower() for scenario in storage.list_scenarios(workspace.id)
    }


def test_promote_stale_candidate_returns_422(client, storage_and_source) -> None:
    _, workspace, source = storage_and_source
    candidate = Candidate(
        candidate_id="candidate-1",
        lever_values={"employer_match.tier_2_rate": 0.1},
        status="feasible",
    )
    _seed_completed_job(candidate)

    response = _promote(client, workspace.id, source.id)

    assert response.status_code == 422
    assert "stale" in response.json()["detail"]


def test_promote_infeasible_candidate_requires_force(
    client, storage_and_source
) -> None:
    storage, workspace, source = storage_and_source
    candidate = Candidate(
        candidate_id="candidate-1",
        lever_values={"auto_enrollment.default_deferral_rate": 0.08},
        status="infeasible",
    )
    _seed_completed_job(candidate)

    rejected = _promote(client, workspace.id, source.id)
    assert rejected.status_code == 422
    assert "force=true" in rejected.json()["detail"]

    promoted = _promote(client, workspace.id, source.id, force=True)
    assert promoted.status_code == 201
    assert promoted.json()["provenance"]["override_used"] is True
    assert (
        storage.get_scenario(workspace.id, promoted.json()["id"]).provenance[
            "override_used"
        ]
        is True
    )


def test_promote_missing_or_running_run_returns_404(client, storage_and_source) -> None:
    _, workspace, source = storage_and_source
    missing = _promote(client, workspace.id, source.id)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "optimizer run not found or expired"

    candidate = Candidate(
        candidate_id="candidate-1",
        lever_values={"auto_enrollment.default_deferral_rate": 0.08},
        status="feasible",
    )
    optimizer_router._jobs["opt-promotion"] = optimizer_router.OptimizerJob(
        run_id="opt-promotion",
        status="running",
        created_at=datetime.now(timezone.utc),
        result=_optimizer_run(candidate),
    )
    running = _promote(client, workspace.id, source.id)
    assert running.status_code == 404
    assert running.json()["detail"] == "optimizer run not found or expired"


def test_promote_rolls_back_partial_storage_failure(
    client, storage_and_source, monkeypatch
) -> None:
    storage, workspace, source = storage_and_source
    candidate = Candidate(
        candidate_id="candidate-1",
        lever_values={"auto_enrollment.default_deferral_rate": 0.08},
        status="feasible",
    )
    _seed_completed_job(candidate)

    def _fail_dump(*args, **kwargs):
        raise OSError("simulated overrides write failure")

    monkeypatch.setattr(workspace_storage.yaml, "dump", _fail_dump)
    response = _promote(client, workspace.id, source.id)

    assert response.status_code == 500
    assert response.json()["detail"] == "failed to create scenario"
    scenario_directories = list(
        (storage.workspaces_root / workspace.id / "scenarios").iterdir()
    )
    assert [directory.name for directory in scenario_directories] == [source.id]
