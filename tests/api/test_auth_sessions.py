"""Tests for Studio session sign-in, cookies, Origin checks, and WebSocket sessions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

import planalign_api.auth as api_auth
import planalign_api.config as api_config
import planalign_api.routers.auth as auth_router_module
from planalign_api.main import create_app
from planalign_api.sessions import SESSION_COOKIE_NAME, SessionStore

pytestmark = [pytest.mark.fast]

_ALLOWED_ORIGIN = "http://localhost:5173"
_DISALLOWED_ORIGIN = "http://other.example"
_TEST_TOKEN = "test-shared-secret-token"


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_session_endpoint_reports_open_when_no_token_configured(
    client_factory,
) -> None:
    client = client_factory(None)

    status_resp = client.get("/api/auth/session")
    assert status_resp.status_code == 200
    assert status_resp.json() == {"auth_required": False, "authenticated": False}

    sign_in = client.post(
        "/api/auth/session",
        json={"token": "anything"},
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert sign_in.status_code == 204
    assert "set-cookie" not in sign_in.headers


@pytest.mark.parametrize("bad_token", ["wrong-shared-secret-token", "café", ""])
def test_sign_in_wrong_token_returns_401_and_sets_no_cookie(
    client_factory, bad_token: str
) -> None:
    client = client_factory(_TEST_TOKEN)

    response = client.post(
        "/api/auth/session",
        json={"token": bad_token},
        headers={"Origin": _ALLOWED_ORIGIN},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid PlanAlign API token."}
    assert "set-cookie" not in response.headers
    assert SESSION_COOKIE_NAME not in client.cookies


def test_sign_in_sets_cookie_attributes_and_authenticates_protected_routes(
    client_factory,
) -> None:
    client = client_factory(_TEST_TOKEN)

    before = client.get("/api/auth/session")
    assert before.status_code == 200
    assert before.json() == {"auth_required": True, "authenticated": False}

    sign_in = client.post(
        "/api/auth/session",
        json={"token": _TEST_TOKEN},
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert sign_in.status_code == 204
    set_cookie = sign_in.headers["set-cookie"]
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie.lower().replace(
        "samesite=strict", "SameSite=strict"
    )
    assert "Path=/" in set_cookie
    assert "Max-Age=43200" in set_cookie
    assert "Secure" not in set_cookie

    after = client.get("/api/auth/session")
    assert after.status_code == 200
    assert after.json() == {"auth_required": True, "authenticated": True}

    workspaces = client.get("/api/workspaces")
    assert workspaces.status_code == 200


def test_sign_in_marks_cookie_secure_over_https(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLANALIGN_API_TOKEN", _TEST_TOKEN)
    settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
    monkeypatch.setattr(api_config, "settings", settings)
    client = TestClient(create_app(), base_url="https://testserver")

    sign_in = client.post(
        "/api/auth/session",
        json={"token": _TEST_TOKEN},
        headers={"Origin": _ALLOWED_ORIGIN},
    )

    assert sign_in.status_code == 204
    assert "Secure" in sign_in.headers["set-cookie"]


def test_sign_in_marks_cookie_secure_behind_https_proxy(client_factory) -> None:
    client = client_factory(_TEST_TOKEN)

    sign_in = client.post(
        "/api/auth/session",
        json={"token": _TEST_TOKEN},
        headers={"Origin": _ALLOWED_ORIGIN, "X-Forwarded-Proto": "https"},
    )

    assert sign_in.status_code == 204
    assert "Secure" in sign_in.headers["set-cookie"]


def test_cookie_authenticated_post_requires_allowed_origin(client_factory) -> None:
    client = client_factory(_TEST_TOKEN)
    sign_in = client.post(
        "/api/auth/session",
        json={"token": _TEST_TOKEN},
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert sign_in.status_code == 204

    missing_origin = client.post("/api/workspaces", json={"name": "No Origin"})
    assert missing_origin.status_code == 403

    bad_origin = client.post(
        "/api/workspaces",
        json={"name": "Bad Origin"},
        headers={"Origin": _DISALLOWED_ORIGIN},
    )
    assert bad_origin.status_code == 403

    good_origin = client.post(
        "/api/workspaces",
        json={"name": "Allowed Origin"},
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert good_origin.status_code == 201


def test_session_post_and_delete_require_allowed_origin(client_factory) -> None:
    client = client_factory(_TEST_TOKEN)

    assert (
        client.post("/api/auth/session", json={"token": _TEST_TOKEN}).status_code == 403
    )
    assert (
        client.post(
            "/api/auth/session",
            json={"token": _TEST_TOKEN},
            headers={"Origin": _DISALLOWED_ORIGIN},
        ).status_code
        == 403
    )
    assert client.delete("/api/auth/session").status_code == 403
    assert (
        client.delete(
            "/api/auth/session",
            headers={"Origin": _DISALLOWED_ORIGIN},
        ).status_code
        == 403
    )


def test_header_token_post_works_without_origin(client_factory) -> None:
    client = client_factory(_TEST_TOKEN)

    bearer = client.post(
        "/api/workspaces",
        json={"name": "Bearer Workspace"},
        headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
    )
    assert bearer.status_code == 201

    x_token = client.post(
        "/api/workspaces",
        json={"name": "Header Workspace"},
        headers={"X-API-Token": _TEST_TOKEN},
    )
    assert x_token.status_code == 201


def test_expired_session_returns_401(client_factory, monkeypatch) -> None:
    clock = _FakeClock()
    store = SessionStore(clock=clock)
    monkeypatch.setattr(api_auth, "get_session_store", lambda: store)
    monkeypatch.setattr(auth_router_module, "get_session_store", lambda: store)

    client = client_factory(_TEST_TOKEN)
    sign_in = client.post(
        "/api/auth/session",
        json={"token": _TEST_TOKEN},
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert sign_in.status_code == 204
    assert client.get("/api/workspaces").status_code == 200

    clock.advance(12 * 3600 + 1)

    assert client.get("/api/workspaces").status_code == 401
    assert client.get("/api/auth/session").json() == {
        "auth_required": True,
        "authenticated": False,
    }


def test_sign_out_revokes_session_and_clears_cookie(client_factory) -> None:
    client = client_factory(_TEST_TOKEN)
    sign_in = client.post(
        "/api/auth/session",
        json={"token": _TEST_TOKEN},
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert sign_in.status_code == 204
    saved_cookie = client.cookies[SESSION_COOKIE_NAME]

    sign_out = client.delete(
        "/api/auth/session",
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert sign_out.status_code == 204
    assert f"{SESSION_COOKIE_NAME}=" in sign_out.headers["set-cookie"]

    assert client.get("/api/workspaces").status_code == 401
    # Replaying the revoked session id must also fail.
    assert (
        client.get(
            "/api/workspaces",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={saved_cookie}"},
        ).status_code
        == 401
    )


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_accepts_session_cookie_and_rejects_query_token(
    client_factory, path: str
) -> None:
    client = client_factory(_TEST_TOKEN)

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            f"{path}?token={_TEST_TOKEN}",
            headers={"Origin": _ALLOWED_ORIGIN},
        ):
            pass
    assert error.value.code == 1008

    sign_in = client.post(
        "/api/auth/session",
        json={"token": _TEST_TOKEN},
        headers={"Origin": _ALLOWED_ORIGIN},
    )
    assert sign_in.status_code == 204

    with client.websocket_connect(path, headers={"Origin": _ALLOWED_ORIGIN}):
        pass


def test_session_store_evicts_oldest_when_at_capacity() -> None:
    clock = _FakeClock()
    store = SessionStore(max_sessions=2, clock=clock)

    first = store.create(60)
    second = store.create(60)
    third = store.create(60)

    assert not store.is_valid(first)
    assert store.is_valid(second)
    assert store.is_valid(third)
    assert store.count() == 2


def test_session_ttl_hours_setting_defaults_and_validates(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
    monkeypatch.delenv("PLANALIGN_API_SESSION_TTL_HOURS", raising=False)

    assert api_config.APISettings().session_ttl_hours == 12.0

    monkeypatch.setenv("PLANALIGN_API_SESSION_TTL_HOURS", "0")
    with pytest.raises(ValidationError):
        api_config.APISettings()
