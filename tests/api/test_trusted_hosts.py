"""Host header allowlist tests for the PlanAlign API."""

from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import WebSocketDenialResponse
from starlette.types import Message, Receive, Scope, Send

import planalign_api.config as api_config
from planalign_api.trusted_hosts import TrustedHostMiddleware, normalize_host

pytestmark = [pytest.mark.fast]

_ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture()
def default_hosts_client(client_factory, monkeypatch):
    """Client built with the production Host allowlist (no test overrides)."""
    monkeypatch.delenv("PLANALIGN_API_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("PLANALIGN_API_HOST", raising=False)
    return client_factory(None)


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "localhost:8000",
        "127.0.0.1",
        "127.0.0.1:5173",
        "[::1]",
        "[::1]:8000",
    ],
)
def test_loopback_hosts_are_accepted(default_hosts_client, host: str) -> None:
    response = default_hosts_client.get("/api/health", headers={"Host": host})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:8000", "testserver", "localhost:abc"]
)
def test_unlisted_hosts_are_rejected(default_hosts_client, host: str) -> None:
    response = default_hosts_client.get("/api/health", headers={"Host": host})

    assert response.status_code == 400
    assert response.text == "Invalid host header"
    assert host not in response.text


def test_allowed_hosts_env_replaces_the_defaults(client_factory, monkeypatch) -> None:
    monkeypatch.setenv("PLANALIGN_API_ALLOWED_HOSTS", "localhost, studio.example")
    monkeypatch.delenv("PLANALIGN_API_HOST", raising=False)
    client = client_factory(None)

    def status(host: str) -> int:
        return client.get("/api/health", headers={"Host": host}).status_code

    assert status("studio.example") == 200
    assert status("localhost") == 200
    assert status("[::1]:8000") == 400
    assert status("evil.example") == 400


@pytest.mark.parametrize(
    "value", ["", " , ", "*", "*.corp.example", "[::1", ":8000", "localhost:abc"]
)
def test_empty_or_wildcard_allowed_hosts_are_rejected(monkeypatch, value: str) -> None:
    monkeypatch.setenv("PLANALIGN_API_ALLOWED_HOSTS", value)

    with pytest.raises(ValueError, match="PLANALIGN_API_ALLOWED_HOSTS"):
        api_config.APISettings()


def test_specific_bind_host_is_trusted_but_wildcard_is_not(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_ALLOWED_HOSTS", raising=False)

    lan = api_config.APISettings(host="192.0.2.10")
    wildcard = api_config.APISettings(host="0.0.0.0")

    assert "192.0.2.10" in lan.trusted_hosts
    assert "0.0.0.0" not in wildcard.trusted_hosts


@pytest.mark.parametrize("path", ["/ws/simulation/run-1", "/ws/batch/batch-1"])
def test_websocket_with_unlisted_host_is_rejected(
    default_hosts_client, path: str
) -> None:
    with pytest.raises(WebSocketDenialResponse) as error:
        with default_hosts_client.websocket_connect(
            path, headers={"Origin": _ALLOWED_ORIGIN, "Host": "evil.example"}
        ):
            pass

    assert error.value.status_code == 400


def test_websocket_with_loopback_host_connects(default_hosts_client) -> None:
    with default_hosts_client.websocket_connect(
        "/ws/batch/batch-1", headers={"Origin": _ALLOWED_ORIGIN, "Host": "localhost"}
    ):
        pass


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("LocalHost:8000", "localhost"),
        ("[::1]:8000", "::1"),
        ("[::1]", "::1"),
        ("::1", "::1"),
        ("[::1", ""),
        ("[::1]evil.example", ""),
        ("[::1]:80:80", ""),
        ("localhost:abc", ""),
        ("localhost:", ""),
        (":8000", ""),
        ("", ""),
    ],
)
def test_normalize_host(raw: str, expected: str) -> None:
    assert normalize_host(raw) == expected


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"host", b"localhost"), (b"host", b"evil.example")],
    ],
)
def test_missing_or_duplicate_host_headers_are_rejected(
    headers: list[tuple[bytes, bytes]],
) -> None:
    sent: list[Message] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("inner app should not be called")

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = TrustedHostMiddleware(inner, allowed_hosts=["localhost", "[::1"])
    scope: Scope = {"type": "http", "headers": headers}

    asyncio.run(middleware(scope, receive, send))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 400
    assert sent[1]["body"] == b"Invalid host header"
