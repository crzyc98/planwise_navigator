import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from planalign_api.main import create_app
from planalign_api import auth
from planalign_api.routers import provenance as provenance_router_module
from tests.fixtures.run_provenance import (
    RUN_ID,
    build_archive,
    build_duplicate_archives,
)

pytestmark = pytest.mark.fast


def test_json_and_zip_have_same_digest_and_cache_headers(tmp_path: Path, monkeypatch):
    build_archive(tmp_path)
    monkeypatch.setattr(
        provenance_router_module,
        "get_settings",
        lambda: SimpleNamespace(workspaces_root=tmp_path),
    )
    client = TestClient(create_app())
    response = client.get(f"/api/runs/{RUN_ID}/provenance")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    digest = response.json()["report"]["digest"]["value"]
    assert response.headers["etag"] == f'"{digest}"'
    assert digest in response.json()["audit_sheet"]
    zipped = client.get(
        f"/api/runs/{RUN_ID}/provenance", headers={"Accept": "application/zip"}
    )
    assert zipped.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as archive:
        assert archive.namelist() == [
            f"{RUN_ID}-provenance.json",
            f"{RUN_ID}-provenance.md",
        ]
        assert digest in archive.read(archive.namelist()[1]).decode()
    repeated = client.get(
        f"/api/runs/{RUN_ID}/provenance", headers={"Accept": "application/zip"}
    )
    assert repeated.content == zipped.content


def test_api_maps_not_found_and_accept(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        provenance_router_module,
        "get_settings",
        lambda: SimpleNamespace(workspaces_root=tmp_path),
    )
    client = TestClient(create_app())
    assert client.get(f"/api/runs/{RUN_ID}/provenance").status_code == 404
    assert (
        client.get(
            f"/api/runs/{RUN_ID}/provenance", headers={"Accept": "text/html"}
        ).status_code
        == 406
    )


def test_api_returns_valid_incomplete_and_duplicate_identity_status(
    tmp_path: Path, monkeypatch
):
    build_archive(tmp_path / "failed", status="failed")
    monkeypatch.setattr(
        provenance_router_module,
        "get_settings",
        lambda: SimpleNamespace(workspaces_root=tmp_path / "failed"),
    )
    client = TestClient(create_app())
    response = client.get(f"/api/runs/{RUN_ID}/provenance")
    assert response.status_code == 200
    assert response.json()["report"]["verification_disposition"] == "incomplete"
    build_duplicate_archives(tmp_path / "duplicate")
    monkeypatch.setattr(
        provenance_router_module,
        "get_settings",
        lambda: SimpleNamespace(workspaces_root=tmp_path / "duplicate"),
    )
    assert client.get(f"/api/runs/{RUN_ID}/provenance").status_code == 422


def test_api_uses_existing_token_protection(tmp_path: Path, monkeypatch):
    build_archive(tmp_path)
    monkeypatch.setattr(
        provenance_router_module,
        "get_settings",
        lambda: SimpleNamespace(workspaces_root=tmp_path),
    )
    monkeypatch.setattr(
        auth, "get_settings", lambda: SimpleNamespace(api_token="audit-token")
    )
    client = TestClient(create_app())
    assert client.get(f"/api/runs/{RUN_ID}/provenance").status_code == 401
    assert (
        client.get(
            f"/api/runs/{RUN_ID}/provenance", headers={"X-API-Token": "audit-token"}
        ).status_code
        == 200
    )
