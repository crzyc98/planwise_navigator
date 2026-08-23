"""API contract tests for deletion endpoint traversal containment."""

from __future__ import annotations

import asyncio
import shutil
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from planalign_api.routers import scenarios as scenarios_router
from planalign_api.routers import workspaces as workspaces_router
from planalign_api.storage.workspace_storage import WorkspaceStorage


WORKSPACE_ID = str(uuid.uuid4())
SCENARIO_ID = str(uuid.uuid4())
OTHER_WORKSPACE_ID = str(uuid.uuid4())

# Includes values that an HTTP client would normalize before they ever reach
# the route ("..", "%2e%2e", embedded separators); those are exercised against
# the endpoint functions directly so no client-side normalization hides them.
MALFORMED_IDS = [
    ".",
    "..",
    "../..",
    "../sentinel",
    "%2e%2e",
    "%2e%2e%2fescape",
    "sub/dir",
    "..\\evil",
    "C:\\Windows",
    "/etc/passwd",
    "not-a-uuid",
    WORKSPACE_ID.upper(),
    WORKSPACE_ID.replace("-", ""),
]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Seed a valid workspace/scenario pair plus a sibling sentinel."""
    root = tmp_path / "workspaces"
    ws_dir = root / WORKSPACE_ID
    (ws_dir / "scenarios" / SCENARIO_ID).mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (ws_dir / "workspace.json").write_text(
        json.dumps(
            {"id": WORKSPACE_ID, "name": "W", "created_at": now, "updated_at": now}
        )
    )
    (ws_dir / "scenarios" / SCENARIO_ID / "scenario.json").write_text(
        json.dumps(
            {
                "id": SCENARIO_ID,
                "workspace_id": WORKSPACE_ID,
                "name": "S",
                "created_at": now,
            }
        )
    )
    sibling = root / OTHER_WORKSPACE_ID
    sibling.mkdir()
    (sibling / "keep.txt").write_text("do not delete")

    storage = WorkspaceStorage(root)
    rmtree_calls: list[Path] = []
    original_rmtree = shutil.rmtree

    def _record(path, *args, **kwargs):
        rmtree_calls.append(Path(path))
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", _record)
    return {"root": root, "storage": storage, "rmtree_calls": rmtree_calls}


def _delete_workspace(env, workspace_id):
    return asyncio.run(
        workspaces_router.delete_workspace(workspace_id, storage=env["storage"])
    )


def _delete_scenario(env, workspace_id, scenario_id):
    return asyncio.run(
        scenarios_router.delete_scenario(
            workspace_id, scenario_id, storage=env["storage"]
        )
    )


def test_delete_workspace_malformed_ids_are_400(env):
    for bad_id in MALFORMED_IDS:
        with pytest.raises(HTTPException) as exc_info:
            _delete_workspace(env, bad_id)
        assert exc_info.value.status_code == 400, bad_id
        assert "canonical UUID" in exc_info.value.detail


def test_delete_scenario_malformed_ids_are_400(env):
    for bad_id in MALFORMED_IDS:
        with pytest.raises(HTTPException) as exc_info:
            _delete_scenario(env, bad_id, SCENARIO_ID)
        assert exc_info.value.status_code == 400, bad_id
        with pytest.raises(HTTPException) as exc_info:
            _delete_scenario(env, WORKSPACE_ID, bad_id)
        assert exc_info.value.status_code == 400, bad_id


def test_delete_unknown_canonical_ids_are_404(env):
    missing = str(uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        _delete_workspace(env, missing)
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        _delete_scenario(env, WORKSPACE_ID, str(uuid.uuid4()))
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        _delete_scenario(env, str(uuid.uuid4()), str(uuid.uuid4()))
    assert exc_info.value.status_code == 404


def test_traversal_never_rmtrees_outside_root(env):
    for bad_id in MALFORMED_IDS:
        with pytest.raises(HTTPException):
            _delete_workspace(env, bad_id)
        with pytest.raises(HTTPException):
            _delete_scenario(env, bad_id, bad_id)

    root = env["root"].resolve()
    for call_path in env["rmtree_calls"]:
        assert call_path.resolve().parent == root

    # The sibling workspace and the legitimate scenario survive.
    assert (env["root"] / OTHER_WORKSPACE_ID / "keep.txt").exists()
    scenario_json = (
        env["root"] / WORKSPACE_ID / "scenarios" / SCENARIO_ID / "scenario.json"
    )
    assert json.loads(scenario_json.read_text())["id"] == SCENARIO_ID


def test_symlinked_workspace_deletion_is_refused_as_404(env, tmp_path):
    outside = tmp_path / "outside-target"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep")
    symlink_id = str(uuid.uuid4())
    (env["root"] / symlink_id).symlink_to(outside, target_is_directory=True)

    with pytest.raises(HTTPException) as exc_info:
        _delete_workspace(env, symlink_id)
    assert exc_info.value.status_code == 404
    assert (outside / "precious.txt").exists()
    assert env["rmtree_calls"] == []


def test_valid_workspace_and_scenario_deletion_succeeds(env):
    assert _delete_scenario(env, WORKSPACE_ID, SCENARIO_ID) == {"success": True}
    assert _delete_workspace(env, WORKSPACE_ID) == {"success": True}
    assert not (env["root"] / WORKSPACE_ID).exists()


@pytest.fixture()
def client(client_factory):
    # client_factory points APISettings.workspaces_root at tmp_path/"workspaces",
    # which is exactly where the ``env`` fixture seeds its tree.
    return client_factory(None)


def test_http_malformed_id_is_400(client, env):
    """The HTTP layer maps malformed IDs to 400 without touching disk."""
    response = client.delete("/api/workspaces/not-a-uuid")
    assert response.status_code == 400
    assert "canonical UUID" in response.json()["detail"]

    response = client.request(
        "DELETE", f"/api/scenarios/{WORKSPACE_ID}/scenarios/%2E%2E"
    )
    assert response.status_code in {400, 404}
    assert env["rmtree_calls"] == []

    assert (env["root"] / OTHER_WORKSPACE_ID / "keep.txt").exists()
    scenario_json = (
        env["root"] / WORKSPACE_ID / "scenarios" / SCENARIO_ID / "scenario.json"
    )
    assert scenario_json.exists()
