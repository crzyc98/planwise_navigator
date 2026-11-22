"""API configuration settings."""

import logging

from pathlib import Path
from typing import Annotated, List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode

from .trusted_hosts import normalize_host

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_WILDCARD_BIND_HOSTS = {"0.0.0.0", "::", "[::]", ""}


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

    # Host header allowlist for HTTP and WebSocket requests. The bind host is
    # added automatically when it is a specific address (see trusted_hosts).
    # NoDecode lets the env var be a plain comma-separated list.
    allowed_hosts: Annotated[List[str], NoDecode] = ["localhost", "127.0.0.1", "::1"]

    # WebSocket
    telemetry_interval_ms: int = 500
    recent_events_limit: int = 20

    # Background tasks
    # Studio runs simulations one at a time unless a server raises this.
    max_concurrent_simulations: int = Field(default=1, ge=1)
    # Maximum jobs waiting for a simulation slot per job type (429 beyond this).
    max_queued_jobs_per_type: int = Field(default=10, ge=0)
    # In-memory operation-history retention. Active operations are always kept.
    batch_operation_ttl_seconds: float = Field(default=3600.0, gt=0)
    batch_operation_max_entries: int = Field(default=100, gt=0)
    bulk_import_operation_ttl_seconds: float = Field(default=3600.0, gt=0)
    bulk_import_operation_max_entries: int = Field(default=100, gt=0)
    # Finished parameter fit/backtest jobs kept per workspace (#588). Running
    # jobs are never pruned.
    param_fit_max_jobs_per_workspace: int = Field(default=20, gt=0)

    # Workspace import archive extraction limits (PLANALIGN_API_IMPORT_MAX_*)
    import_max_unpacked_bytes: int = Field(default=10 * 1024 * 1024 * 1024, gt=0)
    import_max_member_bytes: int = Field(default=4 * 1024 * 1024 * 1024, gt=0)
    import_max_member_count: int = Field(default=10_000, gt=0)

    # Default config path
    default_config_path: Path = Field(
        default_factory=lambda: Path("config/simulation_config.yaml")
    )

    # Default scan root for the Studio ensemble-database picker
    ensembles_root: Path = Field(default_factory=lambda: Path("var/ensembles"))

    # Optimizer runs started through the API write only under this root
    optimizer_runs_root: Path = Field(
        default_factory=lambda: Path("var/optimizer_runs")
    )

    # Git remote sync policy (SSRF / outbound-network control)
    # Allowed URL schemes for sync remotes; widen only deliberately.
    git_remote_allowed_schemes: List[str] = ["https", "ssh"]
    # Optional exact-host/suffix allowlist. Empty list permits any public host.
    git_remote_allowed_hosts: List[str] = []
    # Opt-in to loopback/private/link-local destinations (e.g., self-hosted
    # internal Git servers). Keep disabled unless the network is trusted.
    git_remote_allow_private_networks: bool = False

    class Config:
        env_prefix = "PLANALIGN_API_"
        env_file = ".env"

    @field_validator(
        "allowed_hosts",
        "git_remote_allowed_schemes",
        "git_remote_allowed_hosts",
        mode="before",
    )
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """Accept comma-separated env values in addition to JSON lists."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, value: List[str]) -> List[str]:
        """Require explicit, valid host names; wildcards are not supported."""
        if not value:
            raise ValueError("PLANALIGN_API_ALLOWED_HOSTS must list at least one host")
        if any("*" in host for host in value):
            raise ValueError(
                "PLANALIGN_API_ALLOWED_HOSTS does not support wildcards; "
                "list each host name explicitly"
            )
        if any(not normalize_host(host) for host in value):
            raise ValueError(
                "PLANALIGN_API_ALLOWED_HOSTS contains an invalid host entry"
            )
        return value

    @property
    def trusted_hosts(self) -> List[str]:
        """Allowed Host values, plus the bind host when it is a specific address."""
        if self.host in _WILDCARD_BIND_HOSTS or self.host in self.allowed_hosts:
            return list(self.allowed_hosts)
        return [*self.allowed_hosts, self.host]

    @property
    def ensemble_roots(self) -> List[Path]:
        """Where API callers may read ensemble databases: the picker root, and
        workspaces, where Studio ensemble jobs write their databases."""
        return [self.ensembles_root, self.workspaces_root]

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
