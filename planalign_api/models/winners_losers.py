"""Models for Winners & Losers comparison analysis."""

from typing import List

from pydantic import BaseModel, Field


class BandGroupResult(BaseModel):
    """Aggregated winner/loser/neutral counts for a single band."""

    band_label: str = Field(description="Age band or tenure band label")
    winners: int = Field(description="Count of winners in this band")
    losers: int = Field(description="Count of losers in this band")
    neutral: int = Field(description="Count of neutral in this band")
    total: int = Field(description="Total employees in this band")


class HeatmapCell(BaseModel):
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


class WinnersLosersResponse(BaseModel):
    """Complete Winners & Losers comparison response."""

    plan_a_scenario_id: str = Field(description="Plan A scenario ID")
    plan_b_scenario_id: str = Field(description="Plan B scenario ID")
    final_year: int = Field(description="Simulation year used for comparison")
    total_compared: int = Field(
        description="Employees present in both scenarios"
    )
    total_excluded: int = Field(
        description="Employees present in only one scenario"
    )
    total_winners: int = Field(description="Total winners")
    total_losers: int = Field(description="Total losers")
    total_neutral: int = Field(description="Total neutral")
    age_band_results: List[BandGroupResult] = Field(
        description="Breakdown by age band"
    )
    tenure_band_results: List[BandGroupResult] = Field(
        description="Breakdown by tenure band"
    )
    heatmap: List[HeatmapCell] = Field(
        description="Age × tenure grid cells"
    )
