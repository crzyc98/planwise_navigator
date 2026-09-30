"""Models for Winners & Losers comparison analysis."""

from typing import List, Literal

from pydantic import Field
from .base import APIModel


class DollarImpact(APIModel):
    """Currency rounded to cents per employee before aggregation (B minus A)."""

    total_increases: float = Field(description="Sum of positive employee deltas")
    total_decreases: float = Field(
        description="Sum of negative employee deltas (signed)"
    )
    net_contribution_change: float = Field(
        description="Increases plus signed decreases"
    )
    average_change: float = Field(
        description="Net change per compared employee, or zero"
    )


class ComparisonEvidence(APIModel):
    """Selected comparison evidence; legacy databases may have no run ID."""

    plan_a_scenario_id: str = Field(description="Plan A scenario ID")
    plan_b_scenario_id: str = Field(description="Plan B scenario ID")
    plan_a_run_id: str | None = Field(
        default=None, description="Selected Plan A run ID; null for legacy results"
    )
    plan_b_run_id: str | None = Field(
        default=None, description="Selected Plan B run ID; null for legacy results"
    )
    final_year: int = Field(
        description="Latest simulation year present in both snapshots"
    )


class EmployeeImpact(APIModel):
    """Read-only contribution detail without names or SSNs."""

    employee_id: str
    age_band: str
    tenure_band: str
    plan_a_amount: float
    plan_b_amount: float
    delta: float
    status: Literal["winner", "loser", "neutral"]


class EmployeeImpactPage(ComparisonEvidence, DollarImpact):
    """A stable employee-ID-ordered page and totals for the entire filtered group."""

    age_band: str | None = None
    tenure_band: str | None = None
    total: int
    offset: int
    limit: int
    employees: List[EmployeeImpact]


class BandGroupResult(DollarImpact):
    """Aggregated winner/loser/neutral counts for a single band."""

    band_label: str = Field(description="Age band or tenure band label")
    winners: int = Field(description="Count of winners in this band")
    losers: int = Field(description="Count of losers in this band")
    neutral: int = Field(description="Count of neutral in this band")
    total: int = Field(description="Total employees in this band")


class HeatmapCell(DollarImpact):
    """Single cell in the age × tenure heatmap grid."""

    age_band: str = Field(description="Row label (age band)")
    tenure_band: str = Field(description="Column label (tenure band)")
    winners: int = Field(description="Winner count in this cell")
    losers: int = Field(description="Loser count in this cell")
    neutral: int = Field(description="Neutral count in this cell")
    total: int = Field(description="Total employees in this cell")
    net_pct: float = Field(
        description="Net winner percentage: (winners - losers) / total * 100"
    )


class WinnersLosersResponse(ComparisonEvidence, DollarImpact):
    """Complete Winners & Losers comparison response."""

    plan_a_final_year: int = Field(
        description="Latest snapshot year available for Plan A"
    )
    plan_b_final_year: int = Field(
        description="Latest snapshot year available for Plan B"
    )
    total_compared: int = Field(description="Employees present in both scenarios")
    total_excluded: int = Field(description="Employees present in only one scenario")
    total_winners: int = Field(description="Total winners")
    total_losers: int = Field(description="Total losers")
    total_neutral: int = Field(description="Total neutral")
    age_band_results: List[BandGroupResult] = Field(description="Breakdown by age band")
    tenure_band_results: List[BandGroupResult] = Field(
        description="Breakdown by tenure band"
    )
    heatmap: List[HeatmapCell] = Field(description="Age × tenure grid cells")
