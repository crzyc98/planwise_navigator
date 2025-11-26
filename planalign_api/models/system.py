"""System health and status models."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response for health check endpoint."""

    healthy: bool = Field(description="Whether the system is healthy")
    issues: List[str] = Field(default_factory=list, description="Blocking issues")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking warnings")


class SystemStatus(BaseModel):
    """Detailed system status response."""

    system_ready: bool = Field(description="Whether the system is ready for simulations")
    system_message: str = Field(description="Human-readable status message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Simulation status
    active_simulations: int = Field(default=0, description="Number of running simulations")
    queued_simulations: int = Field(default=0, description="Number of queued simulations")

    # Storage
    total_storage_mb: float = Field(default=0.0, description="Total storage used in MB")
    storage_limit_mb: float = Field(description="Storage limit in MB")
    storage_percent: float = Field(default=0.0, description="Storage usage percentage")

    # Workspace stats
    workspace_count: int = Field(default=0, description="Number of workspaces")
    scenario_count: int = Field(default=0, description="Total number of scenarios")

    # Performance
    thread_count: int = Field(default=1, description="Available thread count")

    # Recommendations
    recommendations: List[str] = Field(
        default_factory=list, description="System recommendations"
    )
