"""Git remote URL policy enforcement for workspace sync.

The sync initialization API, CLI, and subsequent fetch/pull/push operations
validate the remote URL through a single policy gate before any Git network
transport runs:

- Only explicitly allowlisted schemes are accepted (default: ``https``, ``ssh``).
- Local/file/``ext::``-style transports, ambiguous authorities, and malformed
  URLs are rejected.
- Hostnames are resolved via ``getaddrinfo`` and every resolved address must
  be a globally reachable unicast destination unless
  ``PLANALIGN_API_GIT_REMOTE_ALLOW_PRIVATE_NETWORKS`` is set.
- An optional host allowlist restricts destinations further.
- ``redact_remote_url`` removes embedded userinfo from URLs in strings (logs,
  error messages, config files, and API responses).
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import TYPE_CHECKING, List, Optional, overload
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ..config import APISettings

logger = logging.getLogger(__name__)


class RemotePolicyError(Exception):
    """Raised when a remote URL violates the configured remote policy."""


# scp-like syntax: [user@]host:path with no scheme prefix.
_SCP_LIKE_RE = re.compile(r"^(?P<user>[^@/\s:]+@)?(?P<host>[^/@\s:]+):(?P<path>.+)$")

# Matches scheme://... URL tokens inside arbitrary text (e.g. git stderr).
_URL_TOKEN_RE = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<rest>[^\s'\"<>()]+)"
)

# Matches scp-like user:secret@host:path (plain git@host:path without ':' stays intact).
_SCP_CREDENTIAL_RE = re.compile(
    r"(?<![:/\w])[^/@:\s]+:[^@\s]*@(?P<target>[^/@\s:]+:[^\s'\"<>()]+)"
)

# Allowed userinfo format in remote URLs: user with optional ':secret'.
_USERINFO_RE = re.compile(r"^[A-Za-z0-9._-]+(:[^@/\s]*)?$")

# Matches hosts made only of decimal/hex digits, 'x', and dots.
_NUMERIC_OR_HEX_HOST_RE = re.compile(r"^[0-9a-fA-FxX.]+$")

_DISALLOWED_URL_CHARS = frozenset("#?\\%")
_FORBIDDEN_TRANSPORTS = ("file://", "ext::", "local::")
_MAX_URL_LENGTH = 2048
_BLOCKED_DEST_MSG = "Remote host is not an allowed destination"


@overload
def redact_remote_url(text: None) -> None: ...


@overload
def redact_remote_url(text: str) -> str: ...


def redact_remote_url(text: Optional[str]) -> Optional[str]:
    """Remove all userinfo from ``scheme://`` URLs in an arbitrary string.

    Plain scp-style ``git@host:path`` remotes without embedded secrets are
    preserved as-is for readability.
    """
    if not text:
        return text
    redacted = _URL_TOKEN_RE.sub(_redact_url_token, text)
    return _SCP_CREDENTIAL_RE.sub(lambda m: m.group("target"), redacted)


def _redact_url_token(match: re.Match[str]) -> str:
    """Strip userinfo from a single ``scheme://...`` match."""
    scheme = match.group("scheme")
    rest = match.group("rest")
    if "@" not in rest:
        return match.group(0)

    before_slash, slash, after_slash = rest.partition("/")
    if "@" in before_slash:
        if (
            ":" in before_slash
            and not before_slash.startswith("[")
            and "@" in after_slash
            and "/" in after_slash.rsplit("@", 1)[1]
        ):
            _, host_and_path = rest.rsplit("@", 1)
            return f"{scheme}://{host_and_path}"
        _, hostport = before_slash.rsplit("@", 1)
        return f"{scheme}://{hostport}{slash}{after_slash}"

    if ":" in before_slash and not before_slash.startswith("["):
        _, host_and_path = rest.rsplit("@", 1)
        return f"{scheme}://{host_and_path}"

    if (
        not after_slash.startswith("@")
        and "/" in after_slash.rsplit("@", 1)[1]
        and "." not in before_slash
        and before_slash.lower() != "localhost"
    ):
        _, host_and_path = rest.rsplit("@", 1)
        return f"{scheme}://{host_and_path}"

    return match.group(0)


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
        The normalized URL string if it is allowed (stripped, scheme
        lowercased; scp-style remotes keep their form). Callers must pass this
        validated value to Git and use :func:`redact_remote_url` before
        persisting it in config files, logging, or returning it.

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
    scheme = normalized.split("://", 1)[0]
    _check_scheme(scheme, settings.git_remote_allowed_schemes)

    raw_host = _parse_and_verify_authority(normalized, scheme)
    _reject_obfuscated_ip_host(raw_host)

    hostname = raw_host.rstrip(".")
    if not hostname:
        raise RemotePolicyError("Remote URL is missing a host name.")

    _check_host_allowlist(hostname, settings.git_remote_allowed_hosts)
    _check_destination(hostname, settings.git_remote_allow_private_networks)

    # scp-style remotes keep their form: their path is relative to the remote
    # user's home, which an ssh:// rewrite would change.
    return normalized if "://" in url else url


def _reject_malformed(url: str) -> None:
    """Reject empty, oversized, or syntactically disallowed URLs."""
    if not url:
        raise RemotePolicyError("Remote URL must not be empty.")
    if len(url) > _MAX_URL_LENGTH:
        raise RemotePolicyError("Remote URL exceeds the maximum allowed length.")
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in url):
        raise RemotePolicyError("Remote URL contains control characters.")
    lowered = url.lower()
    if lowered.startswith(_FORBIDDEN_TRANSPORTS):
        raise RemotePolicyError(
            f"Remote transport '{lowered.split(':', 1)[0]}' is not allowed."
        )
    if any(ch.isspace() for ch in url):
        raise RemotePolicyError("Whitespace is not allowed in remote URLs.")
    if any(ch in _DISALLOWED_URL_CHARS for ch in url):
        raise RemotePolicyError("Remote URL contains disallowed characters.")


def _normalize_transport(url: str) -> str:
    """Normalize scp-like syntax to ssh:// and lowercase explicit schemes."""
    if "://" in url:
        scheme, rest = url.split("://", 1)
        return f"{scheme.lower()}://{rest}"

    # No scheme: accept only scp-like "[user@]host:path" as SSH.
    match = _SCP_LIKE_RE.match(url)
    if not match:
        raise RemotePolicyError(
            "Remote URL must be an https:// or ssh:// URL "
            "(or scp-style user@host:path)."
        )
    if len(match.group("host")) < 2:
        raise RemotePolicyError(
            "Local filesystem paths are not allowed as sync remotes."
        )
    user = match.group("user") or ""
    path = match.group("path").lstrip("/")
    return f"ssh://{user}{match.group('host')}/{path}"


def _parse_hostport(hostport: str) -> str:
    """Parse ``host[:port]`` (including bracketed IPv6) and return the host."""
    if hostport.startswith("["):
        bracket_end = hostport.find("]")
        if bracket_end == -1:
            raise RemotePolicyError("Remote URL contains a malformed IPv6 host.")
        host = hostport[1:bracket_end]
        port_part = hostport[bracket_end + 1 :]
        if port_part:
            if not port_part.startswith(":"):
                raise RemotePolicyError("Remote URL contains an invalid port.")
            _validate_port(port_part[1:])
        return host

    if ":" in hostport:
        host, port_str = hostport.rsplit(":", 1)
        if ":" in host:
            raise RemotePolicyError("Remote URL contains an invalid host.")
        _validate_port(port_str)
        return host

    return hostport


def _validate_port(port_str: str) -> None:
    if not port_str.isdigit():
        raise RemotePolicyError("Remote URL contains an invalid port.")
    port_num = int(port_str)
    if not (1 <= port_num <= 65535):
        raise RemotePolicyError("Remote URL port is out of range.")


def _parse_and_verify_authority(normalized: str, expected_scheme: str) -> str:
    """Validate authority grammar and require Git-style parsing to match urlparse."""
    rest = normalized.split("://", 1)[1]
    authority = rest.split("/", 1)[0]
    if not authority:
        raise RemotePolicyError("Remote URL is missing a host name.")
    if authority.count("@") > 1:
        raise RemotePolicyError("Remote URL authority must contain at most one '@'.")

    if "@" in authority:
        userinfo, hostport = authority.rsplit("@", 1)
        if (
            not userinfo
            or userinfo.startswith("-")
            or not _USERINFO_RE.fullmatch(userinfo)
        ):
            raise RemotePolicyError("Remote URL contains invalid user credentials.")
    else:
        hostport = authority

    git_host = _parse_hostport(hostport)
    if not git_host:
        raise RemotePolicyError("Remote URL is missing a host name.")
    if git_host.startswith("-"):
        raise RemotePolicyError("Remote host must not start with '-'.")

    parsed = urlparse(normalized)
    try:
        _ = parsed.port
    except ValueError as exc:
        raise RemotePolicyError("Remote URL contains an invalid port.") from exc

    parsed_host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != expected_scheme
        or not parsed_host
        or git_host.lower() != parsed_host
    ):
        raise RemotePolicyError("Remote URL host could not be parsed unambiguously.")

    return git_host.lower()


def _reject_obfuscated_ip_host(raw_host: str) -> None:
    """Reject numeric/hex/octal host strings unless they are canonical IPv4."""
    if not _NUMERIC_OR_HEX_HOST_RE.fullmatch(raw_host):
        return
    try:
        canonical = str(ipaddress.IPv4Address(raw_host))
    except ValueError as exc:
        raise RemotePolicyError(_BLOCKED_DEST_MSG) from exc
    if canonical != raw_host:
        raise RemotePolicyError(_BLOCKED_DEST_MSG)


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


def _is_allowed_public_address(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True only for globally reachable unicast addresses."""
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast and not addr.is_reserved


def _check_destination(hostname: str, allow_private_networks: bool) -> None:
    """Resolve the hostname and verify every address is a public destination."""
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        logger.warning("Cannot resolve remote host %r: %s", hostname, e)
        raise RemotePolicyError(_BLOCKED_DEST_MSG) from e

    addresses: List[str] = []
    for info in addr_infos:
        resolved = str(info[4][0])
        if resolved not in addresses:
            addresses.append(resolved)

    if not addresses:
        logger.warning("Remote host %r resolved to no addresses", hostname)
        raise RemotePolicyError(_BLOCKED_DEST_MSG)

    if allow_private_networks:
        return

    for addr_text in addresses:
        try:
            parsed_addr = ipaddress.ip_address(addr_text.split("%")[0])
        except ValueError as exc:
            logger.warning(
                "Rejected remote host %r: unparseable resolved address %r",
                hostname,
                addr_text,
            )
            raise RemotePolicyError(_BLOCKED_DEST_MSG) from exc
        if not _is_allowed_public_address(parsed_addr):
            logger.warning(
                "Rejected remote host %r: resolved address %s is not a public destination",
                hostname,
                addr_text,
            )
            raise RemotePolicyError(_BLOCKED_DEST_MSG)
