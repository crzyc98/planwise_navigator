"""Scenario models."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ScenarioCreate(BaseModel):
    """Request model for creating a scenario."""

    name: str = Field(..., min_length=1, max_length=100, description="Scenario name")
    description: Optional[str] = Field(None, max_length=500, description="Scenario description")
    config_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration overrides (merged with workspace base config)",
    )


class ScenarioUpdate(BaseModel):
    """Request model for updating a scenario."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    config_overrides: Optional[Dict[str, Any]] = None


class ScenarioResultsSummary(BaseModel):
    """Summary of scenario results."""

    final_headcount: int = Field(description="Final year headcount")
    total_growth_pct: float = Field(description="Total growth percentage")
    cagr: float = Field(description="Compound annual growth rate")
    participation_rate: float = Field(description="DC plan participation rate")
    total_events: int = Field(description="Total events generated")


class Scenario(BaseModel):
    """Full scenario model."""

    id: str = Field(..., description="Unique scenario ID (UUID)")
    workspace_id: str = Field(..., description="Parent workspace ID")
    name: str = Field(..., description="Scenario name")
    description: Optional[str] = Field(None, description="Scenario description")
    config_overrides: Dict[str, Any] = Field(
        default_factory=dict, description="Configuration overrides"
    )
    status: Literal["not_run", "queued", "running", "completed", "failed"] = Field(
        default="not_run", description="Scenario execution status"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    last_run_at: Optional[datetime] = Field(None, description="Last run timestamp")
    last_run_id: Optional[str] = Field(None, description="Last run ID")
    results_summary: Optional[ScenarioResultsSummary] = Field(
        None, description="Summary of last run results"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class ScenarioConfig(BaseModel):
    """Full merged configuration for a scenario."""

    # Simulation settings
    start_year: int = Field(description="Simulation start year")
    end_year: int = Field(description="Simulation end year")
    random_seed: int = Field(description="Random seed for reproducibility")
    target_growth_rate: float = Field(description="Target annual growth rate")

    # Compensation
    cola_rate: float = Field(description="Cost of living adjustment rate")
    merit_budget: float = Field(description="Merit increase budget")
    promotion_increase: float = Field(description="Average promotion increase")

    # Workforce
    total_termination_rate: float = Field(description="Annual termination rate")
    new_hire_termination_rate: float = Field(description="New hire termination rate")

    # Enrollment
    auto_enrollment_enabled: bool = Field(description="Auto-enrollment enabled")
    default_deferral_rate: float = Field(description="Default deferral rate")

    # Employer match
    match_formula: str = Field(description="Match formula type")
    match_rate: float = Field(description="Match rate")
    match_limit: float = Field(description="Match limit as % of salary")

    # Advanced
    engine: str = Field(description="Execution engine (polars/sql)")
    multithreading_enabled: bool = Field(description="Multithreading enabled")

    # Full config for reference
    full_config: Dict[str, Any] = Field(description="Complete merged configuration")
