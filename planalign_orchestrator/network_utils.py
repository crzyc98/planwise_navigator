#!/usr/bin/env python3
"""Subprocess proxy-environment helpers for dbt execution.

Provides ``load_network_config`` and ``test_subprocess_with_proxy`` for
``planalign_orchestrator.dbt_runner``. Outbound HTTP client and connectivity
probe helpers were removed under issue #1192 (zero cloud dependencies).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union

from planalign_core.network_config import load_network_config

__all__ = ["load_network_config", "test_subprocess_with_proxy"]


def test_subprocess_with_proxy(
    command: List[str],
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    cwd: Optional[Union[str, Path]] = None,
) -> subprocess.CompletedProcess:
    """Execute a subprocess command with proxy and CA environment variables."""
    config = load_network_config()

    if env is None:
        env = os.environ.copy()

    if config.proxy.http_proxy:
        env["HTTP_PROXY"] = config.proxy.http_proxy
        env["http_proxy"] = config.proxy.http_proxy

    if config.proxy.https_proxy:
        env["HTTPS_PROXY"] = config.proxy.https_proxy
        env["https_proxy"] = config.proxy.https_proxy

    if config.proxy.no_proxy:
        env["NO_PROXY"] = ",".join(config.proxy.no_proxy)
        env["no_proxy"] = ",".join(config.proxy.no_proxy)

    if config.certificates.ca_bundle_path:
        env["REQUESTS_CA_BUNDLE"] = config.certificates.ca_bundle_path
        env["SSL_CERT_FILE"] = config.certificates.ca_bundle_path
        env["CURL_CA_BUNDLE"] = config.certificates.ca_bundle_path

    timeout = timeout or config.timeouts.total_timeout

    try:
        return subprocess.run(
            command,
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=e.stdout or "",
            stderr=f"Command timed out after {timeout} seconds",
        )
