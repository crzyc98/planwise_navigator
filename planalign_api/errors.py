"""Client-safe error response utilities for the PlanAlign API.

Raw exception text must never reach API callers: exception messages can
disclose absolute paths, SQL fragments, credentials, or configuration
values. Use :func:`sanitize_error` from generic exception handlers — it
keeps full details (including traceback) in structured server logs and
returns only a stable, client-safe message. Callers correlate failures
with server logs via the request ID assigned by the API middleware.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar
from typing import Optional

REQUEST_ID_HEADER = "X-Request-ID"

# Client-supplied correlation IDs are echoed into responses and structured
# logs, so they are restricted to a conservative charset and length to rule
# out log injection or oversized header/log values.
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")

GENERIC_500_DETAIL = "Internal server error"

_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """Generate a fresh correlation ID."""
    return uuid.uuid4().hex


def normalize_request_id(raw: Optional[str]) -> str:
    """Return ``raw`` if it is a safe correlation ID, else a generated one."""
    if raw and _REQUEST_ID_PATTERN.fullmatch(raw):
        return raw
    return new_request_id()


def set_request_id(value: str) -> None:
    """Record the correlation ID for the current request context."""
    _request_id.set(value)


def get_request_id() -> Optional[str]:
    """Return the correlation ID for the current request context, if any."""
    return _request_id.get()


def sanitize_error(
    log: logging.Logger,
    message: str,
    *,
    event: str = "Unhandled API error",
) -> str:
    """Log full exception details server-side; return ``message`` for clients.

    Must be called from within an ``except`` block so ``logger.exception``
    captures the active traceback.
    """
    log.exception("%s [request_id=%s]", event, get_request_id())
    return message


def sanitize_job_error(
    log: logging.Logger,
    job_label: str,
    *,
    event: str = "Background job failed",
) -> str:
    """Build a client-safe error record for a failed background job.

    Full details stay in the logs under a generated error ID that is also
    embedded in the returned record so support can locate them.
    """
    error_id = uuid.uuid4().hex
    log.exception(
        "%s [%s] [error_id=%s] [request_id=%s]",
        event,
        job_label,
        error_id,
        get_request_id(),
    )
    return f"{event} (error_id: {error_id})"
