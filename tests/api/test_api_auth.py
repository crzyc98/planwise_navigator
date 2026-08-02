"""Authentication and network-security configuration tests for the API."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

import planalign_api.config as api_config

pytestmark = [pytest.mark.fast]

_ALLOWED_ORIGIN = "http://localhost:5173"


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


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_requires_configured_token(client_factory, path: str) -> None:
    client = client_factory("shared-secret")

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(path, headers={"Origin": _ALLOWED_ORIGIN}):
            pass

    assert error.value.code == 1008


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_accepts_query_token(client_factory, path: str) -> None:
    client = client_factory("shared-secret")

    with client.websocket_connect(
        f"{path}?token=shared-secret", headers={"Origin": _ALLOWED_ORIGIN}
    ):
        pass


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
@pytest.mark.parametrize("bad_token", ["wrong-secret", "café"])
def test_websocket_rejects_wrong_token(
    client_factory, path: str, bad_token: str
) -> None:
    client = client_factory("shared-secret")

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            f"{path}?token={bad_token}", headers={"Origin": _ALLOWED_ORIGIN}
        ):
            pass

    assert error.value.code == 1008


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_allows_connections_without_configured_token(
    client_factory, path: str
) -> None:
    client = client_factory(None)

    with client.websocket_connect(path, headers={"Origin": _ALLOWED_ORIGIN}):
        pass


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
@pytest.mark.parametrize("origin", ["http://attacker.example", None])
def test_websocket_rejects_disallowed_or_missing_origin(
    client_factory, path: str, origin: str | None
) -> None:
    client = client_factory(None)
    headers = {"Origin": origin} if origin else {}

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(path, headers=headers):
            pass

    assert error.value.code == 1008


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_rejects_disallowed_origin_with_valid_token(
    client_factory, path: str
) -> None:
    client = client_factory("shared-secret")

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            f"{path}?token=shared-secret",
            headers={"Origin": "http://attacker.example"},
        ):
            pass

    assert error.value.code == 1008


def test_non_loopback_wildcard_cors_is_rejected(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    with pytest.raises(ValidationError, match="must not use wildcard CORS"):
        api_config.APISettings(host="0.0.0.0", cors_origins=["*"])


def test_non_loopback_explicit_cors_succeeds(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    settings = api_config.APISettings(
        host="0.0.0.0",
        cors_origins=["https://studio.example.test"],
    )

    assert settings.cors_origins == ["https://studio.example.test"]


def test_loopback_wildcard_cors_succeeds(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    settings = api_config.APISettings(host="127.0.0.1", cors_origins=["*"])

    assert settings.cors_origins == ["*"]


def test_non_loopback_without_token_logs_security_warning(monkeypatch, caplog) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    with caplog.at_level(logging.WARNING, logger="planalign_api.config"):
        api_config.APISettings(
            host="0.0.0.0",
            cors_origins=["https://studio.example.test"],
        )

    assert "SECURITY WARNING" in caplog.text
