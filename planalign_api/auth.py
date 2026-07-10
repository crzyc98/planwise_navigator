"""Optional shared-token authentication for the PlanAlign API."""

from fastapi import HTTPException, Request, status

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

    if supplied_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid PlanAlign API token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
