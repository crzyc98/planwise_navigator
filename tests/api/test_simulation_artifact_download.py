"""Tests for simulation artifact downloads."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
        asyncio.run(simulations.download_artifact("scenario-1", "../secret", storage))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Artifact ../secret not found"


def test_download_artifact_returns_file_within_scenario(artifact_storage):
    """An artifact stored under the scenario directory remains downloadable."""
    storage, scenario_path = artifact_storage
    artifact_path = scenario_path / "reports" / "summary.csv"
    artifact_path.parent.mkdir()
    artifact_path.write_text("metric,value\nheadcount,100\n")

    response = asyncio.run(
        simulations.download_artifact("scenario-1", "reports/summary.csv", storage)
    )

    assert response.path == artifact_path.resolve()
    assert response.media_type == "text/csv"
    assert response.filename == "summary.csv"
