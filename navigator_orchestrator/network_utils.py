#!/usr/bin/env python3
"""
Corporate Network Utilities for PlanWise Navigator.

This module provides network utilities with corporate proxy support, including:
- HTTP client with proxy and certificate support
- Retry logic with exponential backoff
- Network diagnostics and monitoring
- Corporate environment detection
- Timeout handling for network-sensitive operations

Epic E063 - Story S063-07: Corporate Network and Proxy Support
"""

from __future__ import annotations

import json
import random
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.error import HTTPError, URLError

import os
import sys

# Add config directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / "config"))

from network_config import (
    CorporateNetworkConfig,
    NetworkDiagnostics,
    build_proxy_handler,
    create_ssl_context,
    load_network_config,
    should_bypass_proxy,
    validate_network_connectivity
)


@dataclass
class NetworkResponse:
    """Network response with metadata."""

    status_code: int
    content: Union[str, bytes]
    headers: Dict[str, str]
    url: str
    elapsed_time: float
    retries: int = 0


@dataclass
class NetworkError:
    """Network error with context information."""

    error_type: str
    message: str
    url: str
    status_code: Optional[int] = None
    retry_count: int = 0
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class CorporateNetworkClient:
    """
    HTTP client with corporate proxy and certificate support.

    Features:
    - Automatic proxy detection and configuration
    - Corporate certificate handling
    - Retry logic with exponential backoff
    - Timeout management
    - Network diagnostics
    """

    def __init__(self, config: Optional[CorporateNetworkConfig] = None):
        """
        Initialize corporate network client.

        Args:
            config: Corporate network configuration (auto-loaded if None)
        """
        self.config = config or load_network_config()
        self._setup_client()
        self._diagnostics = None
        self._session_start = time.time()

    def _setup_client(self):
        """Setup HTTP client with proxy and SSL configuration."""
        handlers = []

        # Add proxy handler if configured
        if self.config.proxy.http_proxy or self.config.proxy.https_proxy:
            proxy_handler = build_proxy_handler(self.config.proxy)
            handlers.append(proxy_handler)

        # Add SSL/TLS handler with corporate certificates
        ssl_context = create_ssl_context(self.config.certificates)
        https_handler = urllib.request.HTTPSHandler(context=ssl_context)
        handlers.append(https_handler)

        # Add cookie handler for session management
        cookie_handler = urllib.request.HTTPCookieProcessor()
        handlers.append(cookie_handler)

        # Build opener with all handlers
        self.opener = urllib.request.build_opener(*handlers)

        # Set default headers
        self.opener.addheaders = [
            ('User-Agent', 'PlanWise-Navigator/1.0 (Corporate-Environment)'),
            ('Accept', 'application/json, text/plain, */*'),
            ('Accept-Encoding', 'gzip, deflate'),
            ('Connection', 'keep-alive')
        ]

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> NetworkResponse:
        """
        Perform HTTP GET request with corporate network support.

        Args:
            url: Request URL
            params: Query parameters
            **kwargs: Additional request options

        Returns:
            Network response
        """
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"

        return self._request('GET', url, **kwargs)

    def post(self, url: str, data: Optional[Union[str, bytes, Dict]] = None,
             json_data: Optional[Dict] = None, **kwargs) -> NetworkResponse:
        """
        Perform HTTP POST request with corporate network support.

        Args:
            url: Request URL
            data: Request body data
            json_data: JSON data (automatically serialized)
            **kwargs: Additional request options

        Returns:
            Network response
        """
        if json_data:
            data = json.dumps(json_data).encode('utf-8')
            kwargs.setdefault('headers', {})['Content-Type'] = 'application/json'

        return self._request('POST', url, data=data, **kwargs)

    def _request(self, method: str, url: str, data: Optional[Union[str, bytes]] = None,
                headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None,
                max_retries: Optional[int] = None) -> NetworkResponse:
        """
        Perform HTTP request with retry logic and error handling.

        Args:
            method: HTTP method
            url: Request URL
            data: Request body
            headers: Request headers
            timeout: Request timeout
            max_retries: Maximum retry attempts

        Returns:
            Network response

        Raises:
            NetworkError: On network failure after retries
        """
        timeout = timeout or self.config.timeouts.connection_timeout
        max_retries = max_retries or self.config.timeouts.max_retries

        # Check if should bypass proxy
        if should_bypass_proxy(url, self.config.proxy.no_proxy):
            # Create a new opener without proxy for this request
            ssl_context = create_ssl_context(self.config.certificates)
            https_handler = urllib.request.HTTPSHandler(context=ssl_context)
            no_proxy_opener = urllib.request.build_opener(https_handler)
            opener = no_proxy_opener
        else:
            opener = self.opener

        # Prepare request
        request = urllib.request.Request(url, data=data, method=method)
        if headers:
            for key, value in headers.items():
                request.add_header(key, value)

        # Retry logic with exponential backoff
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()

                with self._timeout_context(timeout):
                    response = opener.open(request, timeout=timeout)
                    content = response.read()

                    # Decode content if it's bytes
                    if isinstance(content, bytes):
                        try:
                            content = content.decode('utf-8')
                        except UnicodeDecodeError:
                            pass  # Keep as bytes

                    elapsed_time = time.time() - start_time

                    return NetworkResponse(
                        status_code=response.getcode(),
                        content=content,
                        headers=dict(response.headers),
                        url=response.geturl(),
                        elapsed_time=elapsed_time,
                        retries=attempt
                    )

            except (HTTPError, URLError, socket.timeout) as e:
                last_error = self._create_network_error(e, url, attempt)

                # Don't retry on client errors (4xx)
                if isinstance(e, HTTPError) and 400 <= e.code < 500:
                    break

                # Don't retry on the last attempt
                if attempt >= max_retries:
                    break

                # Calculate retry delay with exponential backoff and jitter
                delay = min(
                    self.config.timeouts.retry_delay * (self.config.timeouts.retry_backoff ** attempt),
                    self.config.timeouts.max_retry_delay
                )
                jitter = random.uniform(0, 0.1) * delay
                time.sleep(delay + jitter)

        # All retries exhausted, raise the last error
        raise RuntimeError(f"Network request failed after {max_retries + 1} attempts: {last_error.message}")

    def _create_network_error(self, error: Exception, url: str, retry_count: int) -> NetworkError:
        """Create structured network error from exception."""
        if isinstance(error, HTTPError):
            return NetworkError(
                error_type="HTTP_ERROR",
                message=f"HTTP {error.code}: {error.reason}",
                url=url,
                status_code=error.code,
                retry_count=retry_count
            )
        elif isinstance(error, URLError):
            return NetworkError(
                error_type="CONNECTION_ERROR",
                message=f"Connection failed: {error.reason}",
                url=url,
                retry_count=retry_count
            )
        elif isinstance(error, socket.timeout):
            return NetworkError(
                error_type="TIMEOUT_ERROR",
                message="Request timed out",
                url=url,
                retry_count=retry_count
            )
        else:
            return NetworkError(
                error_type="UNKNOWN_ERROR",
                message=str(error),
                url=url,
                retry_count=retry_count
            )

    @contextmanager
    def _timeout_context(self, timeout: int):
        """Context manager for timeout handling."""
        # This is a simple timeout context
        # In a real implementation, you might use signal.alarm or threading.Timer
        yield

    def health_check(self) -> NetworkDiagnostics:
        """
        Perform comprehensive network health check.

        Returns:
            Network diagnostics results
        """
        if not self._diagnostics or (time.time() - self._session_start) > 300:  # Refresh every 5 minutes
            self._diagnostics = validate_network_connectivity(self.config)
            self._session_start = time.time()

        return self._diagnostics

    def test_dagster_connectivity(self, host: str = "localhost", port: int = 3000) -> Tuple[bool, Optional[str]]:
        """
        Test connectivity to Dagster web server.

        Args:
            host: Dagster host
            port: Dagster port

        Returns:
            Tuple of (success, error_message)
        """
        url = f"http://{host}:{port}/health"

        try:
            response = self.get(url, timeout=self.config.timeouts.dagster_health_timeout)
            if response.status_code == 200:
                return True, None
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)

    def download_file(self, url: str, destination: Path, chunk_size: Optional[int] = None) -> bool:
        """
        Download file with progress tracking and resume support.

        Args:
            url: Download URL
            destination: Destination file path
            chunk_size: Download chunk size

        Returns:
            Success status
        """
        chunk_size = chunk_size or self.config.performance.chunk_size

        try:
            request = urllib.request.Request(url)

            # Check if file exists for resume
            resume_pos = 0
            if destination.exists():
                resume_pos = destination.stat().st_size
                request.add_header('Range', f'bytes={resume_pos}-')

            response = self.opener.open(request,
                                      timeout=self.config.timeouts.connection_timeout)

            total_size = int(response.headers.get('Content-Length', 0))
            if resume_pos > 0:
                total_size += resume_pos

            mode = 'ab' if resume_pos > 0 else 'wb'
            with open(destination, mode) as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)

            return True

        except Exception as e:
            print(f"Download failed: {e}")
            return False


def create_network_client(config_path: Optional[str] = None) -> CorporateNetworkClient:
    """
    Create corporate network client with configuration.

    Args:
        config_path: Optional path to network configuration

    Returns:
        Configured network client
    """
    config = load_network_config(config_path)
    return CorporateNetworkClient(config)


def test_subprocess_with_proxy(
    command: List[str],
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
    cwd: Optional[Union[str, Path]] = None,
) -> subprocess.CompletedProcess:
    """
    Execute subprocess command with proxy environment variables.

    Args:
        command: Command to execute
        env: Environment variables (proxy settings will be added)
        timeout: Command timeout

    Returns:
        Completed process result
    """
    config = load_network_config()

    # Prepare environment with proxy settings
    if env is None:
        import os
        env = os.environ.copy()

    if config.proxy.http_proxy:
        env['HTTP_PROXY'] = config.proxy.http_proxy
        env['http_proxy'] = config.proxy.http_proxy

    if config.proxy.https_proxy:
        env['HTTPS_PROXY'] = config.proxy.https_proxy
        env['https_proxy'] = config.proxy.https_proxy

    if config.proxy.no_proxy:
        env['NO_PROXY'] = ','.join(config.proxy.no_proxy)
        env['no_proxy'] = ','.join(config.proxy.no_proxy)

    # Add certificate bundle if specified
    if config.certificates.ca_bundle_path:
        env['REQUESTS_CA_BUNDLE'] = config.certificates.ca_bundle_path
        env['SSL_CERT_FILE'] = config.certificates.ca_bundle_path
        env['CURL_CA_BUNDLE'] = config.certificates.ca_bundle_path

    # Execute command with timeout
    timeout = timeout or config.timeouts.total_timeout

    try:
        return subprocess.run(
            command,
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except subprocess.TimeoutExpired as e:
        # Create a mock CompletedProcess for timeout
        return subprocess.CompletedProcess(
            args=command,
            returncode=124,  # Standard timeout exit code
            stdout=e.stdout or "",
            stderr=f"Command timed out after {timeout} seconds"
        )


def diagnose_network_issues() -> Dict[str, Any]:
    """
    Comprehensive network diagnostics for troubleshooting.

    Returns:
        Diagnostic information dictionary
    """
    config = load_network_config()
    client = CorporateNetworkClient(config)

    diagnostics = client.health_check()

    # Additional system-level diagnostics
    system_info = {
        "proxy_env_vars": {
            "HTTP_PROXY": os.environ.get('HTTP_PROXY'),
            "HTTPS_PROXY": os.environ.get('HTTPS_PROXY'),
            "NO_PROXY": os.environ.get('NO_PROXY'),
        },
        "dns_resolution": {},
        "port_connectivity": {},
    }

    # Test DNS resolution
    for endpoint in config.test_endpoints:
        try:
            parsed = urllib.parse.urlparse(endpoint)
            hostname = parsed.hostname
            if hostname:
                socket.gethostbyname(hostname)
                system_info["dns_resolution"][hostname] = True
        except socket.gaierror:
            system_info["dns_resolution"][hostname] = False

    # Test port connectivity
    test_ports = [(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
                  for parsed in [urllib.parse.urlparse(url) for url in config.test_endpoints]
                  if parsed.hostname]

    for host, port in test_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            system_info["port_connectivity"][f"{host}:{port}"] = result == 0
        except Exception:
            system_info["port_connectivity"][f"{host}:{port}"] = False

    return {
        "network_diagnostics": diagnostics,
        "system_info": system_info,
        "configuration": config.dict(),
        "recommendations": _generate_recommendations(diagnostics, system_info)
    }


def _generate_recommendations(diagnostics: NetworkDiagnostics,
                            system_info: Dict[str, Any]) -> List[str]:
    """Generate troubleshooting recommendations based on diagnostics."""
    recommendations = []

    if not any(diagnostics.connectivity_tests.values()):
        recommendations.append("No network connectivity detected. Check network connection and proxy settings.")

        # Check DNS issues
        if not any(system_info["dns_resolution"].values()):
            recommendations.append("DNS resolution failed. Check DNS server configuration.")

        # Check port connectivity
        if not any(system_info["port_connectivity"].values()):
            recommendations.append("Port connectivity failed. Check firewall and proxy configuration.")

    if diagnostics.proxy_detected and not diagnostics.proxy_working:
        recommendations.append("Proxy configuration detected but not working. Verify proxy server settings and authentication.")

    if diagnostics.errors:
        recommendations.append("Review error details for specific connectivity issues.")

    return recommendations
