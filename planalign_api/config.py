"""API configuration settings."""

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class APISettings(BaseSettings):
    """Configuration for the PlanAlign API server."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Storage
    workspaces_root: Path = Field(
        default_factory=lambda: Path.home() / ".planalign" / "workspaces"
    )
    storage_limit_gb: float = 10.0

    # CORS (for React dev server)
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:3003",
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3003",
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


# Global settings instance
settings = APISettings()


def get_settings() -> APISettings:
    """Get the global settings instance."""
    return settings
