"""API error responses must never disclose raw exception details.

Generic 5xx (and exception-derived 4xx) responses must return stable,
client-safe messages; full details — including tracebacks containing
paths, SQL, or credentials — stay in structured server logs and are
correlated to callers via request IDs / error IDs.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

import planalign_api.config as api_config
from planalign_api.errors import GENERIC_500_DETAIL, REQUEST_ID_HEADER
from planalign_api.main import create_app
from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import (
    bands as bands_router,
    imports as imports_router,
    sync as sync_router,
)
from planalign_api.routers.calibration import (
    _execute_job as _run_calibration_job,
    _register_job,
)
from planalign_api.services.export_service import ExportService
from planalign_api.services.file_service import FileService
from planalign_api.storage.workspace_storage import WorkspaceStorage

SECRET_PATH = "/Users/nobody/secret/census.duckdb"
SECRET_SQL = "SELECT * FROM secret_table WHERE password = 'hunter2'"
SECRET_DETAIL = f"{SECRET_SQL} ({SECRET_PATH})"

CENSUS_UPLOAD = {
    "file": ("census.csv", b"employee_id,age\n1,42\n"),
}


def _raise_secret(*args: object, **kwargs: object) -> object:
    raise RuntimeError(SECRET_DETAIL)


def _assert_no_leak(text: str) -> None:
    assert SECRET_PATH not in text
    assert SECRET_SQL not in text


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)
    return TestClient(create_app(), raise_server_exceptions=False)


def _scenario(tmp_path):
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {})
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="S"))
    return storage, workspace.id, scenario.id


# ---------------------------------------------------------------------------
# Global safety net + correlation IDs
# ---------------------------------------------------------------------------


def test_unhandled_exception_returns_sanitized_500_with_request_id(
    tmp_path, monkeypatch, caplog
):
    app = create_app()

    @app.get("/api/__test/boom")
    async def boom() -> dict:
        raise RuntimeError(SECRET_DETAIL)

    client = TestClient(app, raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="planalign_api.main"):
        response = client.get("/api/__test/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": GENERIC_500_DETAIL}
    _assert_no_leak(response.text)
    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id
    # Correlation ID reaches the logs together with full details.
    assert request_id in caplog.text
    assert SECRET_PATH in caplog.text


def test_request_id_header_is_echoed_from_client(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get(
        "/api/health", headers={REQUEST_ID_HEADER: "my-correlation-id"}
    )

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "my-correlation-id"


def test_malformed_request_id_is_replaced_with_generated_one(tmp_path, monkeypatch):
    """Unsafe correlation values (injection, oversized) must never be echoed."""
    import re

    client = _client(tmp_path, monkeypatch)

    for hostile in (
        "bad id\ninjected",
        "trailing-newline\n",
        "trailing-crlf\r\n",
        "x" * 200,
        "id;drop table",
    ):
        response = client.get("/api/health", headers={REQUEST_ID_HEADER: hostile})

        assert response.status_code == 200
        sanitized = response.headers[REQUEST_ID_HEADER]
        assert sanitized != hostile
        assert re.fullmatch(r"[A-Za-z0-9._-]{1,128}", sanitized)


# ---------------------------------------------------------------------------
# Per-router generic handlers
# ---------------------------------------------------------------------------


def test_sync_status_failure_is_sanitized(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(sync_router, "get_sync_service", _raise_secret)

    response = client.get("/api/sync/status")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve sync status"
    _assert_no_leak(response.text)


def test_band_config_read_failure_is_sanitized(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(bands_router.BandService, "read_bands_from_csv", _raise_secret)

    response = client.get("/api/workspaces/ws/config/bands")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to read band configurations"
    _assert_no_leak(response.text)


def test_band_config_domain_value_error_message_is_preserved(tmp_path, monkeypatch):
    """Deliberately authored 4xx validation messages must survive."""

    def _domain_error(*args: object, **kwargs: object) -> object:
        raise ValueError("Age bands must not overlap")

    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(bands_router.BandService, "read_bands_from_csv", _domain_error)

    response = client.get("/api/workspaces/ws/config/bands")

    # Domain-authored message stays; only the raw fallback was sanitized.
    assert response.status_code == 500
    assert response.json()["detail"] == "Invalid band configuration data"
    _assert_no_leak(response.text)


def test_census_upload_save_failure_is_sanitized(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(FileService, "save_uploaded_file", _raise_secret)

    response = client.post(
        "/api/workspaces/ws/upload",
        files=CENSUS_UPLOAD,
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to save file"
    _assert_no_leak(response.text)


def test_import_validation_failure_is_sanitized(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(ExportService, "validate_archive", _raise_secret)

    response = client.post(
        "/api/workspaces/import/validate",
        files={"file": ("archive.7z", b"not-a-real-archive")},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to validate archive"
    _assert_no_leak(response.text)


def test_import_upload_parse_failure_is_sanitized(tmp_path, monkeypatch):
    _, workspace_id, _ = _scenario(tmp_path)
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(imports_router, "_parse_dataframe", _raise_secret)

    response = client.post(
        f"/api/workspaces/{workspace_id}/imports/upload",
        files=CENSUS_UPLOAD,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Could not parse file"
    _assert_no_leak(response.text)


def test_run_details_failure_is_sanitized(tmp_path, monkeypatch):
    _, _, scenario_id = _scenario(tmp_path)
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(WorkspaceStorage, "get_merged_config", _raise_secret)

    response = client.get(f"/api/scenarios/{scenario_id}/details")

    assert response.status_code == 500
    assert response.json()["detail"] == GENERIC_500_DETAIL
    _assert_no_leak(response.text)


# ---------------------------------------------------------------------------
# Persisted error records surfaced through 200 responses
# ---------------------------------------------------------------------------


def test_calibration_job_error_record_is_sanitized(tmp_path, caplog):
    job = _register_job("run")

    with caplog.at_level(logging.ERROR, logger="planalign_api.routers.calibration"):
        _run_calibration_job(
            job,
            build=_raise_secret,
            database_path=None,
            workspace_config=None,
        )

    assert job.status == "failed"
    assert job.error_status == 500
    assert "error_id:" in job.error
    _assert_no_leak(job.error)
    assert SECRET_PATH in caplog.text


def test_bulk_import_failure_warning_is_sanitized(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(ExportService, "import_workspace", _raise_secret)

    response = client.post(
        "/api/workspaces/bulk-import",
        files=[("files", ("archive.7z", b"not-a-real-archive"))],
    )

    assert response.status_code == 200
    warnings = response.json()["results"][0]["warnings"]
    assert len(warnings) == 1
    assert "error_id:" in warnings[0]
    _assert_no_leak(str(warnings))
