"""Session sign-in and sign-out endpoints for Studio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..auth import (
    _tokens_match,
    is_request_authenticated,
    require_allowed_origin,
)
from ..config import APISettings, get_settings
from ..models.auth import SessionSignInRequest, SessionStatusResponse
from ..sessions import SESSION_COOKIE_NAME, get_session_store, token_digest

router = APIRouter()


def _is_https(request: Request) -> bool:
    """Return whether the browser reached Studio over HTTPS, directly or via a proxy."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return request.url.scheme == "https" or forwarded.lower() == "https"


_INVALID_TOKEN_DETAIL = "Invalid PlanAlign API token."


@router.get("/session", response_model=SessionStatusResponse)
def get_session_status(
    request: Request,
    response: Response,
    settings: APISettings = Depends(get_settings),
) -> SessionStatusResponse:
    """Return whether authentication is required and whether the caller has a session."""
    response.headers["Cache-Control"] = "no-store"
    auth_required = settings.api_token is not None
    authenticated = auth_required and is_request_authenticated(request)
    return SessionStatusResponse(
        auth_required=auth_required,
        authenticated=authenticated,
    )


@router.post(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_allowed_origin)],
)
def create_session(
    body: SessionSignInRequest,
    request: Request,
    settings: APISettings = Depends(get_settings),
) -> Response:
    """Verify the shared token and set an HttpOnly session cookie."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Cache-Control"] = "no-store"
    expected_token = settings.api_token
    if expected_token is None:
        return response

    if not _tokens_match(body.token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_DETAIL,
        )

    store = get_session_store()
    existing_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if existing_session_id:
        store.revoke(existing_session_id)

    ttl_seconds = settings.session_ttl_hours * 3600
    session_id = store.create(
        ttl_seconds,
        token_digest=token_digest(expected_token),
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=int(ttl_seconds),
        path="/",
        httponly=True,
        samesite="strict",
        secure=_is_https(request),
    )
    return response


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_allowed_origin)],
)
def delete_session(request: Request) -> Response:
    """Revoke the current session and clear the session cookie."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        get_session_store().revoke(session_id)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=_is_https(request),
    )
    return response
