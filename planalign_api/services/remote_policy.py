"""Git remote URL policy enforcement for workspace sync (SSRF hardening).

The sync initialization API and CLI both accept an arbitrary remote URL that
Git will fetch from. This module defines a single policy gate applied before
any Git transport is created:

- Only explicitly allowlisted schemes are accepted (default: ``https``, ``ssh``).
- Local/file/``ext::``-style transports and malformed URLs are rejected.
- Hostnames are resolved via ``getaddrinfo`` and every resolved address must
  be a public destination; loopback, private, link-local (including cloud
  metadata services), reserved, and unspecified addresses are blocked unless
  ``PLANALIGN_API_GIT_REMOTE_ALLOW_PRIVATE_NETWORKS`` is set.
- An optional host allowlist restricts destinations further.
- ``redact_remote_url`` strips embedded passwords from any string (logs,
  error messages, API responses).
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import TYPE_CHECKING, List, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ..config import APISettings

logger = logging.getLogger(__name__)


class RemotePolicyError(Exception):
    """Raised when a remote URL violates the configured remote policy."""


# scp-like syntax: [user@]host:path with no scheme prefix.
_SCP_LIKE_RE = re.compile(r"^(?P<user>[^@/\s:]+@)?(?P<host>[^/@\s:]+):(?P<path>.+)$")

# Matches "user:password@" (optionally after scheme://) in arbitrary text so
# embedded credentials can be scrubbed from logs, errors, and responses.
_CREDENTIAL_RE = re.compile(
    r"(?P<prefix>(?:[A-Za-z][A-Za-z0-9+.-]*://)?[^/@:\s]+):(?P<secret>[^@\s/]*)@"
)

_MAX_URL_LENGTH = 2048


def redact_remote_url(text: Optional[str]) -> Optional[str]:
    """Replace embedded URL passwords with ``***`` in an arbitrary string."""
    if not text:
        return text
    return _CREDENTIAL_RE.sub(lambda m: f"{m.group('prefix')}:***@", text)


def validate_remote_url(
    remote_url: str,
    settings: Optional["APISettings"] = None,
) -> str:
    """Validate a Git remote URL against the configured policy.

    Args:
        remote_url: The remote URL supplied by the caller.
        settings: API settings providing the policy. Defaults to the global
            settings instance.

    Returns:
        The original URL string if it is allowed. The value is returned
        unchanged; callers must use :func:`redact_remote_url` before logging
        or returning it.

    Raises:
        RemotePolicyError: If the URL is malformed or violates the scheme,
            host allowlist, or network-destination policy.
    """
    if settings is None:
        from ..config import get_settings

        settings = get_settings()

    url = (remote_url or "").strip()
    _reject_malformed(url)

    normalized = _normalize_transport(url)
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").rstrip(".")

    _check_scheme(parsed.scheme, settings.git_remote_allowed_schemes)

    if not hostname:
        raise RemotePolicyError("Remote URL is missing a host name.")

    _check_host_allowlist(hostname, settings.git_remote_allowed_hosts)
    _check_destination(hostname, settings.git_remote_allow_private_networks)

    return url


def _reject_malformed(url: str) -> None:
    """Reject empty, oversized URLs and control characters."""
    if not url:
        raise RemotePolicyError("Remote URL must not be empty.")
    if len(url) > _MAX_URL_LENGTH:
        raise RemotePolicyError("Remote URL exceeds the maximum allowed length.")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in url):
        raise RemotePolicyError("Remote URL contains control characters.")


def _normalize_transport(url: str) -> str:
    """Normalize scp-like syntax to ssh://; reject local-path transports.

    Raises:
        RemotePolicyError: For local paths and unrecognized non-network forms
            such as ``ext::sh -c ...`` helper transports.
    """
    lowered = url.lower()
    if lowered.startswith(("file://", "ext::", "local::")):
        raise RemotePolicyError(
            f"Remote transport '{lowered.split(':', 1)[0]}' is not allowed."
        )

    if "://" in url:
        return url

    # No scheme: accept only scp-like "[user@]host:path" as SSH.
    match = _SCP_LIKE_RE.match(url)
    if not match:
        raise RemotePolicyError(
            "Remote URL must be an https:// or ssh:// URL "
            "(or scp-style user@host:path)."
        )
    if len(match.group("host")) < 2:
        # Single-character "host" indicates a local path (e.g., C:\...).
        raise RemotePolicyError(
            "Local filesystem paths are not allowed as sync remotes."
        )
    user = match.group("user") or ""
    path = match.group("path").lstrip("/")
    return f"ssh://{user}{match.group('host')}/{path}"


def _check_scheme(scheme: str, allowed_schemes: List[str]) -> None:
    allowed = {s.strip().lower() for s in allowed_schemes}
    if scheme.lower() not in allowed:
        raise RemotePolicyError(
            f"Remote URL scheme '{scheme}' is not allowed. "
            f"Allowed schemes: {', '.join(sorted(allowed))}."
        )


def _check_host_allowlist(hostname: str, allowed_hosts: List[str]) -> None:
    patterns = [h.strip().lower().lstrip(".") for h in allowed_hosts if h.strip()]
    if not patterns:
        return
    lowered = hostname.lower()
    if any(lowered == p or lowered.endswith(f".{p}") for p in patterns):
        return
    raise RemotePolicyError(
        f"Remote host '{hostname}' is not in the configured allowlist."
    )


def _check_destination(hostname: str, allow_private_networks: bool) -> None:
    """Resolve the hostname and verify every address is a public destination.

    Raises:
        RemotePolicyError: On resolution failure or blocked addresses when
            private networks are not permitted.
    """
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise RemotePolicyError(
            f"Cannot resolve remote host '{hostname}': {e.args[0]}"
        ) from e

    addresses: List[str] = []
    for info in addr_infos:
        addr = str(info[4][0])
        if addr not in addresses:
            addresses.append(addr)

    if allow_private_networks:
        return

    for addr_text in addresses:
        parsed_addr = ipaddress.ip_address(addr_text.split("%")[0])
        reason = _blocked_reason(parsed_addr)
        if reason:
            raise RemotePolicyError(
                f"Remote host '{hostname}' resolves to {addr}, a {reason}. "
                "Set PLANALIGN_API_GIT_REMOTE_ALLOW_PRIVATE_NETWORKS to "
                "explicitly permit internal Git servers."
            )


def _blocked_reason(
    addr: "ipaddress.IPv4Address | ipaddress.IPv6Address",
) -> Optional[str]:
    if addr.is_unspecified:
        return "unspecified address"
    if addr.is_loopback:
        return "loopback address"
    if addr.is_link_local:
        return "link-local address (possible metadata service)"
    if addr.is_private:
        return "private-network address"
    if addr.is_reserved or addr.is_multicast:
        return "reserved/multicast address"
    return None
