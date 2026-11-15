"""Host header allowlist tests for the PlanAlign API."""

from __future__ import annotations

import pytest
from starlette.testclient import WebSocketDenialResponse

import planalign_api.config as api_config
from planalign_api.trusted_hosts import normalize_host

pytestmark = [pytest.mark.fast]

_ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture()
def default_hosts_client(client_factory, monkeypatch):
    """Client built with the production Host allowlist (no test overrides)."""
    monkeypatch.delenv("PLANALIGN_API_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("PLANALIGN_API_HOST", raising=False)
    return client_factory(None)


@pytest.mark.parametrize(
    "host", ["localhost", "localhost:8000", "127.0.0.1:5173", "[::1]:8000"]
)
def test_loopback_hosts_are_accepted(default_hosts_client, host: str) -> None:
    response = default_hosts_client.get("/api/health", headers={"Host": host})

    assert response.status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "testserver"])
def test_unlisted_hosts_are_rejected(default_hosts_client, host: str) -> None:
    response = default_hosts_client.get("/api/health", headers={"Host": host})

    assert response.status_code == 400


def test_allowed_hosts_env_extends_the_list(client_factory, monkeypatch) -> None:
    monkeypatch.setenv("PLANALIGN_API_ALLOWED_HOSTS", "localhost, studio.example")
    client = client_factory(None)

    assert (
        client.get("/api/health", headers={"Host": "studio.example"}).status_code == 200
    )
    assert (
        client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    )


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
        ("", ""),
    ],
)
def test_normalize_host(raw: str, expected: str) -> None:
    assert normalize_host(raw) == expected
