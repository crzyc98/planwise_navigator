"""Optional shared-token authentication for the PlanAlign API."""

import secrets

from fastapi import HTTPException, Request, WebSocket, status

from .config import get_settings


async def require_api_token(request: Request) -> None:
    """Require the configured shared API token, when one is configured."""
    expected_token = get_settings().api_token
    if expected_token is None:
        return

    authorization = request.headers.get("Authorization")
    bearer_token = (
        authorization.removeprefix("Bearer ")
        if authorization and authorization.startswith("Bearer ")
        else None
    )
    supplied_token = bearer_token or request.headers.get("X-API-Token")

    if supplied_token is None or not secrets.compare_digest(
        supplied_token, expected_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid PlanAlign API token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_websocket_api_token(websocket: WebSocket) -> bool:
    """Authorize a WebSocket before it is accepted by an endpoint handler."""
    expected_token = get_settings().api_token
    if expected_token is None:
        return True

    supplied_token = websocket.query_params.get("token")
    if (
        supplied_token is not None
        # compare_digest raises TypeError on non-ASCII str inputs
        and supplied_token.isascii()
        and secrets.compare_digest(supplied_token, expected_token)
    ):
        return True

    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return False
