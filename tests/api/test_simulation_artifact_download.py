"""Tests for simulation artifact downloads."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from planalign_api.routers import simulations


@pytest.fixture
def artifact_storage(tmp_path, monkeypatch):
    """Provide a scenario directory and minimal storage dependency."""
    scenario_path = tmp_path / "workspace" / "scenarios" / "scenario-1"
    scenario_path.mkdir(parents=True)
    storage = SimpleNamespace(
        _scenario_path=lambda workspace_id, scenario_id: scenario_path
    )
    workspace = SimpleNamespace(id="workspace")
    scenario = SimpleNamespace(id="scenario-1")
    monkeypatch.setattr(
        simulations,
        "_find_scenario_and_workspace",
        lambda storage, scenario_id: (workspace, scenario),
    )
    return storage, scenario_path


def test_download_artifact_rejects_path_traversal(artifact_storage, tmp_path):
    """Artifacts outside the scenario directory are reported as not found."""
    storage, _ = artifact_storage
    (tmp_path / "workspace" / "scenarios" / "secret").write_text("secret")

    with pytest.raises(HTTPException) as exc_info:
        simulations.download_artifact("scenario-1", "../secret", storage)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Artifact ../secret not found"


def test_download_artifact_returns_file_within_scenario(artifact_storage):
    """An artifact stored under the scenario directory remains downloadable."""
    storage, scenario_path = artifact_storage
    artifact_path = scenario_path / "reports" / "summary.csv"
    artifact_path.parent.mkdir()
    artifact_path.write_text("metric,value\nheadcount,100\n")

    response = simulations.download_artifact(
        "scenario-1", "reports/summary.csv", storage
    )

    assert response.path == artifact_path.resolve()
    assert response.media_type == "text/csv"
    assert response.filename == "summary.csv"


@pytest.mark.parametrize(
    "filename,size_mib,media_type",
    [
        (
            "results.xlsx",
            12,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("simulation.duckdb", 150, "application/octet-stream"),
    ],
)
def test_download_large_archived_artifact(
    artifact_storage, filename, size_mib, media_type
):
    """The HTTP response preserves every byte of an artifact above 10 MiB."""
    storage, scenario_path = artifact_storage
    artifact_path = scenario_path / "runs" / "run-1" / filename
    artifact_path.parent.mkdir(parents=True)
    payload = bytes(range(256)) * (size_mib * 1024 * 1024 // 256)
    artifact_path.write_bytes(payload)
    app = FastAPI()
    app.include_router(simulations.router, prefix="/api/scenarios")
    app.dependency_overrides[simulations.get_storage] = lambda: storage

    with TestClient(app) as client:
        response = client.get(
            f"/api/scenarios/scenario-1/artifacts/runs/run-1/{filename}"
        )

    assert response.status_code == 200
    assert response.content == payload
    assert int(response.headers["content-length"]) == len(payload)
    assert response.headers["content-type"] == media_type
    assert f'filename="{filename}"' in response.headers["content-disposition"]
