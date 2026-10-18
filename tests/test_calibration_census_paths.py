"""Census import/calibration path regressions for issue #837."""

from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import Workspace, WorkspaceCreate
from planalign_api.routers import calibration, imports
from planalign_api.services.import_service import ImportService
from planalign_api.services.provenance.capture import config_fingerprint, sha256_file
from planalign_api.services.simulation.run_execution import validate_census
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


@pytest.mark.parametrize("path_kind", ["absolute", "workspace-relative"])
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
    }
    config = {"setup": {"census_parquet_path": paths[path_kind]}}

    assert (
        calibration._canonical_census(config, workspace.id, storage) == census.resolve()
    )
    assert config["setup"]["census_parquet_path"] == str(census.resolve())


@pytest.mark.parametrize("path_kind", ["absolute", "traversal", "symlink"])
def test_census_outside_active_workspace_is_rejected(
    storage: WorkspaceStorage, path_kind: str
) -> None:
    workspace = _workspace(storage)
    root = storage._workspace_path(workspace.id)
    fallback = root / "valid-census.parquet"
    fallback.write_bytes(b"workspace-census")
    storage.update_base_config_key(
        workspace.id, "setup.census_parquet_path", str(fallback.resolve())
    )
    outside = storage.workspaces_root / "other-workspace/census.parquet"
    outside.parent.mkdir()
    outside.write_bytes(b"unrelated-census")
    link = root / "census.parquet"
    link.symlink_to(outside.resolve())
    paths = {
        "absolute": str(outside.resolve()),
        "traversal": "../other-workspace/census.parquet",
        "symlink": "census.parquet",
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


@pytest.fixture
def stale_target(storage: WorkspaceStorage) -> tuple[str, str, Path]:
    workspace = _workspace(storage)
    root = storage._workspace_path(workspace.id)
    census = root / "data/census.parquet"
    census.parent.mkdir()
    census.write_bytes(b"current-census")
    storage.update_base_config_key(
        workspace.id, "setup.census_parquet_path", str(census.resolve())
    )
    missing = str((root / "data/imports/old.parquet").resolve())
    scenario = storage.create_scenario(
        workspace.id,
        ScenarioCreate(
            name="Baseline",
            config_overrides={
                "setup": {"census_parquet_path": missing},
                "data_sources": {"census_parquet_path": missing},
                "compensation": {"cola_rate": 0.03},
            },
        ),
    )
    return workspace.id, scenario.id, census.resolve()


def test_missing_override_uses_same_census_as_simulation(
    storage: WorkspaceStorage, stale_target: tuple[str, str, Path]
) -> None:
    wid, sid, census = stale_target
    config = storage.get_merged_config(wid, sid)
    persisted = deepcopy(config)
    simulation_config = deepcopy(config)
    validate_census(storage, simulation_config, sid, wid)

    assert calibration._canonical_census(config, wid, storage) == census
    assert config == simulation_config
    assert storage.get_merged_config(wid, sid) == persisted


def test_valid_override_keeps_its_own_census(
    storage: WorkspaceStorage, stale_target: tuple[str, str, Path]
) -> None:
    wid, sid, _ = stale_target
    config = storage.get_merged_config(wid, sid)
    own_census = Path(config["setup"]["census_parquet_path"])
    own_census.parent.mkdir()
    own_census.write_bytes(b"scenario-census")
    assert calibration._canonical_census(config, wid, storage) == own_census


def test_existing_outside_override_cannot_be_masked_by_workspace_fallback(
    storage: WorkspaceStorage,
    stale_target: tuple[str, str, Path],
    tmp_path: Path,
) -> None:
    wid, sid, _ = stale_target
    config = storage.get_merged_config(wid, sid)
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"outside-workspace")
    config["setup"]["census_parquet_path"] = str(outside)
    with pytest.raises(HTTPException, match="not an uploaded artifact"):
        calibration._canonical_census(config, wid, storage)


def test_stale_absolute_outside_override_uses_simulation_fallback(
    storage: WorkspaceStorage,
    stale_target: tuple[str, str, Path],
    tmp_path: Path,
) -> None:
    wid, sid, census = stale_target
    config = storage.get_merged_config(wid, sid)
    config["setup"]["census_parquet_path"] = str(tmp_path / "old-workspace.parquet")
    simulation_config = deepcopy(config)

    validate_census(storage, simulation_config, sid, wid)

    assert calibration._canonical_census(config, wid, storage) == census
    assert config == simulation_config


@pytest.mark.parametrize("legacy_kind", ["file", "symlink"])
def test_old_server_relative_path_uses_simulation_fallback(
    storage: WorkspaceStorage,
    stale_target: tuple[str, str, Path],
    legacy_kind: str,
) -> None:
    wid, sid, census = stale_target
    config = storage.get_merged_config(wid, sid)
    legacy = storage._workspace_path(wid) / "data/imports/old.parquet"
    legacy.parent.mkdir(parents=True)
    if legacy_kind == "symlink":
        outside = storage.workspaces_root / "other-workspace/census.parquet"
        outside.parent.mkdir()
        outside.write_bytes(b"outside-workspace")
        legacy.symlink_to(outside.resolve())
    else:
        legacy.write_bytes(b"different-census")
    config["setup"]["census_parquet_path"] = str(
        legacy.absolute().relative_to(Path.cwd())
    )
    simulation_config = deepcopy(config)

    validate_census(storage, simulation_config, sid, wid)

    assert calibration._canonical_census(config, wid, storage) == census
    assert config == simulation_config


def test_fallback_rejects_workspace_census_symlink_escape(
    storage: WorkspaceStorage, stale_target: tuple[str, str, Path], tmp_path: Path
) -> None:
    wid, sid, census = stale_target
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"outside-workspace")
    census.unlink()
    census.symlink_to(outside)
    config = storage.get_merged_config(wid, sid)
    with pytest.raises(HTTPException, match="not an uploaded artifact"):
        calibration._canonical_census(config, wid, storage)


def test_missing_workspace_fallback_still_fails(
    storage: WorkspaceStorage, stale_target: tuple[str, str, Path]
) -> None:
    wid, sid, census = stale_target
    census.unlink()
    config = storage.get_merged_config(wid, sid)
    with pytest.raises(HTTPException, match="census is missing"):
        calibration._canonical_census(config, wid, storage)


def test_apply_fingerprints_actual_fallback_census(
    storage: WorkspaceStorage, stale_target: tuple[str, str, Path]
) -> None:
    wid, sid, census = stale_target
    config = storage.get_merged_config(wid, sid)
    validate_census(storage, config, sid, wid)
    context = calibration.CalibrationContext(
        workspace_id=wid,
        scenario_id=sid,
        source_scenario_id=sid,
        source_run_id="completed-run",
        config_fingerprint=config_fingerprint(config),
        census_fingerprint=sha256_file(census)[0],
        random_seed=42,
        start_year=2025,
        end_year=2026,
    )
    assert calibration._verify_apply_context(context, storage) == config
    census.write_bytes(b"replacement-census")
    with pytest.raises(HTTPException, match="changed after calibration"):
        calibration._verify_apply_context(context, storage)


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
