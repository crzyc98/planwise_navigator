"""Regression tests for bounded multipart upload handling."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import planalign_api.routers.imports as imports_router
import planalign_api.routers.workspaces as workspaces_router
from planalign_api.models.export import ImportValidationResponse
from planalign_api.services import upload_stream

pytestmark = pytest.mark.fast


class ChunkedUpload:
    """Minimal upload double that records requested read sizes."""

    def __init__(self, content: bytes):
        self._content = content
        self._position = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        chunk = self._content[self._position : self._position + size]
        self._position += len(chunk)
        return chunk


def test_streaming_upload_rejects_before_reading_the_full_body(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(upload_stream, "UPLOAD_CHUNK_BYTES", 2)
    monkeypatch.setattr(upload_stream.tempfile, "tempdir", str(tmp_path))
    file = ChunkedUpload(b"abcd")

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            upload_stream.stream_upload_to_tempfile(
                file,  # type: ignore[arg-type]
                suffix=".7z",
                max_file_bytes=3,
            )
        )

    assert error.value.status_code == 413
    assert file.read_sizes == [2, 2]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("path", ["/import/validate", "/import"])
def test_archive_endpoints_reject_oversized_uploads_before_processing(
    client_factory, monkeypatch, path: str
) -> None:
    monkeypatch.setattr(workspaces_router, "MAX_IMPORT_SIZE_BYTES", 3)
    client = client_factory(None)

    response = client.post(
        f"/api/workspaces{path}",
        files={"file": ("workspace.7z", b"four", "application/x-7z-compressed")},
    )

    assert response.status_code == 413


def test_validate_archive_removes_temporary_upload_after_success(
    client_factory, monkeypatch, tmp_path
) -> None:
    """Successful validation must not retain the uploaded archive on disk."""
    monkeypatch.setattr(upload_stream.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(
        workspaces_router.ExportService,
        "validate_archive",
        lambda self, archive_path, file_size: ImportValidationResponse(valid=True),
    )
    client = client_factory(None)

    response = client.post(
        "/api/workspaces/import/validate",
        files={"file": ("workspace.7z", b"archive", "application/x-7z-compressed")},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert list(tmp_path.glob("*.7z")) == []


def test_bulk_import_reports_uploads_that_exceed_the_request_total(
    client_factory, monkeypatch
) -> None:
    """A file over the request total is reported, not raised past earlier imports."""
    monkeypatch.setattr(workspaces_router, "MAX_IMPORT_SIZE_BYTES", 3)
    monkeypatch.setattr(workspaces_router, "MAX_BULK_IMPORT_SIZE_BYTES", 3)
    client = client_factory(None)

    response = client.post(
        "/api/workspaces/bulk-import",
        files=[
            ("files", ("first.7z", b"ok", "application/x-7z-compressed")),
            ("files", ("second.7z", b"ok", "application/x-7z-compressed")),
        ],
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [entry["name"] for entry in results] == ["first.7z", "second.7z"]
    assert results[1]["status"] == "partial"
    assert "Total upload size" in results[1]["warnings"][0]
    assert response.json()["completed"] == 2


def test_census_upload_rejects_oversized_upload_before_parsing(
    client_factory, monkeypatch
) -> None:
    monkeypatch.setattr(imports_router, "MAX_UPLOAD_BYTES", 3)
    client = client_factory(None)
    workspace = client.post("/api/workspaces", json={"name": "Upload test"})
    assert workspace.status_code == 201

    response = client.post(
        f"/api/workspaces/{workspace.json()['id']}/imports/upload",
        files={"file": ("census.csv", b"id\nx\n", "text/csv")},
    )

    assert response.status_code == 413
