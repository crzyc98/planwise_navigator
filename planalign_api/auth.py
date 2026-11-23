"""Optional shared-token and session-cookie authentication for the PlanAlign API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import secrets

from fastapi import HTTPException, Request, WebSocket, status

from .config import get_settings
from .sessions import SESSION_COOKIE_NAME, get_session_store, token_digest

_SAFE_COOKIE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _tokens_match(supplied_token: str | None, expected_token: str) -> bool:
    """Compare tokens in constant time; empty tokens never authenticate."""
    if not expected_token or not supplied_token:
        return False
    return secrets.compare_digest(
        supplied_token.encode("utf-8"),
        expected_token.encode("utf-8"),
    )


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extract the token from an Authorization: Bearer header, if present."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    return None


def _is_origin_allowed(origin: str | None, allowed_origins: Sequence[str]) -> bool:
    """Return whether origin is present and allowed by the CORS configuration."""
    return bool(origin and ("*" in allowed_origins or origin in allowed_origins))


def require_allowed_origin(request: Request) -> None:
    """Require an HTTP Origin header allowed by the CORS configuration."""
    origin = request.headers.get("origin")
    allowed_origins = get_settings().cors_origins
    if not _is_origin_allowed(origin, allowed_origins):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This address is not an allowed origin. Add the Studio address to "
                "PLANALIGN_API_CORS_ORIGINS."
            ),
        )


def _has_valid_header_token(request: Request, expected_token: str) -> bool:
    bearer_token = _extract_bearer_token(request.headers.get("Authorization"))
    supplied_token = bearer_token or request.headers.get("X-API-Token")
    return _tokens_match(supplied_token, expected_token)


def _has_valid_session_cookie(cookies: Mapping[str, str], expected_token: str) -> bool:
    if not expected_token:
        return False
    session_id = cookies.get(SESSION_COOKIE_NAME)
    return get_session_store().is_valid(
        session_id,
        token_digest=token_digest(expected_token),
    )


def is_request_authenticated(request: Request) -> bool:
    """Return whether a request carries a valid header token or session cookie."""
    expected_token = get_settings().api_token
    if expected_token is None:
        return False
    return _has_valid_header_token(
        request, expected_token
    ) or _has_valid_session_cookie(request.cookies, expected_token)


async def require_api_token(request: Request) -> None:
    """Require the configured shared API token via header or session cookie."""
    expected_token = get_settings().api_token
    if expected_token is None:
        return

    if _has_valid_header_token(request, expected_token):
        return

    if _has_valid_session_cookie(request.cookies, expected_token):
        if request.method.upper() not in _SAFE_COOKIE_METHODS:
            require_allowed_origin(request)
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid PlanAlign API token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_websocket_api_token(websocket: WebSocket) -> bool:
    """Authorize a WebSocket via Bearer header or session cookie before accept."""
    expected_token = get_settings().api_token
    if expected_token is None:
        return True

    bearer_token = _extract_bearer_token(websocket.headers.get("authorization"))
    if _tokens_match(bearer_token, expected_token):
        return True

    if _has_valid_session_cookie(websocket.cookies, expected_token):
        return True

    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return False


async def require_websocket_origin(websocket: WebSocket) -> bool:
    """Require a WebSocket handshake Origin allowed by the CORS configuration."""
    origin = websocket.headers.get("origin")
    allowed_origins = get_settings().cors_origins
    if _is_origin_allowed(origin, allowed_origins):
        return True

    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return False
