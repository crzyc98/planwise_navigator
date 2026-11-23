#!/usr/bin/env python3
"""Corporate proxy and certificate configuration for subprocess environments.

Used by ``planalign_orchestrator.dbt_runner`` (via ``network_utils``) to
propagate corporate proxy and CA bundle environment variables to dbt
subprocesses. PlanAlign Engine has zero cloud dependencies and performs no
outbound connectivity checks (see ``SECURITY.md``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProxyConfig(BaseModel):
    """Corporate proxy configuration."""

    http_proxy: Optional[str] = Field(
        None, description="HTTP proxy URL (e.g., http://proxy.company.com:8080)"
    )
    https_proxy: Optional[str] = Field(
        None, description="HTTPS proxy URL (e.g., http://proxy.company.com:8080)"
    )
    ftp_proxy: Optional[str] = Field(None, description="FTP proxy URL (optional)")
    no_proxy: List[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "*.local"],
        description="List of hosts to bypass proxy",
    )

    username: Optional[str] = Field(None, description="Proxy authentication username")
    password: Optional[str] = Field(None, description="Proxy authentication password")
    use_system_auth: bool = Field(
        True, description="Use system authentication (NTLM/Kerberos)"
    )

    proxy_timeout: int = Field(30, description="Proxy connection timeout in seconds")
    proxy_retries: int = Field(3, description="Number of proxy connection retries")

    @field_validator("http_proxy", "https_proxy", "ftp_proxy")
    @classmethod
    def validate_proxy_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("Proxy URL must start with http:// or https://")
        return v

    @field_validator("proxy_timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v <= 0 or v > 300:
            raise ValueError("Proxy timeout must be between 1 and 300 seconds")
        return v


class CertificateConfig(BaseModel):
    """Corporate CA certificate configuration for subprocesses."""

    ca_bundle_path: Optional[str] = Field(
        None, description="Path to corporate CA certificate bundle"
    )
    verify_ssl: bool = Field(True, description="Enable SSL certificate verification")
    custom_cert_dir: Optional[str] = Field(
        None, description="Custom certificate directory"
    )

    @field_validator("ca_bundle_path", "custom_cert_dir")
    @classmethod
    def validate_paths(cls, v: Optional[str]) -> Optional[str]:
        if v and not Path(v).exists():
            raise ValueError(f"Certificate path does not exist: {v}")
        return v


class NetworkTimeoutConfig(BaseModel):
    """Timeout configuration for subprocess execution."""

    connection_timeout: int = Field(30, description="TCP connection timeout in seconds")
    read_timeout: int = Field(60, description="Socket read timeout in seconds")
    total_timeout: int = Field(300, description="Total operation timeout in seconds")
    dbt_command_timeout: int = Field(
        1800, description="dbt command execution timeout (30 minutes)"
    )
    database_timeout: int = Field(60, description="Database connection timeout")

    @field_validator("connection_timeout", "read_timeout", "total_timeout")
    @classmethod
    def validate_timeouts(cls, v: int) -> int:
        if v <= 0 or v > 3600:
            raise ValueError("Timeout must be between 1 and 3600 seconds")
        return v


class CorporateNetworkConfig(BaseModel):
    """Corporate proxy, certificate, and timeout configuration."""

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)

    enabled: bool = Field(True, description="Enable corporate network support")
    auto_detect_proxy: bool = Field(
        True, description="Auto-detect system proxy settings"
    )

    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    certificates: CertificateConfig = Field(default_factory=CertificateConfig)
    timeouts: NetworkTimeoutConfig = Field(default_factory=NetworkTimeoutConfig)


def detect_system_proxy() -> Optional[ProxyConfig]:
    """Auto-detect system proxy configuration from environment variables."""
    proxy_config = ProxyConfig()

    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")

    if http_proxy:
        proxy_config.http_proxy = http_proxy
    if https_proxy:
        proxy_config.https_proxy = https_proxy
    if no_proxy:
        proxy_config.no_proxy = [host.strip() for host in no_proxy.split(",")]

    if proxy_config.http_proxy or proxy_config.https_proxy:
        return proxy_config

    return None


def load_network_config(config_path: Optional[str] = None) -> CorporateNetworkConfig:
    """Create corporate network configuration with optional env proxy auto-detection."""
    config = CorporateNetworkConfig()

    if config.auto_detect_proxy:
        detected_proxy = detect_system_proxy()
        if detected_proxy:
            config.proxy = detected_proxy

    return config
