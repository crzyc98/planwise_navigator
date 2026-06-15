"""Simulation run and telemetry models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SimulationLogLine(BaseModel):
    """A single parsed log entry from a simulation run."""

    sequence: int = Field(
        ..., ge=1, description="1-based line number within the log file"
    )
    timestamp: datetime = Field(
        ..., description="UTC timestamp when the line was produced"
    )
    severity: Literal["INFO", "WARNING", "ERROR"] = Field(
        ..., description="Severity level"
    )
    message: str = Field(..., description="Log message text")


class LogPage(BaseModel):
    """Paginated log lines for the log viewer endpoint."""

    run_id: str = Field(..., description="The run these log lines belong to")
    lines: List[SimulationLogLine] = Field(default_factory=list)
    total_lines: int = Field(..., description="Total lines in the log file")
    page: int = Field(..., ge=1, description="Current page number (1-based)")
    page_size: int = Field(..., ge=1, description="Lines per page requested")
    has_more: bool = Field(..., description="True if additional pages exist")
    is_running: bool = Field(..., description="True if simulation is still in progress")
    log_available: bool = Field(..., description="False if no log file exists yet")


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
    completed_at: Optional[datetime] = Field(
        None, description="Run completion timestamp"
    )
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
    recent_log_lines: List[SimulationLogLine] = Field(
        default_factory=list, description="Recent log lines (rolling window of 50)"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryMilestone(BaseModel):
    """A timestamped record of a significant run occurrence (feature 094)."""

    sequence: int = Field(
        ..., ge=1, description="Monotonic per run; client ordering key"
    )
    timestamp: datetime = Field(..., description="When the milestone occurred (UTC)")
    kind: Literal[
        "run_started",
        "stage_started",
        "stage_completed",
        "year_completed",
        "warning",
        "error",
        "terminal",
    ] = Field(..., description="Milestone discriminator")
    severity: Literal["info", "warning", "error"] = Field(
        "info", description="Drives activity feed styling"
    )
    year: Optional[int] = Field(None, description="Simulation year, when applicable")
    stage: Optional[str] = Field(None, description="Workflow stage, when applicable")
    message: str = Field(..., description="Human-readable feed text")
    detail: Optional[Dict[str, Any]] = Field(
        None, description="Structured payload (e.g. year counts + duration)"
    )


class EventTypeCounts(BaseModel):
    """Cumulative and per-year event counts; exact at year boundaries only."""

    by_type: Dict[str, int] = Field(default_factory=dict)
    by_year: Dict[int, Dict[str, int]] = Field(default_factory=dict)
    total: int = Field(0, ge=0)
    as_of_year: Optional[int] = Field(
        None, description="Last fully counted simulation year"
    )


class PerformanceSample(BaseModel):
    """One trend-chart data point."""

    timestamp: datetime
    elapsed_seconds: float = Field(0.0, ge=0)
    events_per_second: float = Field(0.0, ge=0)
    memory_mb: float = Field(0.0, ge=0)


class RunTelemetrySnapshot(BaseModel):
    """Full restorable run state — WS `snapshot` body and REST telemetry response."""

    run_id: str
    scenario_id: str = ""
    status: Literal[
        "pending", "running", "completed", "failed", "cancelled"
    ] = "running"
    progress: int = Field(0, ge=0, le=100)
    current_stage: str = "INITIALIZATION"
    current_year: int = 0
    total_years: int = 0
    start_year: int = 0
    performance_metrics: PerformanceMetrics
    event_counts: EventTypeCounts = Field(default_factory=EventTypeCounts)
    milestones: List[TelemetryMilestone] = Field(default_factory=list)
    performance_samples: List[PerformanceSample] = Field(default_factory=list)
    last_update_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SnapshotMessage(BaseModel):
    """WS envelope: full state, sent once per (re)connect before any delta."""

    type: Literal["snapshot"] = "snapshot"
    data: RunTelemetrySnapshot


class RunTelemetryUpdate(BaseModel):
    """Incremental live state: snapshot fields minus history lists."""

    run_id: str
    scenario_id: str = ""
    status: Literal[
        "pending", "running", "completed", "failed", "cancelled"
    ] = "running"
    progress: int = Field(0, ge=0, le=100)
    current_stage: str = "INITIALIZATION"
    current_year: int = 0
    total_years: int = 0
    start_year: int = 0
    performance_metrics: PerformanceMetrics
    event_counts: EventTypeCounts = Field(default_factory=EventTypeCounts)
    last_update_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UpdateMessage(BaseModel):
    """WS envelope: incremental live state (throttled to >=1s)."""

    type: Literal["update"] = "update"
    data: RunTelemetryUpdate


class MilestoneMessage(BaseModel):
    """WS envelope: one appended activity-feed entry."""

    type: Literal["milestone"] = "milestone"
    data: TelemetryMilestone


class RunTelemetryResponse(BaseModel):
    """REST snapshot endpoint response (contracts/rest-telemetry-snapshot.md)."""

    run: Dict[str, Any] = Field(
        ..., description="run_id / status / error_message summary"
    )
    telemetry: Optional[RunTelemetrySnapshot] = Field(
        None, description="Null when no in-memory state exists"
    )


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

    # E093: Compensation breakdown by employment status
    compensation_by_status: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Compensation breakdown by year and employment status",
    )

    # CAGR metrics for key workforce measures
    cagr_metrics: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="CAGR calculations for headcount, total compensation, and average compensation",
    )


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
    completed_at: Optional[datetime] = Field(
        None, description="Run completion timestamp"
    )
    duration_seconds: Optional[float] = Field(
        None, description="Total duration in seconds"
    )

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
    status: Literal[
        "pending", "running", "completed", "failed", "cancelled", "not_run"
    ] = Field(description="Run status")

    # Timing
    started_at: Optional[datetime] = Field(None, description="Run start timestamp")
    completed_at: Optional[datetime] = Field(
        None, description="Run completion timestamp"
    )
    duration_seconds: Optional[float] = Field(
        None, description="Total duration in seconds"
    )

    # Simulation info
    start_year: Optional[int] = Field(None, description="Simulation start year")
    end_year: Optional[int] = Field(None, description="Simulation end year")
    total_years: Optional[int] = Field(None, description="Total years simulated")

    # Results summary
    final_headcount: Optional[int] = Field(None, description="Final headcount")
    total_events: Optional[int] = Field(None, description="Total events generated")
    participation_rate: Optional[float] = Field(
        None, description="DC plan participation rate"
    )

    # Configuration snapshot
    config: Optional[Dict[str, Any]] = Field(
        None, description="Configuration used for run"
    )

    # Artifacts
    artifacts: List[Artifact] = Field(
        default_factory=list, description="Output artifacts"
    )

    # Error info
    error_message: Optional[str] = Field(None, description="Error message if failed")

    # E087: Storage location info
    storage_path: Optional[str] = Field(
        None, description="Scenario storage directory path"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }
