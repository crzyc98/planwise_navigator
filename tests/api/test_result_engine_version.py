"""Selected results carry the engine version that produced them (#1182)."""

from __future__ import annotations

import json
import uuid

import duckdb
import pytest

from _version import __version__
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.current_result import publish_current_result
from planalign_api.services.run_trust import engine_version_gap, read_engine_version
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = [pytest.mark.fast]


def _published_scenario(tmp_path, engine_version: str | None) -> tuple[str, str]:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="S"))
    assert scenario is not None
    run_id = str(uuid.uuid4())
    run_dir = storage.allocate_run_directory(workspace.id, scenario.id, run_id)
    duckdb.connect(str(run_dir / "simulation.duckdb")).close()
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": run_id, "status": "completed"})
    )
    if engine_version is not None:
        (run_dir / "provenance.json").write_text(
            json.dumps({"software": {"planalign_version": engine_version}})
        )
    publish_current_result(storage._scenario_path(workspace.id, scenario.id), run_id)
    return workspace.id, scenario.id


@pytest.mark.parametrize(
    ("result", "gap"),
    [
        ("3.1.0", "minor"),
        ("2.9.9", "major"),
        (__version__, None),
        ("99.0.0", None),
        ("not-a-version", None),
        (None, None),
    ],
)
def test_engine_version_gap(result: str | None, gap: str | None) -> None:
    assert engine_version_gap(result) == gap


def test_patch_gap() -> None:
    assert engine_version_gap("3.2.0", running_version="3.2.1") == "patch"


def test_scenario_list_reports_older_result_without_opening_databases(
    tmp_path, client_factory, monkeypatch
) -> None:
    workspace_id, scenario_id = _published_scenario(tmp_path, "3.1.0")
    client = client_factory(None)

    def no_connect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("scenario list must not open scenario databases")

    monkeypatch.setattr(duckdb, "connect", no_connect)
    listed = client.get(f"/api/workspaces/{workspace_id}/scenarios").json()[0]
    detail = client.get(f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}")

    for scenario in (listed, detail.json()):
        assert scenario["result_engine_version"] == "3.1.0"
        assert scenario["result_engine_version_gap"] == "minor"


def test_result_without_provenance_has_no_version(tmp_path, client_factory) -> None:
    workspace_id, _ = _published_scenario(tmp_path, None)
    scenario = client_factory(None).get(f"/api/workspaces/{workspace_id}/scenarios")
    body = scenario.json()[0]
    assert body["result_engine_version"] is None
    assert body["result_engine_version_gap"] is None


def test_unreadable_provenance_is_ignored(tmp_path) -> None:
    (tmp_path / "provenance.json").write_text("{not json")
    assert read_engine_version(tmp_path) is None
