"""API configuration settings."""

import logging

from pathlib import Path
from typing import List

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class APISettings(BaseSettings):
    """Configuration for the PlanAlign API server."""

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    # validation_alias preserves the public PLANALIGN_API_TOKEN environment
    # variable while the class-wide PLANALIGN_API_ prefix serves other fields.
    api_token: str | None = Field(default=None, validation_alias="PLANALIGN_API_TOKEN")

    # Storage
    workspaces_root: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent / "workspaces"
    )
    storage_limit_gb: float = 10.0
    # Development-only escape hatch for legacy local databases. Production API
    # requests must resolve to scenario or workspace storage.
    allow_project_db_fallback: bool = False

    # CORS (for the local Studio dev server)
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # WebSocket
    telemetry_interval_ms: int = 500
    recent_events_limit: int = 20

    # Background tasks
    max_concurrent_simulations: int = 2

    # Default config path
    default_config_path: Path = Field(
        default_factory=lambda: Path("config/simulation_config.yaml")
    )

    class Config:
        env_prefix = "PLANALIGN_API_"
        env_file = ".env"

    @model_validator(mode="after")
    def validate_network_security(self) -> "APISettings":
        """Reject unsafe CORS exposure and flag unauthenticated remote bindings."""
        if self.host not in _LOOPBACK_HOSTS and self.cors_origins == ["*"]:
            raise ValueError(
                "PLANALIGN_API_HOST must not use wildcard CORS when bound to a "
                "non-loopback address. Configure explicit PLANALIGN_API_CORS_ORIGINS."
            )

        if self.host not in _LOOPBACK_HOSTS and not self.api_token:
            logger.warning(
                "SECURITY WARNING: PlanAlign API is bound to non-loopback host %s "
                "without PLANALIGN_API_TOKEN; all API routes are unauthenticated.",
                self.host,
            )

        return self


# Global settings instance
settings = APISettings()


def get_settings() -> APISettings:
    """Get the global settings instance."""
    return settings
