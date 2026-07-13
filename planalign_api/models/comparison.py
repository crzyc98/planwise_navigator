"""Comparison models for scenario analysis."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class WorkforceMetrics(BaseModel):
    """Workforce metrics for a single year."""

    headcount: int = Field(description="Total headcount")
    active: int = Field(description="Active employees")
    terminated: int = Field(description="Terminated employees")
    new_hires: int = Field(description="New hires")
    growth_pct: float = Field(description="Growth percentage")
    avg_compensation: float = Field(
        default=0.0, description="Average prorated compensation for active employees"
    )


class ConfigDelta(BaseModel):
    """One effective configuration difference between two scenarios."""

    path: str = Field(description="Stable dotted configuration path")
    a: Any = Field(default=None, description="Scenario A value")
    b: Any = Field(default=None, description="Scenario B value")
    status: Literal["changed", "only_a", "only_b"]


class ScenarioProvenance(BaseModel):
    """Latest available run provenance for a scenario."""

    available: bool
    config_fingerprint: Optional[str] = Field(
        default=None, min_length=12, max_length=12
    )
    random_seed: Optional[int] = None
    run_timestamp: Optional[datetime] = None
    drift_warning: bool = False
    drift_reasons: List[
        Literal[
            "current_config_mismatch",
            "current_seed_mismatch",
            "mixed_generation",
        ]
    ] = Field(default_factory=list)


class ConfigDiffResponse(BaseModel):
    """Effective configuration diff and provenance for exactly two scenarios."""

    scenario_a: str
    scenario_b: str
    scenario_names: Dict[str, str]
    differences: List[ConfigDelta]
    unchanged_count: int = Field(ge=0)
    provenance: Dict[str, ScenarioProvenance]
    seeds_match: Optional[bool]
    drift_warning: bool


class WorkforceComparisonYear(BaseModel):
    """Workforce comparison for a single year."""

    year: int = Field(description="Simulation year")
    values: Dict[str, WorkforceMetrics] = Field(description="Metrics by scenario ID")
    deltas: Dict[str, WorkforceMetrics] = Field(
        description="Delta from baseline by scenario ID"
    )


class EventComparisonMetric(BaseModel):
    """Event comparison for a single metric."""

    metric: str = Field(description="Metric name (hires, terminations, etc.)")
    year: int = Field(description="Year")
    baseline: int = Field(description="Baseline value")
    scenarios: Dict[str, int] = Field(description="Values by scenario ID")
    deltas: Dict[str, int] = Field(description="Delta from baseline")
    delta_pcts: Dict[str, float] = Field(description="Delta percentage")


class DeltaValue(BaseModel):
    """Delta calculation for a summary metric."""

    baseline: float = Field(description="Baseline value")
    scenarios: Dict[str, float] = Field(description="Values by scenario ID")
    deltas: Dict[str, float] = Field(description="Absolute deltas")
    delta_pcts: Dict[str, float] = Field(description="Percentage deltas")


class DCPlanMetrics(BaseModel):
    """DC plan metrics for a single scenario in a single year."""

    participation_rate: float = Field(default=0.0, description="Participation rate (%)")
    avg_deferral_rate: float = Field(default=0.0, description="Average deferral rate")
    total_employee_contributions: float = Field(
        default=0.0, description="Total employee contributions"
    )
    total_employer_match: float = Field(default=0.0, description="Total employer match")
    total_employer_core: float = Field(default=0.0, description="Total employer core")
    total_employer_cost: float = Field(
        default=0.0, description="Total employer cost (match + core)"
    )
    employer_cost_rate: float = Field(default=0.0, description="Employer cost rate (%)")
    participant_count: int = Field(
        default=0, description="Number of enrolled employees"
    )


class DCPlanComparisonYear(BaseModel):
    """DC plan comparison for a single year."""

    year: int = Field(description="Simulation year")
    values: Dict[str, DCPlanMetrics] = Field(description="Metrics by scenario ID")
    deltas: Dict[str, DCPlanMetrics] = Field(
        description="Delta from baseline by scenario ID"
    )


class ComparisonResponse(BaseModel):
    """Full comparison response."""

    scenarios: List[str] = Field(description="List of scenario IDs in comparison")
    scenario_names: Dict[str, str] = Field(description="Scenario ID to name mapping")
    baseline_scenario: str = Field(description="Baseline scenario ID")

    # Workforce comparison by year
    workforce_comparison: List[WorkforceComparisonYear] = Field(
        description="Year-by-year workforce comparison"
    )

    # Event comparison
    event_comparison: List[EventComparisonMetric] = Field(
        description="Event metrics comparison"
    )

    # DC plan comparison by year
    dc_plan_comparison: List[DCPlanComparisonYear] = Field(
        default_factory=list,
        description="Year-by-year DC plan comparison",
    )

    # Summary deltas
    summary_deltas: Dict[str, DeltaValue] = Field(
        description="Summary metric deltas (final_headcount, total_growth, etc.)"
    )
