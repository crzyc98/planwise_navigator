"""Comparison models for scenario analysis."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkforceMetrics(BaseModel):
    """Workforce metrics for a single year."""

    headcount: int = Field(description="Total headcount")
    active: int = Field(description="Active employees")
    terminated: int = Field(description="Terminated employees")
    new_hires: int = Field(description="New hires")
    growth_pct: float = Field(description="Growth percentage")


class WorkforceComparisonYear(BaseModel):
    """Workforce comparison for a single year."""

    year: int = Field(description="Simulation year")
    values: Dict[str, WorkforceMetrics] = Field(
        description="Metrics by scenario ID"
    )
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

    # Summary deltas
    summary_deltas: Dict[str, DeltaValue] = Field(
        description="Summary metric deltas (final_headcount, total_growth, etc.)"
    )
