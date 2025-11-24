#!/usr/bin/env python3
"""
Network-enhanced requests module for Streamlit dashboard.

This module provides corporate network-aware HTTP functionality for the
Streamlit dashboard, with automatic proxy detection and corporate certificate support.

Epic E063 - Story S063-07: Corporate Network and Proxy Support
"""

import sys
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import streamlit as st

# Add the parent directories to path for imports
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / "config"))
sys.path.append(str(Path(__file__).parent.parent / "planalign_orchestrator"))

try:
    from planalign_orchestrator.network_utils import CorporateNetworkClient, NetworkResponse, create_network_client
    from config.network_config import CorporateNetworkConfig, load_network_config
    CORPORATE_NETWORK_AVAILABLE = True
except ImportError as e:
    st.warning(f"Corporate network support not available: {e}")
    CORPORATE_NETWORK_AVAILABLE = False


class StreamlitNetworkClient:
    """
    Streamlit-aware network client with corporate proxy support.

    This class provides a drop-in replacement for basic requests functionality
    while adding corporate network support, error handling, and Streamlit integration.
    """

    def __init__(self):
        """Initialize the Streamlit network client."""
        self._client = None
        self._config = None
        self._diagnostics_cache = None

        if CORPORATE_NETWORK_AVAILABLE:
            try:
                self._config = load_network_config()
                self._client = create_network_client()

                # Perform initial connectivity check if enabled
                if self._config.connectivity_check:
                    self._run_connectivity_check()

            except Exception as e:
                st.error(f"Failed to initialize corporate network client: {e}")
                self._fallback_to_requests()
        else:
            self._fallback_to_requests()

    def _fallback_to_requests(self):
        """Fallback to standard requests library."""
        try:
            import requests
            self._requests = requests
            st.info("🔄 Using standard HTTP client (corporate network support disabled)")
        except ImportError:
            st.error("❌ No HTTP client available. Install requests library.")
            self._requests = None

    def _run_connectivity_check(self):
        """Run initial connectivity check with caching."""
        if self._diagnostics_cache is None and self._client:
            try:
                with st.spinner("🔍 Checking network connectivity..."):
                    self._diagnostics_cache = self._client.health_check()

                # Show connectivity status
                if any(self._diagnostics_cache.connectivity_tests.values()):
                    st.success("🌐 Network connectivity verified")

                    if self._diagnostics_cache.proxy_detected:
                        if self._diagnostics_cache.proxy_working:
                            st.info("🔒 Corporate proxy detected and working")
                        else:
                            st.warning("🔒 Corporate proxy detected but may have issues")
                else:
                    st.error("❌ Network connectivity issues detected")
                    for error in self._diagnostics_cache.errors[:3]:  # Show first 3 errors
                        st.error(f"  • {error}")

            except Exception as e:
                st.warning(f"⚠️ Network diagnostics failed: {e}")

    def get(self, url: str, timeout: int = 30, **kwargs) -> Tuple[bool, Optional[Union[NetworkResponse, Dict]]]:
        """
        Perform HTTP GET request with corporate network support.

        Args:
            url: Request URL
            timeout: Request timeout
            **kwargs: Additional request parameters

        Returns:
            Tuple of (success, response_data)
        """
        if self._client:
            try:
                response = self._client.get(url, timeout=timeout, **kwargs)
                return True, {
                    'status_code': response.status_code,
                    'content': response.content,
                    'headers': response.headers,
                    'url': response.url,
                    'elapsed_time': response.elapsed_time
                }
            except Exception as e:
                st.error(f"🌐 Corporate network request failed: {e}")
                return False, None

        elif self._requests:
            try:
                response = self._requests.get(url, timeout=timeout, **kwargs)
                return True, {
                    'status_code': response.status_code,
                    'content': response.text,
                    'headers': dict(response.headers),
                    'url': response.url,
                    'elapsed_time': response.elapsed.total_seconds() if hasattr(response, 'elapsed') else 0
                }
            except Exception as e:
                st.error(f"🌐 Standard HTTP request failed: {e}")
                return False, None

        else:
            st.error("❌ No HTTP client available")
            return False, None

    def test_dagster_health(self, host: str = "localhost", port: int = 3000) -> Tuple[bool, str]:
        """
        Test Dagster health endpoint with corporate network support.

        Args:
            host: Dagster host
            port: Dagster port

        Returns:
            Tuple of (success, message)
        """
        if self._client:
            try:
                success, error = self._client.test_dagster_connectivity(host, port)
                if success:
                    return True, "🟢 Connected to Dagster UI"
                else:
                    return False, f"🟡 Dagster connection failed: {error}"
            except Exception as e:
                return False, f"🔴 Dagster connectivity test error: {e}"

        else:
            # Fallback to basic connection test
            url = f"http://{host}:{port}/health"
            success, response = self.get(url, timeout=5)

            if success and response and response['status_code'] == 200:
                return True, "🟢 Connected to Dagster UI"
            elif success:
                return False, f"🟡 Dagster returned HTTP {response['status_code']}"
            else:
                return False, "🔴 Cannot connect to Dagster UI"

    def show_network_diagnostics(self):
        """Display network diagnostics in Streamlit sidebar."""
        if not CORPORATE_NETWORK_AVAILABLE:
            st.sidebar.info("📡 Corporate network support: Disabled")
            return

        with st.sidebar.expander("📡 Network Diagnostics", expanded=False):
            if self._diagnostics_cache:
                diag = self._diagnostics_cache

                # Connection status
                st.write("**Connectivity Tests:**")
                for endpoint, success in diag.connectivity_tests.items():
                    status = "✅" if success else "❌"
                    time_info = ""
                    if endpoint in diag.response_times:
                        time_info = f" ({diag.response_times[endpoint]:.2f}s)"
                    st.write(f"{status} {endpoint.split('/')[-2]}{time_info}")

                # Proxy status
                st.write("**Proxy Status:**")
                if diag.proxy_detected:
                    proxy_status = "✅ Working" if diag.proxy_working else "⚠️ Issues detected"
                    st.write(f"🔒 Proxy: {proxy_status}")
                else:
                    st.write("🔒 Proxy: Not detected")

                # SSL verification
                ssl_status = "✅ Enabled" if diag.ssl_verification else "⚠️ Disabled"
                st.write(f"🔐 SSL Verification: {ssl_status}")

                # Show recommendations if any
                if diag.recommendations:
                    st.write("**Recommendations:**")
                    for rec in diag.recommendations[:2]:  # Show first 2
                        st.info(rec)

            else:
                st.write("Network diagnostics not available")

            # Manual refresh button
            if st.button("🔄 Refresh Diagnostics", key="refresh_network_diag"):
                self._diagnostics_cache = None
                if self._client:
                    self._run_connectivity_check()
                st.experimental_rerun()

    def show_configuration_summary(self):
        """Show network configuration summary in sidebar."""
        if not CORPORATE_NETWORK_AVAILABLE or not self._config:
            return

        with st.sidebar.expander("⚙️ Network Configuration", expanded=False):
            st.write(f"**Status:** {'Enabled' if self._config.enabled else 'Disabled'}")
            st.write(f"**Auto-detect Proxy:** {'Yes' if self._config.auto_detect_proxy else 'No'}")

            if self._config.proxy.http_proxy or self._config.proxy.https_proxy:
                st.write("**Proxy Configuration:**")
                if self._config.proxy.http_proxy:
                    # Mask authentication info for display
                    proxy_display = self._config.proxy.http_proxy
                    if '@' in proxy_display:
                        proxy_display = proxy_display.split('@')[1]  # Remove auth info
                    st.write(f"• HTTP: {proxy_display}")
                if self._config.proxy.https_proxy:
                    proxy_display = self._config.proxy.https_proxy
                    if '@' in proxy_display:
                        proxy_display = proxy_display.split('@')[1]
                    st.write(f"• HTTPS: {proxy_display}")

            st.write(f"**SSL Verification:** {'Enabled' if self._config.certificates.verify_ssl else 'Disabled'}")
            st.write(f"**Connection Timeout:** {self._config.timeouts.connection_timeout}s")
            st.write(f"**Max Retries:** {self._config.timeouts.max_retries}")


# Global instance for the Streamlit app
network_client = StreamlitNetworkClient()


def get_network_client() -> StreamlitNetworkClient:
    """Get the global network client instance."""
    return network_client


def check_dagster_connection(host: str = "localhost", port: int = 3000) -> Tuple[bool, str]:
    """
    Check Dagster connection with corporate network support.

    This function is a drop-in replacement for the original requests-based
    Dagster health check in the Streamlit dashboard.

    Args:
        host: Dagster host
        port: Dagster port

    Returns:
        Tuple of (success, message)
    """
    return network_client.test_dagster_health(host, port)


def show_network_status_widget():
    """Show network status widget in the main Streamlit interface."""
    with st.container():
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            success, message = check_dagster_connection()
            if success:
                st.success(message)
            else:
                st.warning(message)

        with col2:
            if CORPORATE_NETWORK_AVAILABLE:
                st.info("🏢 Corporate network: Enabled")
            else:
                st.info("🌐 Standard network: Active")

        with col3:
            if st.button("🔄 Test Connection", key="test_connection"):
                st.experimental_rerun()


def display_network_diagnostics_sidebar():
    """Display network diagnostics in the sidebar."""
    network_client.show_network_diagnostics()
    network_client.show_configuration_summary()
