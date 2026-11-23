"""Authentication session request and response models."""

from __future__ import annotations

from pydantic import Field

from .base import APIModel


class SessionStatusResponse(APIModel):
    """Current authentication requirement and caller session status."""

    auth_required: bool = Field(
        description="Whether the API requires authentication",
    )
    authenticated: bool = Field(
        description="Whether the caller is currently authenticated",
    )


class SessionSignInRequest(APIModel):
    """Credentials submitted to establish a Studio session cookie."""

    token: str = Field(
        description="Shared API token",
        repr=False,
    )
