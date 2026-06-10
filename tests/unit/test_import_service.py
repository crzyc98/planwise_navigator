"""Unit tests for ImportService — session lifecycle, status transitions, and audit log.

Written BEFORE implementation (TDD). These tests MUST FAIL until import_service.py is implemented.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from planalign_api.models.imports import (
    DetectedColumn,
    FieldMapping,
    ImportSession,
    Transformation,
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
    from datetime import datetime

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
    actions = [json.loads(l)["action"] for l in lines]
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
    actions = [json.loads(l)["action"] for l in lines if l.strip()]
    assert "file_delete" in actions
