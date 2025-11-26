"""Simulation run and telemetry models."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PerformanceMetrics(BaseModel):
    """Real-time performance metrics during simulation."""

    memory_mb: float = Field(description="Memory usage in MB")
    memory_pressure: Literal["low", "moderate", "high", "critical"] = Field(
        description="Memory pressure level"
    )
    elapsed_seconds: float = Field(description="Elapsed time in seconds")
    events_generated: int = Field(description="Total events generated")
    events_per_second: float = Field(description="Event generation rate")


class RecentEvent(BaseModel):
    """Recent event from the simulation stream."""

    event_type: str = Field(description="Event type (HIRE, TERMINATION, etc.)")
    employee_id: str = Field(description="Employee ID")
    timestamp: datetime = Field(description="Event timestamp")
    details: Optional[str] = Field(None, description="Additional details")


class SimulationRun(BaseModel):
    """Simulation run status model."""

    id: str = Field(..., description="Unique run ID (UUID)")
    scenario_id: str = Field(..., description="Parent scenario ID")
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = Field(
        description="Run status"
    )
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    current_stage: Optional[str] = Field(
        None,
        description="Current workflow stage (INITIALIZATION, FOUNDATION, EVENT_GENERATION, etc.)",
    )
    current_year: Optional[int] = Field(None, description="Current simulation year")
    total_years: Optional[int] = Field(None, description="Total years to simulate")
    started_at: datetime = Field(..., description="Run start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Run completion timestamp")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class SimulationTelemetry(BaseModel):
    """WebSocket telemetry message format."""

    run_id: str = Field(..., description="Run ID")
    progress: int = Field(description="Progress percentage")
    current_stage: str = Field(description="Current workflow stage")
    current_year: int = Field(description="Current simulation year")
    total_years: int = Field(description="Total years to simulate")
    performance_metrics: PerformanceMetrics = Field(description="Performance metrics")
    recent_events: List[RecentEvent] = Field(
        default_factory=list, description="Recent events (last 20)"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SimulationResults(BaseModel):
    """Full simulation results."""

    scenario_id: str = Field(..., description="Scenario ID")
    run_id: str = Field(..., description="Run ID")

    # Summary metrics
    start_year: int
    end_year: int
    final_headcount: int
    total_growth_pct: float
    cagr: float
    participation_rate: float

    # Workforce progression
    workforce_progression: List[Dict[str, Any]] = Field(
        description="Year-by-year workforce breakdown"
    )

    # Event trends
    event_trends: Dict[str, List[int]] = Field(
        description="Event counts by type and year"
    )

    # Detailed metrics
    growth_analysis: Dict[str, float] = Field(description="Growth analysis metrics")


class RunRequest(BaseModel):
    """Request to start a simulation run."""

    resume_from_checkpoint: bool = Field(
        default=False, description="Resume from last checkpoint if available"
    )


class Artifact(BaseModel):
    """Simulation artifact file info."""

    name: str = Field(..., description="File name")
    type: Literal["excel", "yaml", "duckdb", "json", "text", "other"] = Field(
        description="Artifact type"
    )
    size_bytes: int = Field(description="File size in bytes")
    path: str = Field(description="Relative path to file")
    created_at: Optional[datetime] = Field(None, description="File creation time")


class RunSummary(BaseModel):
    """Summary of a simulation run for listing."""

    id: str = Field(..., description="Run ID")
    scenario_id: str = Field(..., description="Parent scenario ID")
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = Field(
        description="Run status"
    )
    started_at: datetime = Field(..., description="Run start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Run completion timestamp")
    duration_seconds: Optional[float] = Field(None, description="Total duration in seconds")

    # Summary metrics
    start_year: Optional[int] = Field(None, description="Simulation start year")
    end_year: Optional[int] = Field(None, description="Simulation end year")
    total_events: Optional[int] = Field(None, description="Total events generated")
    final_headcount: Optional[int] = Field(None, description="Final headcount")

    # Artifact count
    artifact_count: int = Field(default=0, description="Number of artifacts")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class RunDetails(BaseModel):
    """Detailed information about a simulation run."""

    id: str = Field(..., description="Run ID")
    scenario_id: str = Field(..., description="Parent scenario ID")
    scenario_name: str = Field(..., description="Scenario name")
    workspace_id: str = Field(..., description="Workspace ID")
    workspace_name: str = Field(..., description="Workspace name")
    status: Literal["pending", "running", "completed", "failed", "cancelled", "not_run"] = Field(
        description="Run status"
    )

    # Timing
    started_at: Optional[datetime] = Field(None, description="Run start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Run completion timestamp")
    duration_seconds: Optional[float] = Field(None, description="Total duration in seconds")

    # Simulation info
    start_year: Optional[int] = Field(None, description="Simulation start year")
    end_year: Optional[int] = Field(None, description="Simulation end year")
    total_years: Optional[int] = Field(None, description="Total years simulated")

    # Results summary
    final_headcount: Optional[int] = Field(None, description="Final headcount")
    total_events: Optional[int] = Field(None, description="Total events generated")
    participation_rate: Optional[float] = Field(None, description="DC plan participation rate")

    # Configuration snapshot
    config: Optional[Dict[str, Any]] = Field(None, description="Configuration used for run")

    # Artifacts
    artifacts: List[Artifact] = Field(default_factory=list, description="Output artifacts")

    # Error info
    error_message: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }
