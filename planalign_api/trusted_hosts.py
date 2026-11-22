"""Reject HTTP and WebSocket requests whose Host header is not allowlisted.

Starlette's ``TrustedHostMiddleware`` splits the Host header on the first
colon, which turns a bracketed IPv6 host such as ``[::1]:8000`` into ``[``.
This middleware parses IPv6 hosts correctly and otherwise behaves the same.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_BRACKETED_IPV6 = re.compile(r"\[([0-9a-f:.]+)\](?::\d+)?")


def normalize_host(host: str) -> str:
    """Return a Host value without its port, IPv6 brackets or letter case.

    A malformed value returns ``""``, which is never allowed.
    """
    host = host.strip().lower()
    if host.startswith("["):
        match = _BRACKETED_IPV6.fullmatch(host)
        return match.group(1) if match else ""
    if host.count(":") > 1:  # bare IPv6 literal, e.g. from configuration
        return host
    if ":" in host:
        name, port = host.split(":", 1)
        return name if port.isascii() and port.isdigit() else ""
    return host


class TrustedHostMiddleware:
    """Answer 400 to any request whose Host is not in ``allowed_hosts``."""

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str]) -> None:
        self.app = app
        self.allowed_hosts = frozenset(
            normalized for h in allowed_hosts if (normalized := normalize_host(h))
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            hosts = Headers(scope=scope).getlist("host")
            host = normalize_host(hosts[0]) if len(hosts) == 1 else ""
            if not host or host not in self.allowed_hosts:
                response = PlainTextResponse("Invalid host header", status_code=400)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
