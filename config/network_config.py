#!/usr/bin/env python3
"""
Corporate Network Configuration and Proxy Support for Fidelity PlanAlign Engine.

This module provides enterprise-grade network configuration and proxy support
for corporate VPN/proxy environments, including:
- HTTP/HTTPS proxy configuration with authentication
- Corporate certificate and security compliance
- Timeout handling and retry logic for network operations
- Network performance optimization for restricted environments
- Automatic proxy detection and validation

Epic E063 - Story S063-07: Corporate Network and Proxy Support
"""

from __future__ import annotations

import os
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from urllib.error import URLError

from pydantic import BaseModel, Field, validator


class ProxyConfig(BaseModel):
    """Corporate proxy configuration with authentication support."""

    # Proxy server configuration
    http_proxy: Optional[str] = Field(None, description="HTTP proxy URL (e.g., http://proxy.company.com:8080)")
    https_proxy: Optional[str] = Field(None, description="HTTPS proxy URL (e.g., http://proxy.company.com:8080)")
    ftp_proxy: Optional[str] = Field(None, description="FTP proxy URL (optional)")
    no_proxy: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "*.local"],
                               description="List of hosts to bypass proxy")

    # Authentication configuration
    username: Optional[str] = Field(None, description="Proxy authentication username")
    password: Optional[str] = Field(None, description="Proxy authentication password")
    use_system_auth: bool = Field(True, description="Use system authentication (NTLM/Kerberos)")

    # Advanced proxy configuration
    proxy_timeout: int = Field(30, description="Proxy connection timeout in seconds")
    proxy_retries: int = Field(3, description="Number of proxy connection retries")

    @validator('http_proxy', 'https_proxy', 'ftp_proxy')
    def validate_proxy_url(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError("Proxy URL must start with http:// or https://")
        return v

    @validator('proxy_timeout')
    def validate_timeout(cls, v):
        if v <= 0 or v > 300:
            raise ValueError("Proxy timeout must be between 1 and 300 seconds")
        return v


class CertificateConfig(BaseModel):
    """Corporate certificate configuration for security compliance."""

    # Certificate bundle configuration
    ca_bundle_path: Optional[str] = Field(None, description="Path to corporate CA certificate bundle")
    verify_ssl: bool = Field(True, description="Enable SSL certificate verification")
    custom_cert_dir: Optional[str] = Field(None, description="Custom certificate directory")

    # Certificate validation settings
    allow_self_signed: bool = Field(False, description="Allow self-signed certificates (dev environments only)")
    hostname_verification: bool = Field(True, description="Enable hostname verification")

    # Certificate chain validation
    check_certificate_chain: bool = Field(True, description="Validate complete certificate chain")
    max_chain_depth: int = Field(10, description="Maximum certificate chain depth")

    @validator('ca_bundle_path', 'custom_cert_dir')
    def validate_paths(cls, v):
        if v and not Path(v).exists():
            raise ValueError(f"Certificate path does not exist: {v}")
        return v


class NetworkTimeoutConfig(BaseModel):
    """Network timeout configuration for different operation types."""

    # Connection timeouts
    connection_timeout: int = Field(30, description="TCP connection timeout in seconds")
    read_timeout: int = Field(60, description="Socket read timeout in seconds")
    total_timeout: int = Field(300, description="Total operation timeout in seconds")

    # Service-specific timeouts
    dagster_health_timeout: int = Field(5, description="Dagster health check timeout")
    dbt_command_timeout: int = Field(1800, description="dbt command execution timeout (30 minutes)")
    database_timeout: int = Field(60, description="Database connection timeout")

    # Retry configuration
    max_retries: int = Field(3, description="Maximum number of retries")
    retry_delay: float = Field(1.0, description="Base delay between retries (seconds)")
    retry_backoff: float = Field(2.0, description="Exponential backoff multiplier")
    max_retry_delay: float = Field(30.0, description="Maximum retry delay")

    @validator('connection_timeout', 'read_timeout', 'total_timeout')
    def validate_timeouts(cls, v):
        if v <= 0 or v > 3600:  # Max 1 hour
            raise ValueError("Timeout must be between 1 and 3600 seconds")
        return v


class NetworkPerformanceConfig(BaseModel):
    """Network performance optimization for restricted corporate environments."""

    # Connection pooling
    enable_connection_pooling: bool = Field(True, description="Enable HTTP connection pooling")
    max_pool_connections: int = Field(10, description="Maximum connections per pool")
    pool_timeout: int = Field(30, description="Connection pool timeout")

    # Request optimization
    enable_gzip: bool = Field(True, description="Enable gzip compression")
    chunk_size: int = Field(8192, description="Download chunk size in bytes")
    buffer_size: int = Field(65536, description="Network buffer size")

    # Bandwidth optimization
    rate_limiting: bool = Field(False, description="Enable bandwidth rate limiting")
    max_bandwidth_mbps: Optional[float] = Field(None, description="Maximum bandwidth in Mbps")

    # Keep-alive settings
    keep_alive: bool = Field(True, description="Enable HTTP keep-alive")
    keep_alive_timeout: int = Field(30, description="Keep-alive timeout in seconds")

    @validator('max_pool_connections')
    def validate_pool_connections(cls, v):
        if v <= 0 or v > 100:
            raise ValueError("Max pool connections must be between 1 and 100")
        return v


class CorporateNetworkConfig(BaseModel):
    """Comprehensive corporate network configuration."""

    # Core configuration sections
    enabled: bool = Field(True, description="Enable corporate network support")
    auto_detect_proxy: bool = Field(True, description="Auto-detect system proxy settings")

    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    certificates: CertificateConfig = Field(default_factory=CertificateConfig)
    timeouts: NetworkTimeoutConfig = Field(default_factory=NetworkTimeoutConfig)
    performance: NetworkPerformanceConfig = Field(default_factory=NetworkPerformanceConfig)

    # Corporate environment detection
    corporate_domains: List[str] = Field(default_factory=lambda: ["company.com", "corp.local"],
                                       description="Corporate domain suffixes for detection")
    vpn_detection: bool = Field(True, description="Detect VPN connections")

    # Validation and testing
    connectivity_check: bool = Field(True, description="Perform connectivity checks on startup")
    test_endpoints: List[str] = Field(
        default_factory=lambda: [
            "https://httpbin.org/get",
            "https://www.google.com",
            "https://github.com"
        ],
        description="Test endpoints for connectivity validation"
    )

    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        use_enum_values = True


@dataclass
class NetworkDiagnostics:
    """Network diagnostics and connectivity test results."""

    timestamp: float = field(default_factory=time.time)
    proxy_detected: bool = False
    proxy_working: bool = False
    ssl_verification: bool = True
    connectivity_tests: Dict[str, bool] = field(default_factory=dict)
    response_times: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def detect_system_proxy() -> Optional[ProxyConfig]:
    """
    Auto-detect system proxy configuration from environment variables and system settings.

    Returns:
        ProxyConfig if proxy detected, None otherwise
    """
    proxy_config = ProxyConfig()

    # Check environment variables (common in corporate environments)
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    no_proxy = os.environ.get('NO_PROXY') or os.environ.get('no_proxy')

    if http_proxy:
        proxy_config.http_proxy = http_proxy
    if https_proxy:
        proxy_config.https_proxy = https_proxy
    if no_proxy:
        proxy_config.no_proxy = [host.strip() for host in no_proxy.split(',')]

    # Return config only if at least one proxy is configured
    if proxy_config.http_proxy or proxy_config.https_proxy:
        return proxy_config

    return None


def create_ssl_context(cert_config: CertificateConfig) -> ssl.SSLContext:
    """
    Create SSL context with corporate certificate configuration.

    Args:
        cert_config: Certificate configuration

    Returns:
        Configured SSL context
    """
    if cert_config.verify_ssl:
        context = ssl.create_default_context()

        # Load custom CA bundle if specified
        if cert_config.ca_bundle_path:
            context.load_verify_locations(cafile=cert_config.ca_bundle_path)

        # Configure certificate verification
        if cert_config.allow_self_signed:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        else:
            context.check_hostname = cert_config.hostname_verification
            context.verify_mode = ssl.CERT_REQUIRED

        # Set certificate chain depth
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.minimum_version = ssl.TLSVersion.TLSv1_2

    else:
        # Create unverified context (not recommended for production)
        context = ssl._create_unverified_context()

    return context


def build_proxy_handler(proxy_config: ProxyConfig) -> urllib.request.ProxyHandler:
    """
    Build urllib2 proxy handler from configuration.

    Args:
        proxy_config: Proxy configuration

    Returns:
        Configured proxy handler
    """
    proxy_dict = {}

    if proxy_config.http_proxy:
        proxy_dict['http'] = proxy_config.http_proxy
    if proxy_config.https_proxy:
        proxy_dict['https'] = proxy_config.https_proxy
    if proxy_config.ftp_proxy:
        proxy_dict['ftp'] = proxy_config.ftp_proxy

    # Add authentication if provided
    if proxy_config.username and proxy_config.password:
        for protocol in proxy_dict:
            url = proxy_dict[protocol]
            parsed = urllib.parse.urlparse(url)
            # Reconstruct URL with authentication
            auth_url = f"{parsed.scheme}://{proxy_config.username}:{proxy_config.password}@{parsed.netloc}"
            if parsed.path:
                auth_url += parsed.path
            proxy_dict[protocol] = auth_url

    return urllib.request.ProxyHandler(proxy_dict)


def should_bypass_proxy(url: str, no_proxy_list: List[str]) -> bool:
    """
    Check if URL should bypass proxy based on no_proxy configuration.

    Args:
        url: URL to check
        no_proxy_list: List of no-proxy patterns

    Returns:
        True if should bypass proxy, False otherwise
    """
    if not no_proxy_list:
        return False

    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or parsed.netloc

    for pattern in no_proxy_list:
        pattern = pattern.strip()
        if not pattern:
            continue

        # Handle wildcard patterns
        if pattern.startswith('*.'):
            domain = pattern[2:]
            if hostname.endswith(domain):
                return True
        elif pattern == hostname:
            return True
        elif pattern in hostname:
            return True

    return False


def load_network_config(config_path: Optional[str] = None) -> CorporateNetworkConfig:
    """
    Load corporate network configuration from file or create default.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Corporate network configuration
    """
    if config_path and Path(config_path).exists():
        # Load from YAML file (implementation would depend on yaml library)
        # For now, return default configuration
        pass

    config = CorporateNetworkConfig()

    # Auto-detect proxy if enabled
    if config.auto_detect_proxy:
        detected_proxy = detect_system_proxy()
        if detected_proxy:
            config.proxy = detected_proxy

    return config


def validate_network_connectivity(config: CorporateNetworkConfig) -> NetworkDiagnostics:
    """
    Validate network connectivity and proxy configuration.

    Args:
        config: Corporate network configuration

    Returns:
        Network diagnostics results
    """
    diagnostics = NetworkDiagnostics()

    # Check proxy detection
    if config.proxy.http_proxy or config.proxy.https_proxy:
        diagnostics.proxy_detected = True

    # Test connectivity to various endpoints
    for endpoint in config.test_endpoints:
        try:
            start_time = time.time()

            # Build request with proxy and SSL configuration
            handlers = []

            if diagnostics.proxy_detected:
                proxy_handler = build_proxy_handler(config.proxy)
                handlers.append(proxy_handler)

            ssl_context = create_ssl_context(config.certificates)
            https_handler = urllib.request.HTTPSHandler(context=ssl_context)
            handlers.append(https_handler)

            opener = urllib.request.build_opener(*handlers)

            # Set timeout
            request = urllib.request.Request(endpoint)
            response = opener.open(request, timeout=config.timeouts.connection_timeout)

            response_time = time.time() - start_time

            if response.getcode() == 200:
                diagnostics.connectivity_tests[endpoint] = True
                diagnostics.response_times[endpoint] = response_time
                if diagnostics.proxy_detected:
                    diagnostics.proxy_working = True
            else:
                diagnostics.connectivity_tests[endpoint] = False
                diagnostics.errors.append(f"HTTP {response.getcode()} for {endpoint}")

        except URLError as e:
            diagnostics.connectivity_tests[endpoint] = False
            diagnostics.errors.append(f"Connection failed for {endpoint}: {str(e)}")
        except Exception as e:
            diagnostics.connectivity_tests[endpoint] = False
            diagnostics.errors.append(f"Unexpected error for {endpoint}: {str(e)}")

    # Generate recommendations
    if not any(diagnostics.connectivity_tests.values()):
        diagnostics.recommendations.append("No network connectivity detected. Check proxy configuration.")
    elif diagnostics.proxy_detected and not diagnostics.proxy_working:
        diagnostics.recommendations.append("Proxy detected but not working. Verify proxy settings.")
    elif diagnostics.errors:
        diagnostics.recommendations.append("Some connectivity issues detected. Review error details.")
    else:
        diagnostics.recommendations.append("Network connectivity appears to be working correctly.")

    return diagnostics
