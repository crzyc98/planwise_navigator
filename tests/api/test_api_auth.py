"""Authentication and network-security configuration tests for the API."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import planalign_api.config as api_config
from planalign_api.main import create_app


@pytest.fixture()
def client_factory(tmp_path, monkeypatch):
    """Build an app with per-test settings without reloading application modules."""

    def _create(api_token: str | None) -> TestClient:
        monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
        if api_token is not None:
            monkeypatch.setenv("PLANALIGN_API_TOKEN", api_token)

        settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
        monkeypatch.setattr(api_config, "settings", settings)
        return TestClient(create_app())

    return _create


def test_protected_router_requires_configured_bearer_token(client_factory) -> None:
    client = client_factory("shared-secret")

    assert client.get("/api/health").status_code == 200

    unauthorized = client.get("/api/workspaces")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"

    authorized = client.get(
        "/api/workspaces",
        headers={"Authorization": "Bearer shared-secret"},
    )
    assert authorized.status_code == 200

    alternate_header = client.get(
        "/api/workspaces",
        headers={"X-API-Token": "shared-secret"},
    )
    assert alternate_header.status_code == 200


def test_protected_router_allows_requests_without_configured_token(
    client_factory,
) -> None:
    client = client_factory(None)

    response = client.get("/api/workspaces")

    assert response.status_code == 200


def test_non_loopback_wildcard_cors_is_rejected(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    with pytest.raises(ValidationError, match="must not use wildcard CORS"):
        api_config.APISettings(host="0.0.0.0", cors_origins=["*"])


def test_non_loopback_without_token_logs_security_warning(monkeypatch, caplog) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    with caplog.at_level(logging.WARNING, logger="planalign_api.config"):
        api_config.APISettings(
            host="0.0.0.0",
            cors_origins=["https://studio.example.test"],
        )

    assert "SECURITY WARNING" in caplog.text
