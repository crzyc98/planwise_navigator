"""Process-level security defaults.

Sets a restrictive POSIX umask so databases, census copies, exports, logs, and
config files created by PlanAlign are readable only by the account running it,
and keeps API credentials out of the environment of child processes.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

logger = logging.getLogger(__name__)

DEFAULT_UMASK = 0o077
UMASK_ENV_VAR = "PLANALIGN_UMASK"
_MAX_UMASK = 0o777
_OCTAL_DIGITS = frozenset("01234567")

API_TOKEN_ENV_VAR = "PLANALIGN_API_TOKEN"
_API_ENV_PREFIX = "PLANALIGN_API_"
_CREDENTIAL_MARKERS = ("TOKEN", "SECRET", "PASSWORD")


def parse_umask(raw: str | None) -> int:
    """Parse an octal umask value from ``PLANALIGN_UMASK``.

    Returns ``DEFAULT_UMASK`` (``0o077``) when unset or blank. Invalid values
    log a warning and fall back to ``DEFAULT_UMASK``.
    """
    if raw is None:
        return DEFAULT_UMASK
    text = raw.strip()
    if not text:
        return DEFAULT_UMASK

    digits = text[2:] if text.startswith(("0o", "0O")) else text
    if not digits or any(ch not in _OCTAL_DIGITS for ch in digits):
        logger.warning(
            "Invalid %s=%r (expected octal permissions mask); falling back to %03o",
            UMASK_ENV_VAR,
            raw,
            DEFAULT_UMASK,
        )
        return DEFAULT_UMASK

    value = int(digits, 8)
    if value > _MAX_UMASK:
        logger.warning(
            "Invalid %s=%r (must be <= 0777); falling back to %03o",
            UMASK_ENV_VAR,
            raw,
            DEFAULT_UMASK,
        )
        return DEFAULT_UMASK
    return value


def restrict_file_permissions() -> None:
    """Apply the configured process umask on POSIX systems (no-op on Windows)."""
    if os.name != "posix":
        return
    mask = parse_umask(os.environ.get(UMASK_ENV_VAR))
    os.umask(mask)


def is_child_env_denied(name: str) -> bool:
    """Whether ``name`` holds an API credential that child processes never need.

    Denied: ``PLANALIGN_API_TOKEN`` and any ``PLANALIGN_API_*`` variable whose
    name contains ``TOKEN``, ``SECRET`` or ``PASSWORD`` (case-insensitive).
    """
    upper = name.upper()
    if upper == API_TOKEN_ENV_VAR:
        return True
    return upper.startswith(_API_ENV_PREFIX) and any(
        marker in upper for marker in _CREDENTIAL_MARKERS
    )


def scrub_child_env(env: Mapping[str, str]) -> dict[str, str]:
    """Copy ``env`` without the names :func:`is_child_env_denied` matches."""
    return {key: value for key, value in env.items() if not is_child_env_denied(key)}


def remove_denied_env_vars() -> None:
    """Drop denied names from this process's own environment (worker start-up)."""
    for name in [key for key in os.environ if is_child_env_denied(key)]:
        os.environ.pop(name, None)
