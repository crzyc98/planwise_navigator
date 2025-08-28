#!/usr/bin/env python3
"""
Corporate Network Diagnostics Utility for PlanWise Navigator.

This utility provides comprehensive network diagnostics and troubleshooting
tools for corporate environments, including proxy detection, certificate
validation, and connectivity testing.

Epic E063 - Story S063-07: Corporate Network and Proxy Support

Usage:
    python scripts/network_diagnostics.py --basic           # Basic connectivity check
    python scripts/network_diagnostics.py --full            # Full diagnostic suite
    python scripts/network_diagnostics.py --proxy-test      # Proxy configuration test
    python scripts/network_diagnostics.py --cert-check      # Certificate validation
    python scripts/network_diagnostics.py --fix-suggestions # Show configuration recommendations
"""

import argparse
import json
import os
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "config"))
sys.path.insert(0, str(project_root / "navigator_orchestrator"))

try:
    from config.network_config import CorporateNetworkConfig, load_network_config, detect_system_proxy
    from navigator_orchestrator.network_utils import (
        CorporateNetworkClient,
        create_network_client,
        diagnose_network_issues,
        test_subprocess_with_proxy
    )
    CORPORATE_NETWORK_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Corporate network modules not available: {e}")
    CORPORATE_NETWORK_AVAILABLE = False


class NetworkDiagnostics:
    """Comprehensive network diagnostics for corporate environments."""

    def __init__(self):
        """Initialize network diagnostics."""
        self.results = {
            "timestamp": time.time(),
            "system_info": {},
            "proxy_info": {},
            "dns_info": {},
            "connectivity": {},
            "certificates": {},
            "performance": {},
            "recommendations": []
        }

        if CORPORATE_NETWORK_AVAILABLE:
            try:
                self.config = load_network_config()
                self.client = create_network_client()
            except Exception as e:
                print(f"⚠️  Failed to initialize corporate network client: {e}")
                self.config = None
                self.client = None
        else:
            self.config = None
            self.client = None

    def run_basic_diagnostics(self) -> Dict[str, Any]:
        """Run basic network connectivity diagnostics."""
        print("🔍 Running basic network diagnostics...")

        # System network information
        self._collect_system_info()

        # Proxy detection and testing
        self._test_proxy_configuration()

        # Basic connectivity tests
        self._test_basic_connectivity()

        return self.results

    def run_full_diagnostics(self) -> Dict[str, Any]:
        """Run comprehensive network diagnostics."""
        print("🔍 Running comprehensive network diagnostics...")

        # Run basic diagnostics first
        self.run_basic_diagnostics()

        # Advanced DNS testing
        self._test_dns_resolution()

        # Certificate validation
        self._test_certificate_validation()

        # Performance testing
        self._test_network_performance()

        # Corporate environment detection
        self._detect_corporate_environment()

        # Generate recommendations
        self._generate_recommendations()

        return self.results

    def _collect_system_info(self):
        """Collect system network information."""
        print("  📊 Collecting system information...")

        self.results["system_info"] = {
            "hostname": socket.gethostname(),
            "fqdn": socket.getfqdn(),
            "platform": sys.platform,
            "python_version": sys.version,
            "environment_variables": {
                "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
                "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
                "NO_PROXY": os.environ.get("NO_PROXY"),
                "REQUESTS_CA_BUNDLE": os.environ.get("REQUESTS_CA_BUNDLE"),
                "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE"),
                "CURL_CA_BUNDLE": os.environ.get("CURL_CA_BUNDLE"),
            }
        }

        # Check for corporate network indicators
        hostname = self.results["system_info"]["hostname"]
        fqdn = self.results["system_info"]["fqdn"]

        corporate_indicators = []
        if any(domain in fqdn for domain in [".corp", ".company", ".local"]):
            corporate_indicators.append("Corporate domain detected in FQDN")

        if any(proxy in str(os.environ.get("HTTP_PROXY", "")) for proxy in ["proxy", "corporate"]):
            corporate_indicators.append("Corporate proxy detected in environment")

        self.results["system_info"]["corporate_indicators"] = corporate_indicators

    def _test_proxy_configuration(self):
        """Test proxy configuration and connectivity."""
        print("  🔒 Testing proxy configuration...")

        proxy_info = {
            "detected": False,
            "configured": False,
            "working": False,
            "authentication": False,
            "bypass_rules": [],
            "errors": []
        }

        # Check environment variables
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")

        if http_proxy or https_proxy:
            proxy_info["detected"] = True
            proxy_info["configured"] = True

            if no_proxy:
                proxy_info["bypass_rules"] = [rule.strip() for rule in no_proxy.split(",")]

        # Test proxy with corporate network client if available
        if CORPORATE_NETWORK_AVAILABLE and self.client:
            try:
                detected_proxy = detect_system_proxy()
                if detected_proxy:
                    proxy_info["detected"] = True
                    proxy_info["configured"] = True

                    # Test proxy functionality
                    test_url = "https://httpbin.org/get"
                    response = self.client.get(test_url)
                    proxy_info["working"] = True

            except Exception as e:
                proxy_info["errors"].append(f"Proxy test failed: {str(e)}")

        self.results["proxy_info"] = proxy_info

    def _test_basic_connectivity(self):
        """Test basic network connectivity."""
        print("  🌐 Testing basic connectivity...")

        test_endpoints = [
            ("Google DNS", "8.8.8.8", 53),
            ("Google HTTPS", "www.google.com", 443),
            ("GitHub", "github.com", 443),
            ("HTTPBin", "httpbin.org", 443)
        ]

        connectivity_results = {}

        for name, host, port in test_endpoints:
            try:
                start_time = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                result = sock.connect_ex((host, port))
                sock.close()
                elapsed = time.time() - start_time

                connectivity_results[name] = {
                    "success": result == 0,
                    "response_time": elapsed,
                    "endpoint": f"{host}:{port}",
                    "error": None if result == 0 else f"Connection failed (code: {result})"
                }

            except Exception as e:
                connectivity_results[name] = {
                    "success": False,
                    "response_time": None,
                    "endpoint": f"{host}:{port}",
                    "error": str(e)
                }

        self.results["connectivity"] = connectivity_results

    def _test_dns_resolution(self):
        """Test DNS resolution for key domains."""
        print("  🔍 Testing DNS resolution...")

        test_domains = [
            "www.google.com",
            "github.com",
            "httpbin.org",
            "pypi.org",
            "duckdb.org"
        ]

        dns_results = {}

        for domain in test_domains:
            try:
                start_time = time.time()
                ip_address = socket.gethostbyname(domain)
                elapsed = time.time() - start_time

                dns_results[domain] = {
                    "success": True,
                    "ip_address": ip_address,
                    "response_time": elapsed,
                    "error": None
                }

            except socket.gaierror as e:
                dns_results[domain] = {
                    "success": False,
                    "ip_address": None,
                    "response_time": None,
                    "error": str(e)
                }

        self.results["dns_info"] = dns_results

    def _test_certificate_validation(self):
        """Test SSL certificate validation."""
        print("  🔐 Testing certificate validation...")

        cert_results = {}
        test_sites = [
            "https://www.google.com",
            "https://github.com",
            "https://httpbin.org"
        ]

        for site in test_sites:
            parsed = urllib.parse.urlparse(site)
            hostname = parsed.hostname
            port = parsed.port or 443

            try:
                # Test certificate chain
                context = ssl.create_default_context()
                with socket.create_connection((hostname, port), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert = ssock.getpeercert()

                        cert_results[site] = {
                            "valid": True,
                            "subject": dict(x[0] for x in cert.get('subject', [])),
                            "issuer": dict(x[0] for x in cert.get('issuer', [])),
                            "version": cert.get('version'),
                            "serial_number": cert.get('serialNumber'),
                            "not_before": cert.get('notBefore'),
                            "not_after": cert.get('notAfter'),
                            "error": None
                        }

            except Exception as e:
                cert_results[site] = {
                    "valid": False,
                    "error": str(e)
                }

        self.results["certificates"] = cert_results

    def _test_network_performance(self):
        """Test network performance characteristics."""
        print("  ⚡ Testing network performance...")

        performance_results = {
            "latency_tests": {},
            "bandwidth_estimate": None,
            "packet_loss": None
        }

        # Latency tests to various endpoints
        latency_endpoints = [
            ("Google DNS", "8.8.8.8"),
            ("Cloudflare DNS", "1.1.1.1"),
            ("GitHub", "github.com")
        ]

        for name, host in latency_endpoints:
            latencies = []
            for _ in range(5):  # 5 ping attempts
                try:
                    start_time = time.time()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((host, 80))
                    sock.close()

                    if result == 0:
                        latency = (time.time() - start_time) * 1000  # Convert to ms
                        latencies.append(latency)

                except Exception:
                    pass

                time.sleep(0.1)  # Small delay between attempts

            if latencies:
                performance_results["latency_tests"][name] = {
                    "min": min(latencies),
                    "max": max(latencies),
                    "avg": sum(latencies) / len(latencies),
                    "samples": len(latencies)
                }

        self.results["performance"] = performance_results

    def _detect_corporate_environment(self):
        """Detect indicators of corporate network environment."""
        print("  🏢 Detecting corporate environment...")

        indicators = []

        # Check hostname patterns
        hostname = socket.gethostname().lower()
        fqdn = socket.getfqdn().lower()

        corporate_domains = ['.corp', '.company', '.local', '.internal', '.intranet']
        if any(domain in fqdn for domain in corporate_domains):
            indicators.append(f"Corporate domain detected: {fqdn}")

        # Check for proxy settings
        if self.results["proxy_info"]["detected"]:
            indicators.append("Corporate proxy configuration detected")

        # Check for corporate certificate paths
        cert_paths = [
            "/etc/ssl/certs/ca-certificates.crt",
            "/etc/pki/tls/certs/ca-bundle.crt",
            "/usr/local/share/certs/",
            "C:\\Windows\\System32\\config\\systemprofile\\AppData\\LocalLow\\Microsoft\\CryptnetUrlCache\\"
        ]

        for path in cert_paths:
            if Path(path).exists():
                indicators.append(f"Corporate certificate path found: {path}")
                break

        # Check environment variables for corporate indicators
        corporate_env_vars = ["CORPORATE_PROXY", "COMPANY_CERT", "DOMAIN_CONTROLLER"]
        for var in corporate_env_vars:
            if os.environ.get(var):
                indicators.append(f"Corporate environment variable detected: {var}")

        self.results["corporate_environment"] = {
            "detected": len(indicators) > 0,
            "indicators": indicators,
            "confidence": min(len(indicators) * 0.3, 1.0)  # Max confidence of 1.0
        }

    def _generate_recommendations(self):
        """Generate network configuration recommendations."""
        recommendations = []

        # Connectivity recommendations
        failed_connections = [name for name, result in self.results["connectivity"].items()
                            if not result["success"]]
        if failed_connections:
            recommendations.append(
                f"Network connectivity issues detected for: {', '.join(failed_connections)}. "
                "Check firewall settings and network configuration."
            )

        # Proxy recommendations
        if self.results["proxy_info"]["detected"] and not self.results["proxy_info"]["working"]:
            recommendations.append(
                "Proxy detected but not working properly. Verify proxy server settings, "
                "authentication credentials, and bypass rules."
            )

        # DNS recommendations
        failed_dns = [domain for domain, result in self.results["dns_info"].items()
                     if not result["success"]]
        if failed_dns:
            recommendations.append(
                f"DNS resolution failed for: {', '.join(failed_dns)}. "
                "Check DNS server configuration and network connectivity."
            )

        # Certificate recommendations
        failed_certs = [site for site, result in self.results["certificates"].items()
                       if not result["valid"]]
        if failed_certs:
            recommendations.append(
                f"SSL certificate validation failed for: {', '.join(failed_certs)}. "
                "Check corporate certificate bundle configuration."
            )

        # Performance recommendations
        if self.results["performance"]["latency_tests"]:
            avg_latencies = [result["avg"] for result in self.results["performance"]["latency_tests"].values()]
            if avg_latencies and max(avg_latencies) > 1000:  # > 1 second
                recommendations.append(
                    "High network latency detected. Consider optimizing network configuration "
                    "or using performance optimization settings."
                )

        # Corporate environment recommendations
        if self.results["corporate_environment"]["detected"]:
            recommendations.append(
                "Corporate network environment detected. Ensure corporate network configuration "
                "is properly enabled in PlanWise Navigator settings."
            )

        if not recommendations:
            recommendations.append("Network configuration appears to be working correctly.")

        self.results["recommendations"] = recommendations

    def print_results(self, detailed: bool = False):
        """Print diagnostic results in a human-readable format."""
        print("\n" + "="*60)
        print("📡 PLANWISE NAVIGATOR NETWORK DIAGNOSTICS REPORT")
        print("="*60)

        # System Information
        print(f"\n🖥️  SYSTEM INFORMATION")
        print(f"   Hostname: {self.results['system_info']['hostname']}")
        print(f"   FQDN: {self.results['system_info']['fqdn']}")
        print(f"   Platform: {self.results['system_info']['platform']}")

        # Corporate Environment
        if "corporate_environment" in self.results:
            corp_env = self.results["corporate_environment"]
            status = "Detected" if corp_env["detected"] else "Not detected"
            print(f"\n🏢 CORPORATE ENVIRONMENT: {status}")
            if corp_env["indicators"]:
                for indicator in corp_env["indicators"]:
                    print(f"   • {indicator}")

        # Proxy Information
        proxy = self.results["proxy_info"]
        print(f"\n🔒 PROXY CONFIGURATION")
        print(f"   Detected: {'Yes' if proxy['detected'] else 'No'}")
        print(f"   Working: {'Yes' if proxy['working'] else 'No'}")
        if proxy["errors"]:
            print("   Errors:")
            for error in proxy["errors"]:
                print(f"     • {error}")

        # Connectivity Results
        print(f"\n🌐 CONNECTIVITY TESTS")
        for name, result in self.results["connectivity"].items():
            status = "✅" if result["success"] else "❌"
            time_info = f" ({result['response_time']:.3f}s)" if result["response_time"] else ""
            print(f"   {status} {name}: {result['endpoint']}{time_info}")
            if result["error"]:
                print(f"       Error: {result['error']}")

        # DNS Results
        if "dns_info" in self.results and detailed:
            print(f"\n🔍 DNS RESOLUTION TESTS")
            for domain, result in self.results["dns_info"].items():
                status = "✅" if result["success"] else "❌"
                ip_info = f" → {result['ip_address']}" if result["ip_address"] else ""
                time_info = f" ({result['response_time']:.3f}s)" if result["response_time"] else ""
                print(f"   {status} {domain}{ip_info}{time_info}")
                if result["error"]:
                    print(f"       Error: {result['error']}")

        # Certificate Results
        if "certificates" in self.results and detailed:
            print(f"\n🔐 CERTIFICATE VALIDATION")
            for site, result in self.results["certificates"].items():
                status = "✅" if result["valid"] else "❌"
                print(f"   {status} {site}")
                if result["error"]:
                    print(f"       Error: {result['error']}")

        # Performance Results
        if "performance" in self.results and detailed:
            print(f"\n⚡ PERFORMANCE METRICS")
            for name, result in self.results["performance"]["latency_tests"].items():
                print(f"   {name}: {result['avg']:.1f}ms avg "
                      f"(min: {result['min']:.1f}ms, max: {result['max']:.1f}ms)")

        # Recommendations
        print(f"\n💡 RECOMMENDATIONS")
        for i, rec in enumerate(self.results["recommendations"], 1):
            print(f"   {i}. {rec}")

        print("\n" + "="*60)

    def export_results(self, filename: str):
        """Export results to JSON file."""
        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"📄 Results exported to: {output_path}")


def main():
    """Main entry point for network diagnostics utility."""
    parser = argparse.ArgumentParser(
        description="PlanWise Navigator Corporate Network Diagnostics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/network_diagnostics.py --basic
    python scripts/network_diagnostics.py --full --export report.json
    python scripts/network_diagnostics.py --proxy-test
    python scripts/network_diagnostics.py --fix-suggestions
        """
    )

    parser.add_argument("--basic", action="store_true",
                       help="Run basic connectivity diagnostics")
    parser.add_argument("--full", action="store_true",
                       help="Run comprehensive diagnostic suite")
    parser.add_argument("--proxy-test", action="store_true",
                       help="Test proxy configuration only")
    parser.add_argument("--cert-check", action="store_true",
                       help="Test certificate validation only")
    parser.add_argument("--fix-suggestions", action="store_true",
                       help="Generate configuration recommendations")
    parser.add_argument("--export", metavar="FILE",
                       help="Export results to JSON file")
    parser.add_argument("--detailed", action="store_true",
                       help="Show detailed output")

    args = parser.parse_args()

    # Default to basic if no specific test specified
    if not any([args.basic, args.full, args.proxy_test, args.cert_check, args.fix_suggestions]):
        args.basic = True

    diagnostics = NetworkDiagnostics()

    try:
        if args.full:
            results = diagnostics.run_full_diagnostics()
        elif args.proxy_test:
            print("🔍 Testing proxy configuration...")
            results = {"proxy_info": {}}
            diagnostics._test_proxy_configuration()
        elif args.cert_check:
            print("🔍 Testing certificate validation...")
            results = {"certificates": {}}
            diagnostics._test_certificate_validation()
        elif args.fix_suggestions:
            results = diagnostics.run_full_diagnostics()
            print("\n💡 CONFIGURATION RECOMMENDATIONS:")
            for i, rec in enumerate(results["recommendations"], 1):
                print(f"   {i}. {rec}")
            return
        else:  # basic
            results = diagnostics.run_basic_diagnostics()

        # Print results
        diagnostics.print_results(detailed=args.detailed or args.full)

        # Export results if requested
        if args.export:
            diagnostics.export_results(args.export)

    except KeyboardInterrupt:
        print("\n⚠️  Diagnostics interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Diagnostics failed: {e}")
        if args.detailed:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
