"""The census as-of date is asked at import and follows the census in use.

All census data here is synthetic.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

import duckdb
import pytest
from fastapi.testclient import TestClient

from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.storage.workspace_storage import WorkspaceStorage
from tests.test_import_full_file_quality import MAPPINGS, _census

pytestmark = pytest.mark.fast


@pytest.fixture()
def setup(client_factory, tmp_path: Path) -> tuple[TestClient, WorkspaceStorage, str]:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="W"), {"setup": {}})
    return client_factory(None), storage, workspace.id


def _setup_value(storage: WorkspaceStorage, ws: str, key: str) -> Optional[Any]:
    workspace = storage.get_workspace(ws)
    assert workspace is not None
    return (workspace.base_config.get("setup") or {}).get(key)


def _mapped_import(client: TestClient, ws: str, name: str = "census.csv") -> str:
    upload = client.post(
        f"/api/workspaces/{ws}/imports/upload",
        files={"file": (name, io.BytesIO(_census().encode()), "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    import_id = upload.json()["import_id"]
    saved = client.put(
        f"/api/workspaces/{ws}/imports/{import_id}/mapping",
        json={"field_mappings": MAPPINGS},
    )
    assert saved.json()["validation_errors"] == []
    return import_id


def _generate(client: TestClient, ws: str, as_of: str) -> dict:
    import_id = _mapped_import(client, ws, f"census_{as_of}.csv")
    generated = client.post(
        f"/api/workspaces/{ws}/imports/{import_id}/generate",
        json={"census_as_of_date": as_of},
    )
    assert generated.status_code == 202, generated.text
    files = client.get(f"/api/workspaces/{ws}/parquet-files").json()
    return next(f for f in files["parquet_files"] if f["import_id"] == import_id)


def test_wizard_suggests_requires_and_stores_the_date(setup) -> None:
    client, storage, ws = setup
    import_id = _mapped_import(client, ws)

    preview = client.get(f"/api/workspaces/{ws}/imports/{import_id}/mapped-preview")
    missing = client.post(f"/api/workspaces/{ws}/imports/{import_id}/generate")

    # Hire years in the synthetic census run 2015-2024.
    assert preview.json()["suggested_census_as_of_date"] == "2024-12-31"
    assert missing.status_code == 422
    record = _generate(client, ws, "2025-03-31")
    assert record["census_as_of_date"] == "2025-03-31"
    assert _setup_value(storage, ws, "census_as_of_date") == "2025-03-31"
    assert _setup_value(storage, ws, "census_parquet_path") == record["storage_path"]


def test_use_as_census_brings_the_files_own_date(setup, tmp_path: Path) -> None:
    client, storage, ws = setup
    first = _generate(client, ws, "2025-03-31")
    _generate(client, ws, "2024-06-30")
    undated = tmp_path / "workspaces" / ws / "data" / "undated.parquet"
    with duckdb.connect() as conn:
        conn.execute(
            f"COPY (SELECT 'E1' AS employee_id) TO '{undated}' (FORMAT parquet)"
        )

    def use(path: str) -> Optional[Any]:
        response = client.post(
            f"/api/workspaces/{ws}/set-census-path", json={"file_path": path}
        )
        assert response.status_code == 200, response.text
        return _setup_value(storage, ws, "census_as_of_date")

    assert _setup_value(storage, ws, "census_as_of_date") == "2024-06-30"
    assert use(first["storage_path"]) == "2025-03-31"
    # A file with no stored date clears it, so the engine infers one again.
    assert use(str(undated)) is None


def test_changing_a_files_date_updates_the_census_in_use_only(setup) -> None:
    client, storage, ws = setup
    older = _generate(client, ws, "2025-03-31")
    _generate(client, ws, "2024-06-30")

    def put(file_id: str, as_of: str) -> int:
        return client.put(
            f"/api/workspaces/{ws}/parquet-files/{file_id}/census-as-of-date",
            json={"census_as_of_date": as_of},
        ).status_code

    assert put(older["file_id"], "2025-01-31") == 200
    assert _setup_value(storage, ws, "census_as_of_date") == "2024-06-30"
    active = next(
        f
        for f in client.get(f"/api/workspaces/{ws}/parquet-files").json()[
            "parquet_files"
        ]
        if f["file_id"] != older["file_id"]
    )
    assert put(active["file_id"], "2024-07-31") == 200
    assert _setup_value(storage, ws, "census_as_of_date") == "2024-07-31"
    assert put("missing", "2024-07-31") == 404


def test_direct_upload_stores_the_suggested_date_for_confirmation(
    setup, tmp_path: Path
) -> None:
    client, storage, ws = setup
    source = tmp_path / "upload.parquet"
    with duckdb.connect() as conn:
        conn.execute(f"""COPY (SELECT 'E' || i AS employee_id,
                DATE '1980-01-01' AS employee_birth_date,
                MAKE_DATE(2020 + i % 5, 3, 1) AS employee_hire_date,
                60000.0 AS employee_gross_compensation, TRUE AS active
              FROM range(50) t(i)) TO '{source}' (FORMAT parquet)""")

    uploaded = client.post(
        f"/api/workspaces/{ws}/upload",
        files={
            "file": ("census.parquet", source.read_bytes(), "application/octet-stream")
        },
    )

    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["census_as_of_date"] == "2024-12-31"
    assert body["census_file_id"]
    assert _setup_value(storage, ws, "census_as_of_date") == "2024-12-31"
