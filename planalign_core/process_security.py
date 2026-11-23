"""Process-level filesystem permission defaults.

Sets a restrictive POSIX umask so databases, census copies, exports, logs, and
config files created by PlanAlign are readable only by the account running it.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_UMASK = 0o077
UMASK_ENV_VAR = "PLANALIGN_UMASK"
_MAX_UMASK = 0o777
_OCTAL_DIGITS = frozenset("01234567")


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
