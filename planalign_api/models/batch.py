"""Batch processing models."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BatchScenario(BaseModel):
    """Status of a scenario within a batch."""

    scenario_id: str = Field(..., description="Scenario ID")
    name: str = Field(..., description="Scenario name")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        description="Scenario status"
    )
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class BatchCreate(BaseModel):
    """Request to create a batch job."""

    name: Optional[str] = Field(None, description="Batch job name")
    scenario_ids: Optional[List[str]] = Field(
        None, description="Specific scenarios to run (runs all if not provided)"
    )
    parallel: bool = Field(default=False, description="Run scenarios in parallel")
    export_format: Optional[Literal["excel", "csv"]] = Field(
        None, description="Export format for results"
    )


class BatchJob(BaseModel):
    """Batch job status model."""

    id: str = Field(..., description="Unique batch job ID")
    name: str = Field(..., description="Batch job name")
    workspace_id: str = Field(..., description="Parent workspace ID")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        description="Overall batch status"
    )
    submitted_at: datetime = Field(..., description="Submission timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    duration_seconds: Optional[float] = Field(None, description="Total duration")
    scenarios: List[BatchScenario] = Field(
        default_factory=list, description="Scenarios in this batch"
    )
    parallel: bool = Field(default=False, description="Whether running in parallel")
    export_format: Optional[str] = Field(None, description="Export format")
    results_path: Optional[str] = Field(None, description="Path to results directory")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class BatchHistory(BaseModel):
    """List of batch jobs for history view."""

    jobs: List[BatchJob] = Field(default_factory=list)
    total: int = Field(default=0)
