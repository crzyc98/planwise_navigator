"""Security and behavior tests for the run-details and run-log endpoints."""

import asyncio
import json
import os
import shutil
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from planalign_api.routers import simulations


RUN_ID = str(uuid.uuid4())


@pytest.fixture
def run_storage(tmp_path, monkeypatch):
    """Provide a scenario directory with a valid run, plus minimal storage."""
    scenario_path = tmp_path / "workspace" / "scenarios" / "scenario-1"
    runs_root = scenario_path / "runs"
    run_dir = runs_root / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": RUN_ID, "status": "completed"})
    )
    (run_dir / "simulation.log").write_text(
        "2026-01-01T10:30:00.000000Z [INFO] Starting simulation\n"
        "2026-01-01T10:31:00.000000Z [ERROR] Boom\n"
    )

    storage = SimpleNamespace(
        _scenario_path=lambda workspace_id, scenario_id: scenario_path
    )
    workspace = SimpleNamespace(id="workspace", name="Workspace")
    scenario = SimpleNamespace(id="scenario-1", name="Scenario 1")
    monkeypatch.setattr(
        simulations,
        "_find_scenario_and_workspace",
        lambda storage, scenario_id: (workspace, scenario),
    )
    return storage, scenario_path, run_dir


def _call_get_run(storage, run_id):
    return asyncio.run(simulations.get_run("scenario-1", run_id, storage))


def _call_get_run_logs(storage, run_id):
    return _call_get_run_logs_severity(storage, run_id, severity=None)


def _call_get_run_logs_severity(storage, run_id, *, severity):
    return asyncio.run(
        simulations.get_run_logs(
            "scenario-1",
            run_id,
            page=1,
            page_size=200,
            severity=severity,
            storage=storage,
        )
    )


@pytest.mark.parametrize(
    "bad_run_id",
    [
        "..",
        "../..",
        "../../secrets",
        "%2e%2e",
        "%2e%2e%2fworkspace",
        "subdir/../../..",
        "..\\evil",
        "/etc/passwd",
        "/absolute/path",
        "not-a-uuid",
        "12345",
        RUN_ID.upper(),
        RUN_ID.replace("-", ""),
        f"{RUN_ID}/../{RUN_ID}",
    ],
)
def test_get_run_rejects_malformed_and_traversal_ids(run_storage, bad_run_id):
    storage, _, _ = run_storage

    with pytest.raises(HTTPException) as exc_info:
        _call_get_run(storage, bad_run_id)

    assert exc_info.value.status_code == 400
    assert "canonical UUID" in exc_info.value.detail


@pytest.mark.parametrize(
    "bad_run_id",
    [
        "..",
        "../..",
        "%2e%2e",
        "..\\evil",
        "/etc/passwd",
        "not-a-uuid",
        RUN_ID.upper(),
    ],
)
def test_get_run_logs_rejects_malformed_and_traversal_ids(run_storage, bad_run_id):
    storage, _, _ = run_storage

    with pytest.raises(HTTPException) as exc_info:
        _call_get_run_logs(storage, bad_run_id)

    assert exc_info.value.status_code == 400


def test_get_run_unknown_canonical_uuid_is_404(run_storage):
    storage, _, _ = run_storage

    with pytest.raises(HTTPException) as exc_info:
        _call_get_run(storage, str(uuid.uuid4()))

    assert exc_info.value.status_code == 404


def test_get_run_logs_unknown_canonical_uuid_is_404(run_storage):
    storage, _, _ = run_storage

    with pytest.raises(HTTPException) as exc_info:
        _call_get_run_logs(storage, str(uuid.uuid4()))

    assert exc_info.value.status_code == 404


def test_get_run_symlink_escape_is_404(run_storage, tmp_path):
    storage, _, run_dir = run_storage

    secret_dir = tmp_path / "outside" / "secret-run"
    secret_dir.mkdir(parents=True)
    (secret_dir / "simulation.log").write_text("classified\n")

    shutil.rmtree(run_dir)
    os.symlink(secret_dir, run_dir)

    with pytest.raises(HTTPException) as exc_info:
        _call_get_run(storage, RUN_ID)

    assert exc_info.value.status_code == 404


def test_get_run_broken_metadata_fails_closed(run_storage):
    storage, _, run_dir = run_storage
    (run_dir / "run_metadata.json").write_text("{broken")

    with pytest.raises(HTTPException) as exc_info:
        _call_get_run(storage, RUN_ID)

    assert exc_info.value.status_code == 404


def test_get_run_metadata_identity_mismatch_is_404(run_storage):
    storage, scenario_path, run_dir = run_storage
    other_id = str(uuid.uuid4())
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": other_id, "status": "completed"})
    )

    with pytest.raises(HTTPException) as exc_info:
        _call_get_run(storage, RUN_ID)

    assert exc_info.value.status_code == 404


def test_get_run_returns_details_for_valid_run(run_storage):
    storage, _, _ = run_storage

    details = _call_get_run(storage, RUN_ID)

    assert details.id == RUN_ID
    assert details.scenario_id == "scenario-1"
    assert details.status == "completed"
    artifact_paths = [a.path for a in details.artifacts]
    assert f"runs/{RUN_ID}/run_metadata.json" in artifact_paths
    assert f"runs/{RUN_ID}/simulation.log" in artifact_paths


def test_get_run_logs_returns_paginated_lines(run_storage):
    storage, _, _ = run_storage

    page = _call_get_run_logs(storage, RUN_ID)

    assert page.run_id == RUN_ID
    assert page.total_lines == 2
    assert page.is_running is False
    assert page.log_available is True

    filtered = _call_get_run_logs_severity(storage, RUN_ID, severity="ERROR")
    assert filtered.total_lines == 1


# ---------------------------------------------------------------------------
# HTTP-level contract (routing, percent-decoding, exact status codes)
# ---------------------------------------------------------------------------


@pytest.fixture
def http_client(client_factory, tmp_path):
    """TestClient with a real workspace/scenario/run layout on disk."""
    run_dir = (
        tmp_path
        / "workspaces"
        / "workspace-1"
        / "scenarios"
        / "scenario-1"
        / "runs"
        / RUN_ID
    )
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": RUN_ID, "status": "completed"})
    )
    (run_dir / "simulation.log").write_text(
        "2026-01-01T10:30:00.000000Z [INFO] Starting simulation\n"
    )
    scenario_json = run_dir.parent.parent / "scenario.json"
    scenario_json.write_text(
        json.dumps(
            {
                "id": "scenario-1",
                "workspace_id": "workspace-1",
                "name": "Scenario 1",
                "created_at": "2026-01-01T00:00:00",
            }
        )
    )
    workspace_json = tmp_path / "workspaces" / "workspace-1" / "workspace.json"
    workspace_json.parent.mkdir(parents=True, exist_ok=True)
    workspace_json.write_text(
        json.dumps(
            {
                "id": "workspace-1",
                "name": "Workspace 1",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        )
    )
    return client_factory(None)


@pytest.mark.parametrize(
    ("raw_suffix", "expected_status"),
    [
        # Decodes to "..": survives routing as one segment, rejected by handler.
        ("%2e%2e", 400),
        ("not-a-uuid", 400),
        (RUN_ID.upper(), 400),
        (RUN_ID.replace("-", ""), 400),
        (str(uuid.uuid4()), 404),
        # Decodes to "../..%2Fsecrets"-style multi-segment paths: falls outside
        # the {run_id} route template entirely, so Starlette answers 404.
        ("..%2f..%2fsecrets", 404),
    ],
)
def test_run_detail_http_contract(http_client, raw_suffix, expected_status):
    response = http_client.get(f"/api/scenarios/scenario-1/runs/{raw_suffix}")
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("raw_suffix", "expected_status"),
    [
        ("%2e%2e", 400),
        ("not-a-uuid", 400),
        (RUN_ID.upper(), 400),
        (str(uuid.uuid4()), 404),
        ("..%2f..%2fsecrets", 404),
    ],
)
def test_run_logs_http_contract(http_client, raw_suffix, expected_status):
    response = http_client.get(f"/api/scenarios/scenario-1/runs/{raw_suffix}/logs")
    assert response.status_code == expected_status


def test_run_detail_http_happy_path(http_client):
    response = http_client.get(f"/api/scenarios/scenario-1/runs/{RUN_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == RUN_ID


def test_run_logs_http_happy_path(http_client):
    response = http_client.get(f"/api/scenarios/scenario-1/runs/{RUN_ID}/logs")
    assert response.status_code == 200
    assert response.json()["run_id"] == RUN_ID
