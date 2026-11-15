"""Unit tests for ImportService — session lifecycle, status transitions, and audit log.

Written BEFORE implementation (TDD). These tests MUST FAIL until import_service.py is implemented.
"""

import json
from pathlib import Path

import pytest

from planalign_api.models.imports import (
    DetectedColumn,
)

# ---------------------------------------------------------------------------
# Fixture: temp workspace root
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_workspaces(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture()
def service(tmp_workspaces: Path):
    from planalign_api.services.import_service import ImportService

    return ImportService(workspaces_root=tmp_workspaces)


@pytest.fixture()
def workspace_id(tmp_workspaces: Path) -> str:
    wid = "ws-test-001"
    (tmp_workspaces / wid).mkdir(parents=True)
    return wid


# ---------------------------------------------------------------------------
# Session create — correlation_id present
# ---------------------------------------------------------------------------


def test_create_session_returns_correlation_id(service, workspace_id):
    session = service.create_session(
        workspace_id=workspace_id,
        original_filename="test.csv",
        source_format="csv",
        detected_columns=[DetectedColumn(name="A", inferred_type="string")],
        row_count=10,
        preview_rows=[{"A": "val"}],
    )
    assert session.correlation_id != ""
    assert session.correlation_id == session.import_id


def test_create_session_writes_metadata_json(service, workspace_id):
    session = service.create_session(
        workspace_id=workspace_id,
        original_filename="test.csv",
        source_format="csv",
        detected_columns=[],
        row_count=0,
        preview_rows=[],
    )
    metadata_path = service._metadata_path(workspace_id, session.import_id)
    assert metadata_path.exists()
    data = json.loads(metadata_path.read_text())
    assert data["import_id"] == session.import_id


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_status_transition_uploaded_to_mapping_in_progress(service, workspace_id):
    session = service.create_session(
        workspace_id=workspace_id,
        original_filename="test.csv",
        source_format="csv",
        detected_columns=[],
        row_count=0,
        preview_rows=[],
    )
    assert session.status == "uploaded"
    updated = service.update_status(
        workspace_id, session.import_id, "mapping_in_progress"
    )
    assert updated.status == "mapping_in_progress"


def test_status_transition_to_generating(service, workspace_id):
    session = service.create_session(
        workspace_id=workspace_id,
        original_filename="test.csv",
        source_format="csv",
        detected_columns=[],
        row_count=0,
        preview_rows=[],
    )
    service.update_status(workspace_id, session.import_id, "mapping_in_progress")
    updated = service.update_status(workspace_id, session.import_id, "generating")
    assert updated.status == "generating"


def test_status_transition_generating_to_completed(service, workspace_id):
    session = service.create_session(
        workspace_id=workspace_id,
        original_filename="test.csv",
        source_format="csv",
        detected_columns=[],
        row_count=0,
        preview_rows=[],
    )
    service.update_status(workspace_id, session.import_id, "mapping_in_progress")
    service.update_status(workspace_id, session.import_id, "generating")
    updated = service.update_status(workspace_id, session.import_id, "completed")
    assert updated.status == "completed"


def test_status_transition_generating_to_failed(service, workspace_id):
    session = service.create_session(
        workspace_id=workspace_id,
        original_filename="test.csv",
        source_format="csv",
        detected_columns=[],
        row_count=0,
        preview_rows=[],
    )
    service.update_status(workspace_id, session.import_id, "generating")
    updated = service.update_status(
        workspace_id, session.import_id, "failed", error_message="boom"
    )
    assert updated.status == "failed"
    assert updated.error_message == "boom"


# ---------------------------------------------------------------------------
# Session metadata read/write
# ---------------------------------------------------------------------------


def test_get_session_returns_saved_session(service, workspace_id):
    created = service.create_session(
        workspace_id=workspace_id,
        original_filename="census.xlsx",
        source_format="xlsx",
        detected_columns=[DetectedColumn(name="X", inferred_type="integer")],
        row_count=5,
        preview_rows=[],
    )
    retrieved = service.get_session(workspace_id, created.import_id)
    assert retrieved is not None
    assert retrieved.import_id == created.import_id
    assert retrieved.original_filename == "census.xlsx"


def test_get_session_returns_none_for_unknown(service, workspace_id):
    result = service.get_session(workspace_id, "nonexistent-id")
    assert result is None


# ---------------------------------------------------------------------------
# Parquet index append
# ---------------------------------------------------------------------------


def test_parquet_index_appends_on_save(service, workspace_id, tmp_workspaces):
    from planalign_api.models.imports import ParquetFile

    pf = ParquetFile(
        workspace_id=workspace_id,
        import_id="imp-001",
        filename="20260530_test.parquet",
        storage_path=str(
            tmp_workspaces / workspace_id / "data" / "imports" / "20260530_test.parquet"
        ),
        original_filename="test.csv",
        row_count=100,
        file_size_bytes=4096,
        schema=[],
    )
    service.save_parquet_record(workspace_id, pf)
    files = service.list_parquet_files(workspace_id)
    assert len(files) == 1
    assert files[0].filename == "20260530_test.parquet"


# ---------------------------------------------------------------------------
# Audit log written on create, generate, delete
# ---------------------------------------------------------------------------


def test_audit_log_written_on_create(service, workspace_id, tmp_workspaces):
    service.create_session(
        workspace_id=workspace_id,
        original_filename="census.csv",
        source_format="csv",
        detected_columns=[],
        row_count=0,
        preview_rows=[],
    )
    audit_path = service._audit_log_path(workspace_id)
    assert audit_path.exists()
    lines = audit_path.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["action"] == "session_create"
    assert entry["filename"] == "census.csv"


def test_audit_log_written_on_generate_success(service, workspace_id, tmp_workspaces):
    session = service.create_session(
        workspace_id=workspace_id,
        original_filename="census.csv",
        source_format="csv",
        detected_columns=[],
        row_count=50,
        preview_rows=[],
    )
    service._write_audit_log(
        workspace_id=workspace_id,
        action="generate_success",
        import_id=session.import_id,
        filename="census.csv",
        row_count=50,
        user="analyst",
        mapping_config={},
    )
    audit_path = service._audit_log_path(workspace_id)
    lines = audit_path.read_text().strip().split("\n")
    actions = [json.loads(ln)["action"] for ln in lines]
    assert "generate_success" in actions


def test_audit_log_written_on_delete(service, workspace_id, tmp_workspaces):
    from planalign_api.models.imports import ParquetFile

    pf = ParquetFile(
        workspace_id=workspace_id,
        import_id="imp-001",
        filename="20260530_test.parquet",
        storage_path=str(
            tmp_workspaces / workspace_id / "data" / "imports" / "20260530_test.parquet"
        ),
        original_filename="test.csv",
        row_count=10,
        file_size_bytes=1024,
        schema=[],
    )
    service.save_parquet_record(workspace_id, pf)
    service.delete_parquet_file(workspace_id, pf.file_id, user="analyst")
    audit_path = service._audit_log_path(workspace_id)
    lines = audit_path.read_text().strip().split("\n")
    actions = [json.loads(ln)["action"] for ln in lines if ln.strip()]
    assert "file_delete" in actions


# ---------------------------------------------------------------------------
# Parquet records resolve only inside their workspace
# ---------------------------------------------------------------------------

# Path from another machine, as carried by a workspace export archive.
STALE_EXPORT_PATH = "/old/machine/workspaces/old-ws-id/data/imports/inside.parquet"


def _record(service, workspace_id: str, storage_path: str):
    from planalign_api.models.imports import ParquetFile

    pf = ParquetFile(
        workspace_id=workspace_id,
        import_id="imp-001",
        filename=Path(storage_path).name,
        storage_path=storage_path,
        original_filename="test.csv",
    )
    service.save_parquet_record(workspace_id, pf)
    return pf


def _workspace_file(tmp_workspaces: Path, workspace_id: str) -> Path:
    path = tmp_workspaces / workspace_id / "data" / "imports" / "inside.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PAR1")
    return path


@pytest.fixture()
def outside_file(tmp_path: Path) -> Path:
    path = tmp_path / "elsewhere" / "outside.parquet"
    path.parent.mkdir()
    path.write_bytes(b"keep me")
    return path


@pytest.fixture()
def api_client(service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from planalign_api.routers.imports import get_import_service, router

    app = FastAPI()
    app.include_router(router, prefix="/api/workspaces")
    app.dependency_overrides[get_import_service] = lambda: service
    return TestClient(app)


def test_resolve_accepts_record_inside_workspace(service, workspace_id, tmp_workspaces):
    inside = _workspace_file(tmp_workspaces, workspace_id)
    pf = _record(service, workspace_id, str(inside.resolve()))
    assert service.resolve_parquet_path(workspace_id, pf) == inside.resolve()


@pytest.mark.parametrize(
    "stored",
    [
        "../../../elsewhere/outside.parquet",
        "imports/../../../../elsewhere/outside.parquet",
        "/other/data/../../../elsewhere/outside.parquet",
    ],
)
def test_resolve_rejects_dotdot_paths(service, workspace_id, outside_file, stored):
    pf = _record(service, workspace_id, stored)
    assert service.resolve_parquet_path(workspace_id, pf) is None


def test_resolve_rejects_absolute_path_outside_workspace(
    service, workspace_id, outside_file
):
    pf = _record(service, workspace_id, str(outside_file))
    assert service.resolve_parquet_path(workspace_id, pf) is None


def test_resolve_rejects_symlink_escaping_workspace(
    service, workspace_id, tmp_workspaces, outside_file
):
    link = tmp_workspaces / workspace_id / "data" / "imports" / "link.parquet"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside_file)
    pf = _record(service, workspace_id, str(link))
    assert service.resolve_parquet_path(workspace_id, pf) is None


def test_resolve_reroots_path_from_exported_workspace(
    service, workspace_id, tmp_workspaces
):
    inside = _workspace_file(tmp_workspaces, workspace_id)
    pf = _record(service, workspace_id, STALE_EXPORT_PATH)
    assert service.resolve_parquet_path(workspace_id, pf) == inside.resolve()


def test_download_outside_workspace_returns_404(
    api_client, service, workspace_id, outside_file
):
    pf = _record(service, workspace_id, str(outside_file))
    resp = api_client.get(
        f"/api/workspaces/{workspace_id}/parquet-files/{pf.file_id}/download"
    )
    assert resp.status_code == 404


def test_delete_outside_workspace_keeps_outside_file(
    api_client, service, workspace_id, outside_file
):
    pf = _record(service, workspace_id, str(outside_file))
    resp = api_client.delete(
        f"/api/workspaces/{workspace_id}/parquet-files/{pf.file_id}"
    )
    assert resp.status_code == 204
    assert outside_file.read_bytes() == b"keep me"
    assert service.list_parquet_files(workspace_id) == []


def test_download_and_delete_record_inside_workspace(
    api_client, service, workspace_id, tmp_workspaces
):
    inside = _workspace_file(tmp_workspaces, workspace_id)
    pf = _record(service, workspace_id, str(inside.resolve()))
    url = f"/api/workspaces/{workspace_id}/parquet-files/{pf.file_id}"
    download = api_client.get(f"{url}/download")
    assert download.status_code == 200
    assert download.content == b"PAR1"
    assert api_client.delete(url).status_code == 204
    assert not inside.exists()


def test_download_reroots_record_from_exported_workspace(
    api_client, service, workspace_id, tmp_workspaces
):
    _workspace_file(tmp_workspaces, workspace_id)
    pf = _record(service, workspace_id, STALE_EXPORT_PATH)
    resp = api_client.get(
        f"/api/workspaces/{workspace_id}/parquet-files/{pf.file_id}/download"
    )
    assert resp.status_code == 200
    assert resp.content == b"PAR1"


def test_resolve_reroots_windows_export_path(service, workspace_id, tmp_workspaces):
    inside = _workspace_file(tmp_workspaces, workspace_id)
    pf = _record(
        service, workspace_id, r"C:\Users\x\old-ws\data\imports\inside.parquet"
    )
    assert service.resolve_parquet_path(workspace_id, pf) == inside.resolve()


def test_resolve_rejects_non_parquet_files_inside_workspace(
    service, workspace_id, tmp_workspaces
):
    log = tmp_workspaces / workspace_id / "data" / "imports" / "audit.log"
    log.parent.mkdir(parents=True)
    log.write_text("audit")
    pf = _record(service, workspace_id, "/old/root/ws/data/imports/audit.log")
    assert service.resolve_parquet_path(workspace_id, pf) is None


def test_delete_stale_record_keeps_file_with_same_name(
    api_client, service, workspace_id, tmp_workspaces
):
    # A stale exported record must not delete the live file it re-roots to.
    census = tmp_workspaces / workspace_id / "data" / "census.parquet"
    census.parent.mkdir(parents=True, exist_ok=True)
    census.write_bytes(b"PAR1 live")
    pf = _record(service, workspace_id, "/old/root/old-ws/data/census.parquet")
    resp = api_client.delete(
        f"/api/workspaces/{workspace_id}/parquet-files/{pf.file_id}"
    )
    assert resp.status_code == 204
    assert census.read_bytes() == b"PAR1 live"
