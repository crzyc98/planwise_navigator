"""Regression tests for issue #532: response security headers and the
absolute ``storage_path`` no longer leaking out of workspace responses.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

import planalign_api.config as api_config
import planalign_api.routers.system as system_router

pytestmark = [pytest.mark.fast]


def _create_workspace(client, name: str = "Security Test Workspace") -> dict:
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_workspace_responses_omit_storage_path(client_factory) -> None:
    client = client_factory(None)

    created = _create_workspace(client)
    assert "storage_path" not in created

    fetched = client.get(f"/api/workspaces/{created['id']}")
    assert fetched.status_code == 200
    assert "storage_path" not in fetched.json()

    updated = client.put(
        f"/api/workspaces/{created['id']}", json={"description": "updated"}
    )
    assert updated.status_code == 200
    assert "storage_path" not in updated.json()


@pytest.mark.parametrize("path", ["/api/health", "/api/workspaces"])
def test_json_responses_get_locked_down_security_headers(
    client_factory, path: str
) -> None:
    client = client_factory(None)

    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'"
    )


def test_docs_page_gets_a_scoped_csp_that_still_allows_swagger_assets(
    client_factory,
) -> None:
    client = client_factory(None)

    response = client.get("/api/docs")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    csp = response.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp


def test_health_uses_fixed_messages_and_logs_details_server_side(
    client_factory, tmp_path, monkeypatch, caplog
) -> None:
    client = client_factory(None)
    missing_config = tmp_path / "private-dir" / "missing_config.yaml"
    blocked_workspaces = tmp_path / "restricted-root" / "workspaces"
    monkeypatch.setattr(
        api_config,
        "settings",
        api_config.APISettings(
            workspaces_root=blocked_workspaces,
            default_config_path=missing_config,
            storage_limit_gb=1.0,
        ),
    )

    def _fail_mkdir(self: Path, *args, **kwargs) -> None:
        if self == blocked_workspaces:
            raise PermissionError(f"Permission denied: '{blocked_workspaces}'")

    monkeypatch.setattr(Path, "mkdir", _fail_mkdir)
    monkeypatch.setattr(
        system_router,
        "workspace_totals",
        lambda *_args, **_kwargs: SimpleNamespace(total_mb=975.4),
    )

    with caplog.at_level(logging.WARNING, logger="planalign_api.routers.system"):
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "healthy": False,
        "issues": ["Workspaces storage is unavailable."],
        "warnings": [
            "Default configuration file not found; new workspaces will use built-in defaults.",
            "Workspace storage usage exceeds 90% of configured limit.",
        ],
    }
    serialized = response.text
    assert str(blocked_workspaces) not in serialized
    assert str(missing_config) not in serialized
    assert "Permission denied" not in serialized
    assert "975.4" not in serialized

    assert str(blocked_workspaces) in caplog.text
    assert "Permission denied" in caplog.text
    assert str(missing_config) in caplog.text
    assert "975.4MB" in caplog.text
