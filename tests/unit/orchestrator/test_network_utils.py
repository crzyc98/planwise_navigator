"""Tests for planalign_orchestrator.network_utils module.

Covers the NetworkResponse/NetworkError dataclasses, structured error mapping
in CorporateNetworkClient._create_network_error, troubleshooting recommendation
generation, proxy-aware subprocess execution, and the client factory.
"""

from __future__ import annotations

import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from planalign_orchestrator import network_utils as nu
from planalign_orchestrator.network_utils import (
    CorporateNetworkClient,
    NetworkError,
    NetworkResponse,
    _generate_recommendations,
    create_network_client,
)

pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


def test_network_response_defaults_retries_zero():
    resp = NetworkResponse(
        status_code=200, content="ok", headers={}, url="http://x", elapsed_time=0.1
    )
    assert resp.retries == 0


def test_network_error_sets_timestamp_when_missing():
    err = NetworkError(error_type="X", message="boom", url="http://x")
    assert err.timestamp is not None


def test_network_error_preserves_explicit_timestamp():
    err = NetworkError(error_type="X", message="boom", url="http://x", timestamp=123.0)
    assert err.timestamp == 123.0


# ---------------------------------------------------------------------------
# _create_network_error (pure mapping; instantiate without running __init__)
# ---------------------------------------------------------------------------


@pytest.fixture()
def bare_client():
    """A client instance whose __init__ (which builds real urllib openers and
    SSL contexts) is bypassed, since _create_network_error uses no instance state."""
    return object.__new__(CorporateNetworkClient)


def test_create_network_error_http_error(bare_client):
    err = HTTPError("http://x", 404, "Not Found", hdrs=None, fp=None)
    result = bare_client._create_network_error(err, "http://x", retry_count=2)
    assert result.error_type == "HTTP_ERROR"
    assert result.status_code == 404
    assert result.retry_count == 2
    assert "404" in result.message


def test_create_network_error_url_error(bare_client):
    result = bare_client._create_network_error(
        URLError("name resolution failed"), "http://x", retry_count=0
    )
    assert result.error_type == "CONNECTION_ERROR"
    assert result.status_code is None


def test_create_network_error_timeout(bare_client):
    result = bare_client._create_network_error(
        socket.timeout("slow"), "http://x", retry_count=1
    )
    assert result.error_type == "TIMEOUT_ERROR"


def test_create_network_error_unknown(bare_client):
    result = bare_client._create_network_error(
        ValueError("weird"), "http://x", retry_count=0
    )
    assert result.error_type == "UNKNOWN_ERROR"
    assert "weird" in result.message


# ---------------------------------------------------------------------------
# _generate_recommendations
# ---------------------------------------------------------------------------


def _diagnostics(
    *, connectivity, proxy_detected=False, proxy_working=True, errors=None
):
    return SimpleNamespace(
        connectivity_tests=connectivity,
        proxy_detected=proxy_detected,
        proxy_working=proxy_working,
        errors=errors or [],
    )


def test_recommendations_healthy_network_is_empty():
    diag = _diagnostics(connectivity={"google": True})
    system_info = {
        "dns_resolution": {"google.com": True},
        "port_connectivity": {"x": True},
    }
    assert _generate_recommendations(diag, system_info) == []


def test_recommendations_no_connectivity_flags_dns_and_ports():
    diag = _diagnostics(connectivity={"google": False})
    system_info = {
        "dns_resolution": {"google.com": False},
        "port_connectivity": {"google.com:443": False},
    }
    recs = _generate_recommendations(diag, system_info)
    joined = " ".join(recs)
    assert "No network connectivity" in joined
    assert "DNS resolution failed" in joined
    assert "Port connectivity failed" in joined


def test_recommendations_flags_broken_proxy():
    diag = _diagnostics(
        connectivity={"google": True}, proxy_detected=True, proxy_working=False
    )
    system_info = {"dns_resolution": {}, "port_connectivity": {}}
    recs = _generate_recommendations(diag, system_info)
    assert any("Proxy configuration detected but not working" in r for r in recs)


def test_recommendations_flags_errors():
    diag = _diagnostics(connectivity={"google": True}, errors=["TLS handshake failed"])
    system_info = {"dns_resolution": {}, "port_connectivity": {}}
    recs = _generate_recommendations(diag, system_info)
    assert any("Review error details" in r for r in recs)


# ---------------------------------------------------------------------------
# test_subprocess_with_proxy
# ---------------------------------------------------------------------------


def _proxy_config(
    *, http=None, https=None, no_proxy=None, ca_bundle=None, total_timeout=30
):
    return SimpleNamespace(
        proxy=SimpleNamespace(
            http_proxy=http, https_proxy=https, no_proxy=no_proxy or []
        ),
        certificates=SimpleNamespace(ca_bundle_path=ca_bundle),
        timeouts=SimpleNamespace(total_timeout=total_timeout),
    )


def test_subprocess_with_proxy_injects_env_and_runs():
    cfg = _proxy_config(
        http="http://proxy:8080",
        https="http://proxy:8080",
        no_proxy=["localhost"],
        ca_bundle="/certs/ca.pem",
    )
    completed = subprocess.CompletedProcess(
        args=["echo"], returncode=0, stdout="hi", stderr=""
    )

    with patch.object(nu, "load_network_config", return_value=cfg), patch.object(
        nu.subprocess, "run", return_value=completed
    ) as run_mock:
        result = nu.test_subprocess_with_proxy(["echo", "hi"], env={})

    assert result.returncode == 0
    passed_env = run_mock.call_args.kwargs["env"]
    assert passed_env["HTTP_PROXY"] == "http://proxy:8080"
    assert passed_env["HTTPS_PROXY"] == "http://proxy:8080"
    assert passed_env["NO_PROXY"] == "localhost"
    assert passed_env["REQUESTS_CA_BUNDLE"] == "/certs/ca.pem"


def test_subprocess_with_proxy_handles_timeout():
    cfg = _proxy_config(total_timeout=5)
    with patch.object(nu, "load_network_config", return_value=cfg), patch.object(
        nu.subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired(cmd=["sleep"], timeout=5),
    ):
        result = nu.test_subprocess_with_proxy(["sleep", "10"], env={})

    assert result.returncode == 124
    assert "timed out" in result.stderr


# ---------------------------------------------------------------------------
# create_network_client
# ---------------------------------------------------------------------------


def test_create_network_client_uses_loaded_config():
    sentinel_config = MagicMock(name="config")
    sentinel_client = MagicMock(name="client")
    with patch.object(
        nu, "load_network_config", return_value=sentinel_config
    ) as load_mock, patch.object(
        nu, "CorporateNetworkClient", return_value=sentinel_client
    ) as client_cls:
        result = create_network_client("/path/cfg.json")

    load_mock.assert_called_once_with("/path/cfg.json")
    client_cls.assert_called_once_with(sentinel_config)
    assert result is sentinel_client
