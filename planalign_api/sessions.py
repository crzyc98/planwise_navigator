"""In-memory session store for Studio cookie authentication."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import secrets
import threading
import time

SESSION_COOKIE_NAME = "planalign_session"
DEFAULT_MAX_SESSIONS = 1024


def token_digest(token: str) -> bytes:
    """Return a fixed-length digest binding a session to the active API token."""
    return hashlib.sha256(token.encode("utf-8")).digest()


@dataclass(frozen=True)
class _SessionRecord:
    expires_at: float
    token_digest: bytes | None = None


class SessionStore:
    """Thread-safe, bounded in-memory session store with per-session expiry."""

    def __init__(
        self,
        *,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be at least 1")
        self._max_sessions = max_sessions
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, _SessionRecord] = OrderedDict()

    def _now(self) -> float:
        return self._clock() if self._clock is not None else time.monotonic()

    def _prune_expired_locked(self, now: float) -> None:
        expired = [
            session_id
            for session_id, record in self._sessions.items()
            if record.expires_at <= now
        ]
        for session_id in expired:
            del self._sessions[session_id]

    def create(
        self,
        ttl_seconds: float,
        *,
        token_digest: bytes | None = None,
    ) -> str:
        """Create and store a new random session id, dropping the oldest if full."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        session_id = secrets.token_urlsafe(32)
        with self._lock:
            now = self._now()
            self._prune_expired_locked(now)
            while len(self._sessions) >= self._max_sessions:
                self._sessions.popitem(last=False)
            self._sessions[session_id] = _SessionRecord(
                expires_at=now + ttl_seconds,
                token_digest=token_digest,
            )
        return session_id

    def is_valid(
        self,
        session_id: str | None,
        *,
        token_digest: bytes | None = None,
    ) -> bool:
        """Return whether session_id exists, is unexpired, and matches token_digest."""
        if not session_id:
            return False
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return False
            if record.expires_at <= self._now():
                del self._sessions[session_id]
                return False
            if token_digest is not None:
                return record.token_digest is not None and secrets.compare_digest(
                    record.token_digest, token_digest
                )
            return record.token_digest is None

    def revoke(self, session_id: str | None) -> None:
        """Remove a session id if present."""
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        """Remove all stored sessions."""
        with self._lock:
            self._sessions.clear()

    def count(self) -> int:
        """Return the number of currently live (unexpired) sessions."""
        with self._lock:
            self._prune_expired_locked(self._now())
            return len(self._sessions)


_session_store = SessionStore()


def get_session_store() -> SessionStore:
    """Return the process-wide session store."""
    return _session_store
