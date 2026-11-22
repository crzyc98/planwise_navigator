"""Tests for planalign_orchestrator.network_utils and planalign_core.network_config.

Covers proxy-aware subprocess execution and system proxy environment detection.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from planalign_core.network_config import CorporateNetworkConfig, load_network_config
from planalign_orchestrator import network_utils as nu

pytestmark = pytest.mark.fast


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


def test_subprocess_with_proxy_injects_env_and_runs() -> None:
    cfg = _proxy_config(
        http="http://proxy:8080",
        https="http://proxy:8080",
        no_proxy=["localhost"],
        ca_bundle="/certs/ca.pem",
    )
    completed = subprocess.CompletedProcess(
        args=["echo"], returncode=0, stdout="hi", stderr=""
    )

    with (
        patch.object(nu, "load_network_config", return_value=cfg),
        patch.object(nu.subprocess, "run", return_value=completed) as run_mock,
    ):
        result = nu.test_subprocess_with_proxy(["echo", "hi"], env={})

    assert result.returncode == 0
    passed_env = run_mock.call_args.kwargs["env"]
    assert passed_env["HTTP_PROXY"] == "http://proxy:8080"
    assert passed_env["HTTPS_PROXY"] == "http://proxy:8080"
    assert passed_env["NO_PROXY"] == "localhost"
    assert passed_env["REQUESTS_CA_BUNDLE"] == "/certs/ca.pem"


def test_subprocess_with_proxy_handles_timeout() -> None:
    cfg = _proxy_config(total_timeout=5)
    with (
        patch.object(nu, "load_network_config", return_value=cfg),
        patch.object(
            nu.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["sleep"], timeout=5),
        ),
    ):
        result = nu.test_subprocess_with_proxy(["sleep", "10"], env={})

    assert result.returncode == 124
    assert "timed out" in result.stderr


def test_load_network_config_detects_env_proxy_without_outbound_probes(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://corp-proxy.internal:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://corp-proxy.internal:8443")
    monkeypatch.setenv("NO_PROXY", "localhost, 127.0.0.1")

    cfg = load_network_config()

    assert isinstance(cfg, CorporateNetworkConfig)
    assert cfg.proxy.http_proxy == "http://corp-proxy.internal:8080"
    assert cfg.proxy.https_proxy == "http://corp-proxy.internal:8443"
    assert cfg.proxy.no_proxy == ["localhost", "127.0.0.1"]
    assert not hasattr(cfg, "test_endpoints")
    assert not hasattr(cfg, "connectivity_check")
