"""Tests for scenario-scoped run-health summary endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from planalign_api.models.provenance import (
    CapturedValidationResult,
    RunProvenanceManifest,
)
from planalign_api.routers import simulations
from planalign_api.services.current_result import publish_current_result
from tests.fixtures.run_provenance import (
    RUN_ID,
    add_minimal_archived_database,
    build_archive,
)

pytestmark = pytest.mark.fast


@pytest.fixture()
def health_client(client_factory, tmp_path, monkeypatch):
    """TestClient bound to a workspace containing scenario-a's archived runs."""
    workspaces_root = tmp_path / "workspaces"
    workspaces_root.mkdir()
    workspace = SimpleNamespace(id="workspace", name="Workspace")
    scenario = SimpleNamespace(id="scenario-a", name="Scenario A")
    monkeypatch.setattr(
        simulations,
        "_find_scenario_and_workspace",
        lambda storage_arg, scenario_id: (workspace, scenario),
    )
    return client_factory(None), workspaces_root


def _rewrite_validation(
    workspaces_root: Path,
    run_id: str,
    results: list[CapturedValidationResult],
    disposition: str,
):
    run_dir = (
        workspaces_root / "workspace" / "scenarios" / "scenario-a" / "runs" / run_id
    )
    manifest = RunProvenanceManifest.model_validate_json(
        (run_dir / "provenance.json").read_text(encoding="utf-8")
    )
    payload = json.loads(manifest.model_dump_json())
    payload["validation_results"] = [
        json.loads(item.model_dump_json()) for item in results
    ]
    payload["validation_disposition"] = disposition
    (run_dir / "provenance.json").write_text(
        RunProvenanceManifest.model_validate(payload).model_dump_json(indent=2),
        encoding="utf-8",
    )


def _result(**overrides) -> CapturedValidationResult:
    values = dict(
        simulation_year=2025,
        check_name="event_sequence_validation",
        severity="error",
        passed=True,
        affected_record_count=0,
    )
    values.update(overrides)
    return CapturedValidationResult(**values)


def test_clean_run_reports_pass_counts(health_client):
    client, root = health_client
    build_archive(root)
    response = client.get(f"/api/scenarios/scenario-a/runs/{RUN_ID}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "clean"
    assert body["disposition"] == "passed"
    assert body["run_id"] == RUN_ID
    assert body["scenario_id"] == "scenario-a"
    assert body["counts"] == {"passed": 1, "warning": 0, "failed": 0, "total": 1}
    assert body["findings"] == []


def test_warning_run_lists_warning_finding(health_client):
    client, root = health_client
    build_archive(root)
    _rewrite_validation(
        root,
        RUN_ID,
        [
            _result(),
            _result(
                check_name="contribution_rate_bounds",
                severity="warning",
                passed=False,
                affected_record_count=3,
            ),
        ],
        "passed_with_warnings",
    )
    body = client.get(f"/api/scenarios/scenario-a/runs/{RUN_ID}/health").json()
    assert body["status"] == "warnings"
    assert body["counts"] == {"passed": 1, "warning": 1, "failed": 0, "total": 2}
    finding = body["findings"][0]
    assert finding["check_name"] == "contribution_rate_bounds"
    assert finding["severity"] == "warning"
    assert finding["stage"] == "VALIDATION"
    assert finding["simulation_year"] == 2025
    assert finding["message"] == "Warning in 2025: 3 records affected."


def test_failed_run_lists_error_finding(health_client):
    client, root = health_client
    build_archive(root)
    _rewrite_validation(
        root,
        RUN_ID,
        [_result(passed=False, affected_record_count=1)],
        "failed",
    )
    body = client.get(f"/api/scenarios/scenario-a/runs/{RUN_ID}/health").json()
    assert body["status"] == "failed"
    assert body["counts"]["failed"] == 1
    finding = body["findings"][0]
    assert finding["severity"] == "error"
    assert finding["message"] == "Error in 2025: 1 record affected."
    assert "path" not in finding["message"].lower()


def test_missing_provenance_artifact_is_distinct_from_clean(health_client):
    client, root = health_client
    build_archive(root, legacy=True)
    body = client.get(f"/api/scenarios/scenario-a/runs/{RUN_ID}/health").json()
    assert body["status"] == "missing_provenance"
    assert body["counts"] == {"passed": 0, "warning": 0, "failed": 0, "total": 0}
    assert body["findings"] == []


def test_malformed_provenance_is_unavailable(health_client):
    client, root = health_client
    run_dir = build_archive(root)
    (run_dir / "provenance.json").write_text("{malformed", encoding="utf-8")
    body = client.get(f"/api/scenarios/scenario-a/runs/{RUN_ID}/health").json()
    assert body["status"] == "unavailable"


def test_empty_validation_results_are_unavailable_not_clean(health_client):
    client, root = health_client
    build_archive(root)
    _rewrite_validation(root, RUN_ID, [], "incomplete")
    body = client.get(f"/api/scenarios/scenario-a/runs/{RUN_ID}/health").json()
    assert body["status"] == "unavailable"


def test_run_health_is_scoped_to_requested_scenario(health_client):
    client, root = health_client
    build_archive(root)
    scenario_b_runs = root / "workspace" / "scenarios" / "scenario-b" / "runs"
    scenario_b_runs.mkdir(parents=True)
    (root / "workspace" / "scenarios" / "scenario-a" / "runs" / RUN_ID).rename(
        scenario_b_runs / RUN_ID
    )
    assert (
        client.get(f"/api/scenarios/scenario-a/runs/{RUN_ID}/health").status_code == 404
    )
    body = client.get(f"/api/scenarios/scenario-b/runs/{RUN_ID}/health").json()
    assert body["status"] == "clean"
    assert body["scenario_id"] == "scenario-b"


def test_unknown_and_malformed_run_ids(health_client):
    client, root = health_client
    build_archive(root)
    unknown = str(uuid4())
    assert (
        client.get(f"/api/scenarios/scenario-a/runs/{unknown}/health").status_code
        == 404
    )
    assert (
        client.get("/api/scenarios/scenario-a/runs/not-a-uuid/health").status_code
        == 400
    )


def test_scenario_endpoint_targets_pointer_result_run(health_client):
    client, root = health_client
    run_dir = build_archive(root)
    add_minimal_archived_database(run_dir)
    publish_current_result(run_dir.parent.parent, RUN_ID)

    # A newer completed run exists on disk but was never promoted.
    newer_id = str(UUID(int=42))
    build_archive(root, run_id=newer_id, status="completed")

    body = client.get("/api/scenarios/scenario-a/run-health").json()
    assert body["status"] == "clean"
    assert body["run_id"] == RUN_ID
    assert body["run_id"] != newer_id


def test_scenario_endpoint_without_completed_result_is_404(health_client):
    client, root = health_client
    build_archive(root)
    response = client.get("/api/scenarios/scenario-a/run-health")
    assert response.status_code == 404
