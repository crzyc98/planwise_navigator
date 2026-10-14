"""Census import/calibration path regressions for issue #837."""

from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from planalign_api.models.workspace import Workspace, WorkspaceCreate
from planalign_api.routers import calibration, imports
from planalign_api.services.import_service import ImportService
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.fast


@pytest.fixture(params=[False, True], ids=["relative-root", "absolute-root"])
def storage(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> WorkspaceStorage:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "workspaces" if request.param else Path("workspaces")
    return WorkspaceStorage(root)


def _workspace(storage: WorkspaceStorage) -> Workspace:
    return storage.create_workspace(
        WorkspaceCreate(name="fresh-workspace"),
        {"simulation": {"start_year": 2025, "end_year": 2026}},
    )


@pytest.mark.parametrize("path_kind", ["absolute", "workspace-relative", "legacy"])
def test_existing_census_paths_resolve(
    storage: WorkspaceStorage, path_kind: str
) -> None:
    workspace = _workspace(storage)
    census = storage._workspace_path(workspace.id) / "data/imports/census.parquet"
    census.parent.mkdir(parents=True)
    census.write_bytes(b"synthetic-census")
    paths = {
        "absolute": str(census.resolve()),
        "workspace-relative": "data/imports/census.parquet",
        "legacy": str(census),
    }
    config = {"setup": {"census_parquet_path": paths[path_kind]}}

    assert (
        calibration._canonical_census(config, workspace.id, storage) == census.resolve()
    )
    assert config["setup"]["census_parquet_path"] == str(census.resolve())


@pytest.mark.parametrize(
    "path_kind", ["absolute", "traversal", "symlink", "legacy-symlink"]
)
def test_census_outside_active_workspace_is_rejected(
    storage: WorkspaceStorage, path_kind: str
) -> None:
    workspace = _workspace(storage)
    root = storage._workspace_path(workspace.id)
    outside = storage.workspaces_root / "other-workspace/census.parquet"
    outside.parent.mkdir()
    outside.write_bytes(b"unrelated-census")
    link = root / "census.parquet"
    link.symlink_to(outside.resolve())
    paths = {
        "absolute": str(outside.resolve()),
        "traversal": "../other-workspace/census.parquet",
        "symlink": "census.parquet",
        "legacy-symlink": str(link),
    }
    config = {"setup": {"census_parquet_path": paths[path_kind]}}

    with pytest.raises(HTTPException) as exc:
        calibration._canonical_census(config, workspace.id, storage)
    assert exc.value.status_code == 409


def test_missing_census_does_not_select_another_upload(
    storage: WorkspaceStorage,
) -> None:
    workspace = _workspace(storage)
    other = storage._workspace_path(workspace.id) / "data/imports/other.parquet"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"unrelated-upload")
    config = {"setup": {"census_parquet_path": "data/imports/missing.parquet"}}

    with pytest.raises(HTTPException, match="census is missing"):
        calibration._canonical_census(config, workspace.id, storage)


def _upload_and_map(client: TestClient, workspace_id: str) -> str:
    prefix = f"/api/workspaces/{workspace_id}/imports"
    fields = {
        "employee_id": "string",
        "employee_birth_date": "date",
        "employee_hire_date": "date",
        "employee_gross_compensation": "decimal",
        "active": "boolean",
    }
    csv = ",".join(fields) + "\nEMP001,1980-01-01,2020-01-01,75000,true\n"
    upload = client.post(
        f"{prefix}/upload", files={"file": ("census.csv", csv, "text/csv")}
    )
    assert upload.status_code == 201, upload.text
    import_id = upload.json()["import_id"]
    mapping = client.put(
        f"{prefix}/{import_id}/mapping",
        json={
            "field_mappings": [
                {"input_column": name, "output_column": name, "output_type": kind}
                for name, kind in fields.items()
            ]
        },
    )
    assert mapping.status_code == 200, mapping.text
    return import_id


def test_mapped_import_handoff_to_calibration(storage: WorkspaceStorage) -> None:
    workspace = _workspace(storage)
    service = ImportService(storage.workspaces_root)
    app = FastAPI()
    app.include_router(imports.router, prefix="/api/workspaces")
    app.include_router(calibration.router, prefix="/api")
    app.dependency_overrides[imports.get_import_service] = lambda: service
    app.dependency_overrides[imports.get_workspace_storage] = lambda: storage
    app.dependency_overrides[calibration.get_storage] = lambda: storage
    client = TestClient(app)
    prefix = f"/api/workspaces/{workspace.id}/imports"
    import_id = _upload_and_map(client, workspace.id)
    generated = client.post(f"{prefix}/{import_id}/generate")
    assert generated.status_code == 202, generated.text

    config = storage.get_workspace(workspace.id).base_config
    configured = Path(config["setup"]["census_parquet_path"])
    assert configured.is_absolute()
    assert configured.is_file()
    assert calibration._canonical_census(config, workspace.id, storage) == configured
    records = service.list_parquet_files(workspace.id)
    assert records[0].storage_path == str(configured)

    # Finding the census must still require a matching completed source run.
    result = client.post("/api/calibration/run", json={"workspace_id": workspace.id})
    assert result.status_code == 409, result.text
    assert "completed" in result.json()["detail"].lower()
