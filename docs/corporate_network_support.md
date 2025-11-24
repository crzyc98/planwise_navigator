# Corporate Network and Proxy Support for Fidelity PlanAlign Engine

## Overview

Fidelity PlanAlign Engine includes comprehensive corporate network support designed for enterprise environments with proxies, corporate certificates, and restricted network access. This document provides complete configuration and troubleshooting guidance for IT administrators and developers.

**Epic E063 - Story S063-07: Corporate Network and Proxy Support**

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration](#configuration)
3. [Corporate Environment Detection](#corporate-environment-detection)
4. [Proxy Configuration](#proxy-configuration)
5. [Certificate Management](#certificate-management)
6. [Network Diagnostics](#network-diagnostics)
7. [Troubleshooting](#troubleshooting)
8. [Integration Guide](#integration-guide)
9. [Security Considerations](#security-considerations)

## Quick Start

### Automatic Configuration (Recommended)

Fidelity PlanAlign Engine automatically detects corporate network settings from environment variables:

```bash
# Set proxy environment variables (if not already configured by IT)
export HTTP_PROXY="http://proxy.company.com:8080"
export HTTPS_PROXY="http://proxy.company.com:8080"
export NO_PROXY="localhost,127.0.0.1,*.local"

# Set certificate bundle (if custom CA required)
export REQUESTS_CA_BUNDLE="/path/to/corporate-ca-bundle.crt"
export SSL_CERT_FILE="/path/to/corporate-ca-bundle.crt"

# Run network diagnostics to verify configuration
python scripts/network_diagnostics.py --basic
```

### Manual Configuration

Edit `config/simulation_config.yaml` to customize corporate network settings:

```yaml
corporate_network:
  enabled: true
  auto_detect_proxy: true

  proxy:
    http_proxy: "http://proxy.company.com:8080"
    https_proxy: "http://proxy.company.com:8080"
    no_proxy: ["localhost", "127.0.0.1", "*.company.com"]
    username: null  # Use system authentication
    password: null

  certificates:
    ca_bundle_path: "/etc/ssl/certs/corporate-ca-bundle.crt"
    verify_ssl: true

  timeouts:
    connection_timeout: 30
    dbt_command_timeout: 1800
    max_retries: 3
```

## Configuration

### Environment Variables

The following environment variables are automatically detected and used:

| Variable | Description | Example |
|----------|-------------|---------|
| `HTTP_PROXY` | HTTP proxy server URL | `http://proxy.company.com:8080` |
| `HTTPS_PROXY` | HTTPS proxy server URL | `http://proxy.company.com:8080` |
| `NO_PROXY` | Bypass proxy for these hosts | `localhost,127.0.0.1,*.local` |
| `REQUESTS_CA_BUNDLE` | Path to CA certificate bundle | `/etc/ssl/certs/ca-bundle.crt` |
| `SSL_CERT_FILE` | SSL certificate file | `/etc/ssl/certs/ca-certificates.crt` |
| `CURL_CA_BUNDLE` | cURL CA bundle path | `/etc/ssl/certs/ca-bundle.crt` |

### Configuration File

The corporate network configuration is stored in `config/simulation_config.yaml`:

```yaml
corporate_network:
  # Master enable/disable switch
  enabled: true

  # Automatically detect proxy from environment variables
  auto_detect_proxy: true

  # Proxy configuration
  proxy:
    http_proxy: null           # Auto-detected if null
    https_proxy: null          # Auto-detected if null
    ftp_proxy: null            # Optional FTP proxy
    no_proxy: ["localhost", "127.0.0.1", "*.local"]

    # Authentication settings
    username: null             # Proxy username (null = system auth)
    password: null             # Proxy password (null = system auth)
    use_system_auth: true      # Use NTLM/Kerberos authentication

    # Connection settings
    proxy_timeout: 30          # Proxy connection timeout (seconds)
    proxy_retries: 3           # Number of retry attempts

  # Corporate certificate configuration
  certificates:
    ca_bundle_path: null       # Path to corporate CA bundle
    verify_ssl: true           # Enable SSL verification
    allow_self_signed: false   # Allow self-signed certs (dev only)
    hostname_verification: true # Verify certificate hostnames
    check_certificate_chain: true
    max_chain_depth: 10

  # Network timeout configuration
  timeouts:
    connection_timeout: 30     # TCP connection timeout
    read_timeout: 60           # Socket read timeout
    total_timeout: 300         # Total operation timeout
    dagster_health_timeout: 5  # Dagster connectivity check
    dbt_command_timeout: 1800  # dbt command timeout (30 minutes)
    database_timeout: 60       # Database connection timeout
    max_retries: 3             # Maximum retry attempts
    retry_delay: 1.0           # Base retry delay (seconds)
    retry_backoff: 2.0         # Exponential backoff multiplier
    max_retry_delay: 30.0      # Maximum retry delay

  # Performance optimization
  performance:
    enable_connection_pooling: true
    max_pool_connections: 10
    enable_gzip: true
    chunk_size: 8192
    keep_alive: true
    keep_alive_timeout: 30

  # Corporate environment detection
  corporate_domains: ["company.com", "corp.local"]
  vpn_detection: true

  # Connectivity validation
  connectivity_check: true
  test_endpoints:
    - "https://httpbin.org/get"
    - "https://www.google.com"
    - "https://github.com"
```

## Corporate Environment Detection

Fidelity PlanAlign Engine automatically detects corporate network environments based on:

1. **Hostname patterns**: `.corp`, `.company`, `.local`, `.internal`
2. **Proxy configuration**: Environment variables or manual configuration
3. **Certificate paths**: Standard corporate certificate locations
4. **DNS settings**: Corporate DNS servers and domains
5. **Network routing**: VPN connections and internal IP ranges

### Detection Results

Run the network diagnostics to see detection results:

```bash
python scripts/network_diagnostics.py --full

# Output includes:
# 🏢 CORPORATE ENVIRONMENT: Detected
#    • Corporate domain detected in FQDN
#    • Corporate proxy detected in environment
#    • Corporate certificate path found
```

## Proxy Configuration

### Supported Proxy Types

- **HTTP/HTTPS Proxies**: Standard corporate web proxies
- **SOCKS Proxies**: SOCKS4/SOCKS5 proxy support (via environment)
- **Authenticated Proxies**: Username/password and system authentication
- **PAC Files**: Proxy Auto-Configuration (via system settings)

### Authentication Methods

1. **System Authentication** (Recommended)
   ```yaml
   proxy:
     use_system_auth: true
     username: null
     password: null
   ```

2. **Username/Password Authentication**
   ```yaml
   proxy:
     use_system_auth: false
     username: "domain\\username"
     password: "password"
   ```

3. **Environment Variables**
   ```bash
   export HTTP_PROXY="http://username:password@proxy.company.com:8080"
   export HTTPS_PROXY="http://username:password@proxy.company.com:8080"
   ```

### Proxy Bypass Rules

Configure hosts to bypass the proxy using `no_proxy` settings:

```yaml
proxy:
  no_proxy:
    - "localhost"
    - "127.0.0.1"
    - "*.local"
    - "*.company.com"
    - "10.0.0.0/8"     # Internal IP ranges
    - "192.168.0.0/16" # Private networks
```

## Certificate Management

### Corporate CA Bundle

Configure the path to your corporate certificate authority bundle:

```yaml
certificates:
  ca_bundle_path: "/etc/ssl/certs/corporate-ca-bundle.crt"
```

Common corporate CA bundle locations:

| OS | Path |
|----|------|
| **Ubuntu/Debian** | `/etc/ssl/certs/ca-certificates.crt` |
| **CentOS/RHEL** | `/etc/pki/tls/certs/ca-bundle.crt` |
| **Windows** | `C:\Windows\System32\config\systemprofile\AppData\LocalLow\Microsoft\CryptnetUrlCache\` |
| **macOS** | `/usr/local/share/certs/` or `/etc/ssl/cert.pem` |

### Certificate Validation Levels

1. **Strict Validation** (Production)
   ```yaml
   certificates:
     verify_ssl: true
     hostname_verification: true
     allow_self_signed: false
   ```

2. **Development/Testing**
   ```yaml
   certificates:
     verify_ssl: true
     hostname_verification: false
     allow_self_signed: true  # Only for development!
   ```

3. **Disabled** (Not recommended)
   ```yaml
   certificates:
     verify_ssl: false
   ```

## Network Diagnostics

### Running Diagnostics

Fidelity PlanAlign Engine includes a comprehensive network diagnostics tool:

```bash
# Basic connectivity check
python scripts/network_diagnostics.py --basic

# Full diagnostic suite
python scripts/network_diagnostics.py --full

# Proxy-specific testing
python scripts/network_diagnostics.py --proxy-test

# Certificate validation testing
python scripts/network_diagnostics.py --cert-check

# Generate configuration recommendations
python scripts/network_diagnostics.py --fix-suggestions

# Export results to file
python scripts/network_diagnostics.py --full --export network_report.json
```

### Diagnostic Output

```
📡 PLANWISE NAVIGATOR NETWORK DIAGNOSTICS REPORT
============================================================

🖥️  SYSTEM INFORMATION
   Hostname: workstation-001
   FQDN: workstation-001.company.com
   Platform: linux

🏢 CORPORATE ENVIRONMENT: Detected
   • Corporate domain detected in FQDN
   • Corporate proxy configuration detected

🔒 PROXY CONFIGURATION
   Detected: Yes
   Working: Yes

🌐 CONNECTIVITY TESTS
   ✅ Google DNS: 8.8.8.8:53 (0.045s)
   ✅ Google HTTPS: www.google.com:443 (0.234s)
   ✅ GitHub: github.com:443 (0.187s)
   ✅ HTTPBin: httpbin.org:443 (0.298s)

💡 RECOMMENDATIONS
   1. Network configuration appears to be working correctly.
```

### Streamlit Dashboard Integration

The Streamlit dashboard automatically shows network status:

```python
from streamlit_dashboard.network_enhanced_requests import display_network_diagnostics_sidebar

# In your Streamlit app
display_network_diagnostics_sidebar()
```

This adds network diagnostics to the sidebar showing:
- Connectivity status
- Proxy configuration
- SSL verification status
- Real-time network health

## Troubleshooting

### Common Issues

#### 1. Proxy Connection Failures

**Symptoms**: `Connection failed`, `Proxy authentication required`

**Solutions**:
```bash
# Verify proxy settings
echo $HTTP_PROXY
echo $HTTPS_PROXY

# Test proxy connectivity
curl -x $HTTP_PROXY https://httpbin.org/get

# Check authentication
python scripts/network_diagnostics.py --proxy-test
```

#### 2. SSL Certificate Errors

**Symptoms**: `SSL certificate verify failed`, `Certificate validation error`

**Solutions**:
```bash
# Check certificate bundle
ls -la $REQUESTS_CA_BUNDLE
openssl x509 -in $REQUESTS_CA_BUNDLE -text -noout

# Test certificate validation
python scripts/network_diagnostics.py --cert-check

# Temporarily disable for testing (not recommended)
export PYTHONHTTPSVERIFY=0
```

#### 3. DNS Resolution Issues

**Symptoms**: `Name resolution failed`, `Host not found`

**Solutions**:
```bash
# Test DNS resolution
nslookup github.com
dig github.com

# Check DNS configuration
cat /etc/resolv.conf

# Test with network diagnostics
python scripts/network_diagnostics.py --full
```

#### 4. Timeout Issues

**Symptoms**: `Connection timed out`, `Request timeout`

**Solutions**:
```yaml
# Increase timeouts in configuration
corporate_network:
  timeouts:
    connection_timeout: 60    # Increase from 30
    total_timeout: 600        # Increase from 300
    max_retries: 5            # Increase from 3
```

### Advanced Troubleshooting

#### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run with debug output
python scripts/network_diagnostics.py --full --detailed
```

#### Capture Network Traffic

```bash
# Use tcpdump to capture traffic (requires root)
sudo tcpdump -i any -w network_capture.pcap host proxy.company.com

# Analyze with Wireshark or similar tool
```

#### Test Individual Components

```bash
# Test proxy directly
curl -v -x http://proxy.company.com:8080 https://httpbin.org/get

# Test SSL/TLS
openssl s_client -connect github.com:443 -servername github.com

# Test DNS
dig @8.8.8.8 github.com
```

## Integration Guide

### Streamlit Dashboard

The Streamlit dashboard automatically includes corporate network support:

```python
# File: streamlit_dashboard/your_app.py
from network_enhanced_requests import (
    get_network_client,
    check_dagster_connection,
    show_network_status_widget,
    display_network_diagnostics_sidebar
)

# Show network status
show_network_status_widget()

# Add diagnostics to sidebar
display_network_diagnostics_sidebar()

# Test Dagster connection with corporate support
success, message = check_dagster_connection()
if success:
    st.success(message)
else:
    st.warning(message)
```

### PlanAlign Orchestrator

The orchestrator automatically uses corporate network settings:

```python
from planalign_orchestrator.dbt_runner import DbtRunner

# DbtRunner automatically includes corporate network support
runner = DbtRunner(
    working_dir=Path("dbt"),
    threads=1,
    verbose=True
)

# All dbt commands will use corporate proxy and certificates
result = runner.execute_command(["run", "--select", "model_name"])
```

### Custom Network Operations

For custom network operations, use the corporate network client:

```python
from planalign_orchestrator.network_utils import create_network_client

# Create corporate network-aware client
client = create_network_client()

# Make HTTP requests with automatic proxy and certificate support
response = client.get("https://api.example.com/data")
print(f"Status: {response.status_code}")
print(f"Content: {response.content}")
```

## Security Considerations

### Best Practices

1. **Use System Authentication**: Avoid storing proxy credentials in configuration files
2. **Certificate Validation**: Always enable SSL certificate verification in production
3. **Secure Configuration**: Protect configuration files with appropriate permissions
4. **Regular Updates**: Keep certificate bundles and proxy settings updated
5. **Monitor Access**: Log and monitor network access patterns

### Configuration Security

```bash
# Set secure permissions on configuration files
chmod 600 config/simulation_config.yaml
chown user:group config/simulation_config.yaml

# Use environment variables for sensitive data
export PROXY_USERNAME="username"
export PROXY_PASSWORD="password"
```

### Compliance Requirements

- **Data Protection**: All network traffic uses HTTPS with certificate validation
- **Audit Trail**: Network operations are logged for compliance monitoring
- **Access Control**: Proxy authentication ensures authorized access only
- **Encryption**: End-to-end encryption for all corporate network communications

### Risk Mitigation

1. **Network Isolation**: Use corporate VPN and firewalls
2. **Certificate Pinning**: Validate specific corporate certificates
3. **Timeout Limits**: Prevent resource exhaustion with appropriate timeouts
4. **Error Handling**: Graceful degradation when network services unavailable
5. **Monitoring**: Real-time network health monitoring and alerting

## Support and Maintenance

### Regular Maintenance Tasks

1. **Update Certificate Bundles**: Corporate certificates expire and need updates
2. **Monitor Network Health**: Run diagnostics regularly to detect issues early
3. **Review Proxy Logs**: Check proxy server logs for connection patterns
4. **Update Configuration**: Adjust timeouts and settings based on performance
5. **Security Reviews**: Regular security assessments of network configuration

### Getting Help

1. **Run Network Diagnostics**: Always start with the diagnostic tool
2. **Check Logs**: Review application and system logs for network errors
3. **Test Connectivity**: Use built-in testing tools to isolate issues
4. **Contact IT**: Work with corporate IT for proxy and certificate issues
5. **Documentation**: Refer to this guide and inline code documentation

For additional support, contact your system administrator or refer to the Fidelity PlanAlign Engine documentation.
