"""Authentication and network-security configuration tests for the API."""

from __future__ import annotations

import logging

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

import planalign_api.auth as api_auth
import planalign_api.config as api_config

pytestmark = [pytest.mark.fast]

_ALLOWED_ORIGIN = "http://localhost:5173"
_TEST_TOKEN = "test-shared-secret-token"


def test_protected_router_requires_configured_bearer_token(client_factory) -> None:
    client = client_factory(_TEST_TOKEN)

    assert client.get("/api/health").status_code == 200

    unauthorized = client.get("/api/workspaces")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"

    authorized = client.get(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
    )
    assert authorized.status_code == 200

    alternate_header = client.get(
        "/api/workspaces",
        headers={"X-API-Token": _TEST_TOKEN},
    )
    assert alternate_header.status_code == 200


def test_protected_router_allows_requests_without_configured_token(
    client_factory,
) -> None:
    client = client_factory(None)

    response = client.get("/api/workspaces")

    assert response.status_code == 200


def test_artifact_ticket_issuance_requires_authentication(client_factory) -> None:
    client = client_factory(_TEST_TOKEN)
    url = "/api/scenarios/missing/artifact-download-url/results.xlsx"

    assert client.post(url).status_code == 401
    assert (
        client.post(url, headers={"Authorization": f"Bearer {_TEST_TOKEN}"}).status_code
        == 404
    )
    assert client.get("/api/artifact-download/invalid").status_code == 403


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_requires_configured_token(client_factory, path: str) -> None:
    client = client_factory(_TEST_TOKEN)

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(path, headers={"Origin": _ALLOWED_ORIGIN}):
            pass

    assert error.value.code == 1008


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_accepts_query_token(client_factory, path: str) -> None:
    client = client_factory(_TEST_TOKEN)

    with client.websocket_connect(
        f"{path}?token={_TEST_TOKEN}", headers={"Origin": _ALLOWED_ORIGIN}
    ):
        pass


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
@pytest.mark.parametrize("bad_token", ["wrong-secret-token-value", "café", ""])
def test_websocket_rejects_wrong_token(
    client_factory, path: str, bad_token: str
) -> None:
    client = client_factory(_TEST_TOKEN)

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
    client = client_factory(_TEST_TOKEN)

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            f"{path}?token={_TEST_TOKEN}",
            headers={"Origin": "http://attacker.example"},
        ):
            pass

    assert error.value.code == 1008


@pytest.mark.parametrize(
    "invalid_token",
    [
        "",
        "   ",
        " " * 20,
        "a" * 15,
        "   short        ",
        "too-short-tok",
    ],
)
def test_empty_blank_or_short_api_token_is_rejected_without_echoing_value(
    monkeypatch, invalid_token: str
) -> None:
    monkeypatch.setenv("PLANALIGN_API_TOKEN", invalid_token)

    with pytest.raises(ValidationError) as exc_info:
        api_config.APISettings()

    message = str(exc_info.value)
    assert "PLANALIGN_API_TOKEN" in message
    assert "16" in message
    if invalid_token.strip():
        assert invalid_token.strip() not in message


def test_minimum_length_api_token_succeeds_and_is_hidden_from_repr(monkeypatch) -> None:
    token = "a" * 16
    monkeypatch.setenv("PLANALIGN_API_TOKEN", token)

    settings = api_config.APISettings()

    assert settings.api_token == token
    assert token not in repr(settings)


def test_unset_api_token_remains_none(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    settings = api_config.APISettings()

    assert settings.api_token is None


def test_empty_supplied_or_configured_token_never_authenticates(
    client_factory, monkeypatch
) -> None:
    client = client_factory(None)
    monkeypatch.setattr(
        api_auth,
        "get_settings",
        lambda: SimpleNamespace(api_token="", cors_origins=[_ALLOWED_ORIGIN]),
    )

    assert client.get("/api/workspaces").status_code == 401
    assert (
        client.get("/api/workspaces", headers={"Authorization": "Bearer "}).status_code
        == 401
    )
    assert client.get("/api/workspaces", headers={"X-API-Token": ""}).status_code == 401

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            "/ws/simulation/run-1?token=", headers={"Origin": _ALLOWED_ORIGIN}
        ):
            pass

    assert error.value.code == 1008


@pytest.mark.parametrize("path", ["/api/docs", "/api/redoc", "/api/openapi.json"])
def test_api_docs_and_openapi_require_token_when_configured(
    client_factory, path: str
) -> None:
    client = client_factory(_TEST_TOKEN)

    unauthorized = client.get(path)
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"

    bearer_ok = client.get(path, headers={"Authorization": f"Bearer {_TEST_TOKEN}"})
    assert bearer_ok.status_code == 200

    header_ok = client.get(path, headers={"X-API-Token": _TEST_TOKEN})
    assert header_ok.status_code == 200

    if path == "/api/openapi.json":
        payload = bearer_ok.json()
        assert "openapi" in payload
        assert "/api/health" in payload["paths"]
    else:
        assert "/api/openapi.json" in bearer_ok.text


@pytest.mark.parametrize("path", ["/api/docs", "/api/redoc", "/api/openapi.json"])
def test_api_docs_and_openapi_remain_open_without_configured_token(
    client_factory, path: str
) -> None:
    client = client_factory(None)

    response = client.get(path)

    assert response.status_code == 200
    if path == "/api/openapi.json":
        assert "openapi" in response.json()
    else:
        assert "/api/openapi.json" in response.text


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
