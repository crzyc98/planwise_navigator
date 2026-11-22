"""Containment and identifier validation tests for workspace and scenario paths."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.file_service import FileService
from planalign_api.services.import_service import ImportService
from planalign_api.services.path_guard import (
    PathGuardError,
    ProtectedPathError,
    require_safe_path_component,
    resolve_child_path,
)
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.fast

OVERLONG_ID = "a" * 129

CENSUS_CSV = (
    b"employee_id,employee_birth_date,employee_hire_date,"
    b"employee_gross_compensation,active\n"
    b"E001,1985-04-10,2020-01-15,75000,true\n"
)

# Direct Python values (including ones an HTTP client would normalize before sending).
MALFORMED_RAW_IDS = [
    "",
    " ",
    "   ",
    ".",
    "..",
    "../outside",
    "%2e%2e",
    "foo\\bar",
    "..\\outside",
    "sub/dir",
    ".hidden",
    "ws\x00evil",
    "C:evil",
    OVERLONG_ID,
]

# URL-encoded path segments that arrive at the FastAPI route handler as:
# "..", "%2e%2e", "foo\\bar", "..\\outside", " ", ".hidden", and an overlong ID.
MALFORMED_URL_SEGMENTS = [
    "%2e%2e",
    "%252e%252e",
    "foo%5Cbar",
    "%2e%2e%5Coutside",
    "%20",
    ".hidden",
    OVERLONG_ID,
]


def _snapshot_tree(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if not path.name.startswith(".")
    }


def _seed_workspace_and_scenario(
    workspaces_root: Path,
) -> tuple[WorkspaceStorage, str, str]:
    storage = WorkspaceStorage(workspaces_root)
    workspace = storage.create_workspace(
        WorkspaceCreate(name="Containment Test"),
        {"simulation": {"start_year": 2025, "end_year": 2027}},
    )
    scenario = storage.create_scenario(
        workspace.id,
        ScenarioCreate(
            name="Baseline", config_overrides={"simulation": {"random_seed": 7}}
        ),
    )
    assert scenario is not None
    return storage, workspace.id, scenario.id


def _seed_legacy_workspace(
    workspaces_root: Path,
    workspace_id: str = "ws-test-001",
    scenario_id: str = "sc-001",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    ws_dir = workspaces_root / workspace_id
    sc_dir = ws_dir / "scenarios" / scenario_id
    (sc_dir / "runs").mkdir(parents=True)
    (sc_dir / "results").mkdir(parents=True)
    (ws_dir / "workspace.json").write_text(
        json.dumps(
            {
                "id": workspace_id,
                "name": "Legacy Workspace",
                "created_at": now,
                "updated_at": now,
            }
        ),
        encoding="utf-8",
    )
    (ws_dir / "base_config.yaml").write_text(
        "simulation:\n  start_year: 2025\n  end_year: 2027\n",
        encoding="utf-8",
    )
    (sc_dir / "scenario.json").write_text(
        json.dumps(
            {
                "id": scenario_id,
                "workspace_id": workspace_id,
                "name": "Legacy Scenario",
                "config_overrides": {},
                "status": "not_run",
                "created_at": now,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def env(client_factory: Any, tmp_path: Path) -> dict[str, Any]:
    workspaces_root = tmp_path / "workspaces"
    storage, workspace_id, scenario_id = _seed_workspace_and_scenario(workspaces_root)
    client: TestClient = client_factory(None, raise_server_exceptions=False)
    return {
        "tmp_path": tmp_path,
        "workspaces_root": workspaces_root,
        "storage": storage,
        "workspace_id": workspace_id,
        "scenario_id": scenario_id,
        "client": client,
    }


# ---------------------------------------------------------------------------
# Path helper and service unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_id", MALFORMED_RAW_IDS)
def test_path_helpers_reject_malformed_ids_without_creating_paths(
    tmp_path: Path, bad_id: str
) -> None:
    root = tmp_path / "workspaces"
    storage = WorkspaceStorage(root)
    file_service = FileService(root)
    import_service = ImportService(root)
    valid_ws = storage.create_workspace(WorkspaceCreate(name="Valid"), {})
    before_tmp = _snapshot_tree(tmp_path)

    with pytest.raises(PathGuardError):
        require_safe_path_component(bad_id, label="workspace_id")
    with pytest.raises(PathGuardError):
        resolve_child_path(root, bad_id, label="workspace_id")
    with pytest.raises(PathGuardError):
        storage._workspace_path(bad_id)
    with pytest.raises(PathGuardError):
        storage._scenario_path(valid_ws.id, bad_id)
    with pytest.raises(PathGuardError):
        storage._scenario_path(bad_id, str(uuid.uuid4()))
    with pytest.raises(PathGuardError):
        storage.find_workspace_id_for_scenario(bad_id)
    with pytest.raises(PathGuardError):
        file_service.save_uploaded_file(bad_id, CENSUS_CSV, "census.csv")
    with pytest.raises(PathGuardError):
        file_service.validate_path(bad_id, "data/census.parquet")
    with pytest.raises(PathGuardError):
        file_service.list_workspace_files(bad_id)
    with pytest.raises(PathGuardError):
        import_service._ws_path(bad_id)
    with pytest.raises(PathGuardError):
        import_service._session_path(valid_ws.id, bad_id)
    with pytest.raises(PathGuardError):
        import_service.get_template(valid_ws.id, bad_id)

    assert _snapshot_tree(tmp_path) == before_tmp


def test_path_helpers_refuse_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    storage = WorkspaceStorage(root)
    file_service = FileService(root)
    import_service = ImportService(root)
    outside = tmp_path / "outside"
    outside.mkdir()

    ws_link_id = str(uuid.uuid4())
    (root / ws_link_id).symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProtectedPathError):
        storage._workspace_path(ws_link_id)
    with pytest.raises(ProtectedPathError):
        file_service.save_uploaded_file(ws_link_id, CENSUS_CSV, "census.csv")
    with pytest.raises(ProtectedPathError):
        import_service._ws_path(ws_link_id)
    assert list(outside.iterdir()) == []


# ---------------------------------------------------------------------------
# HTTP route tests for malformed workspace and scenario IDs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_segment", MALFORMED_URL_SEGMENTS)
def test_workspace_and_upload_routes_reject_malformed_workspace_ids(
    env: dict[str, Any], bad_segment: str
) -> None:
    client: TestClient = env["client"]
    tmp_path: Path = env["tmp_path"]
    workspaces_root: Path = env["workspaces_root"]
    scenario_id: str = env["scenario_id"]

    before_tmp = _snapshot_tree(tmp_path)
    before_ws = _snapshot_tree(workspaces_root)

    responses = [
        client.get(f"/api/workspaces/{bad_segment}"),
        client.put(f"/api/workspaces/{bad_segment}", json={"name": "Nope"}),
        client.get(f"/api/workspaces/{bad_segment}/scenarios"),
        client.get(f"/api/workspaces/{bad_segment}/scenarios/{scenario_id}"),
        client.put(
            f"/api/workspaces/{bad_segment}/scenarios/{scenario_id}",
            json={"name": "Nope"},
        ),
        client.get(f"/api/workspaces/{bad_segment}/scenarios/{scenario_id}/config"),
        client.post(
            f"/api/workspaces/{bad_segment}/upload",
            files={"file": ("census.csv", CENSUS_CSV, "text/csv")},
        ),
        client.post(
            f"/api/workspaces/{bad_segment}/imports/upload",
            files={"file": ("census.csv", CENSUS_CSV, "text/csv")},
        ),
        client.post(f"/api/workspaces/{bad_segment}/export"),
        client.post(
            f"/api/workspaces/{bad_segment}/set-census-path",
            json={"file_path": "data/census.parquet"},
        ),
        client.post(
            f"/api/workspaces/{bad_segment}/analyze-age-distribution",
            json={"file_path": "data/census.parquet"},
        ),
        client.post(
            f"/api/workspaces/{bad_segment}/analyze-age-bands",
            json={"file_path": "data/census.parquet"},
        ),
        client.post(
            f"/api/workspaces/{bad_segment}/solve-compensation-growth",
            json={"target_growth_rate": 0.03},
        ),
    ]

    for response in responses:
        assert response.status_code == 400, (
            bad_segment,
            response.request.method,
            response.request.url.path,
            response.status_code,
            response.text,
        )

    assert _snapshot_tree(tmp_path) == before_tmp
    assert _snapshot_tree(workspaces_root) == before_ws


@pytest.mark.parametrize("bad_segment", MALFORMED_URL_SEGMENTS)
def test_scenario_routes_reject_malformed_scenario_ids(
    env: dict[str, Any], bad_segment: str
) -> None:
    client: TestClient = env["client"]
    tmp_path: Path = env["tmp_path"]
    workspaces_root: Path = env["workspaces_root"]
    workspace_id: str = env["workspace_id"]

    before_tmp = _snapshot_tree(tmp_path)
    before_ws = _snapshot_tree(workspaces_root)

    responses = [
        client.get(f"/api/workspaces/{workspace_id}/scenarios/{bad_segment}"),
        client.put(
            f"/api/workspaces/{workspace_id}/scenarios/{bad_segment}",
            json={"name": "Nope"},
        ),
        client.get(f"/api/workspaces/{workspace_id}/scenarios/{bad_segment}/config"),
        client.get(f"/api/scenarios/{bad_segment}/details"),
    ]

    for response in responses:
        assert response.status_code == 400, (
            bad_segment,
            response.request.method,
            response.request.url.path,
            response.status_code,
            response.text,
        )

    assert _snapshot_tree(tmp_path) == before_tmp
    assert _snapshot_tree(workspaces_root) == before_ws


def test_raw_dotdot_literal_rejected_on_routes(env: dict[str, Any]) -> None:
    """Literal '..' is rejected with 4xx and creates nothing, even without encoding."""
    client: TestClient = env["client"]
    tmp_path: Path = env["tmp_path"]
    before_tmp = _snapshot_tree(tmp_path)

    cases: list[tuple[str, str, dict[str, Any]]] = [
        ("GET", "/api/workspaces/..", {}),
        ("PUT", "/api/workspaces/..", {"json": {"name": "Nope"}}),
        ("GET", "/api/workspaces/../scenarios", {}),
        (
            "POST",
            "/api/workspaces/../upload",
            {"files": {"file": ("census.csv", CENSUS_CSV, "text/csv")}},
        ),
        (
            "POST",
            "/api/workspaces/../imports/upload",
            {"files": {"file": ("census.csv", CENSUS_CSV, "text/csv")}},
        ),
    ]
    for method, path, kwargs in cases:
        response = client.request(method, path, **kwargs)
        assert response.status_code in {400, 404, 405}, (
            method,
            path,
            response.status_code,
        )

    assert _snapshot_tree(tmp_path) == before_tmp


def test_symlinked_workspace_returns_404_and_writes_nothing(
    env: dict[str, Any],
) -> None:
    client: TestClient = env["client"]
    tmp_path: Path = env["tmp_path"]
    workspaces_root: Path = env["workspaces_root"]
    outside = tmp_path / "outside-secret"
    outside.mkdir()
    (outside / "workspace.json").write_text('{"id": "x"}', encoding="utf-8")

    link_id = str(uuid.uuid4())
    (workspaces_root / link_id).symlink_to(outside, target_is_directory=True)

    assert client.get(f"/api/workspaces/{link_id}").status_code == 404
    assert (
        client.post(
            f"/api/workspaces/{link_id}/upload",
            files={"file": ("census.csv", CENSUS_CSV, "text/csv")},
        ).status_code
        == 404
    )
    assert not (outside / "data").exists()


# ---------------------------------------------------------------------------
# Unknown well-formed workspace IDs on write routes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unknown_id", ["5f1250d8-8103-400c-8e72-a34563876e2f", "nonexistent-workspace"]
)
def test_uploads_to_unknown_workspace_return_404_and_create_nothing(
    env: dict[str, Any], unknown_id: str
) -> None:
    client: TestClient = env["client"]
    tmp_path: Path = env["tmp_path"]
    workspaces_root: Path = env["workspaces_root"]
    before_tmp = _snapshot_tree(tmp_path)

    census_upload = client.post(
        f"/api/workspaces/{unknown_id}/upload",
        files={"file": ("census.csv", CENSUS_CSV, "text/csv")},
    )
    assert census_upload.status_code == 404
    assert not (workspaces_root / unknown_id).exists()

    import_upload = client.post(
        f"/api/workspaces/{unknown_id}/imports/upload",
        files={"file": ("census.csv", CENSUS_CSV, "text/csv")},
    )
    assert import_upload.status_code == 404
    assert not (workspaces_root / unknown_id).exists()

    set_path = client.post(
        f"/api/workspaces/{unknown_id}/set-census-path",
        json={"file_path": "data/census.parquet"},
    )
    assert set_path.status_code == 404
    assert _snapshot_tree(tmp_path) == before_tmp


# ---------------------------------------------------------------------------
# End-to-end happy path for canonical UUID and legacy single-component IDs
# ---------------------------------------------------------------------------


def test_valid_canonical_and_legacy_ids_work_end_to_end(env: dict[str, Any]) -> None:
    client: TestClient = env["client"]
    workspaces_root: Path = env["workspaces_root"]
    _seed_legacy_workspace(workspaces_root, "ws-test-001", "sc-001")

    for workspace_id, scenario_id in [
        (env["workspace_id"], env["scenario_id"]),
        ("ws-test-001", "sc-001"),
    ]:
        assert client.get(f"/api/workspaces/{workspace_id}").status_code == 200
        assert (
            client.put(
                f"/api/workspaces/{workspace_id}",
                json={"name": f"Updated {workspace_id}"},
            ).status_code
            == 200
        )
        scenarios_resp = client.get(f"/api/workspaces/{workspace_id}/scenarios")
        assert scenarios_resp.status_code == 200
        assert any(item["id"] == scenario_id for item in scenarios_resp.json())

        assert (
            client.get(
                f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}"
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}",
                json={"name": f"Updated {scenario_id}"},
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/workspaces/{workspace_id}/scenarios/{scenario_id}/config"
            ).status_code
            == 200
        )
        upload_resp = client.post(
            f"/api/workspaces/{workspace_id}/upload",
            files={"file": ("census.csv", CENSUS_CSV, "text/csv")},
        )
        assert upload_resp.status_code == 201, upload_resp.text
        assert (workspaces_root / workspace_id / "data" / "census.parquet").is_file()

        import_resp = client.post(
            f"/api/workspaces/{workspace_id}/imports/upload",
            files={"file": ("census.csv", CENSUS_CSV, "text/csv")},
        )
        assert import_resp.status_code == 201, import_resp.text
