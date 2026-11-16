"""Request model for the Cost Comparison summary workbook.

The Cost Comparison page derives every figure it shows (totals, differences
from the anchor, cost rates, forfeiture offsets and net cost) in
``planalign_studio/components/costSummary.ts``. The page renders those figures
and sends the same object here, so the workbook has no second implementation
of any derived column. The server adds names, view labels and run provenance.
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import Field

from ..constants import MAX_SCENARIO_COMPARISON
from .base import APIModel
from .employer_cost import ForfeiturePolicy
from .vesting import VestingScheduleType

# Generous bounds: a comparison is at most a few dozen years.
MAX_SUMMARY_YEARS = 100
MAX_NOTE_LENGTH = 500

Figure = Optional[Annotated[float, Field(allow_inf_nan=False)]]
Note = Annotated[str, Field(max_length=MAX_NOTE_LENGTH)]

SummaryField = Literal[
    "employer_cost",
    "employer_cost_vs_anchor",
    "cost_pct_of_capped_pay",
    "cost_pct_vs_anchor_pp",
    "employer_match",
    "employer_core",
    "forfeiture_offset",
    "reallocated_to_participants",
    "net_employer_cost",
    "net_employer_cost_vs_anchor",
    "total_compensation",
    "total_compensation_vs_anchor",
]


class CostSummaryFigures(APIModel):
    """One row of figures. Null means unavailable; ``notes`` says why."""

    employer_cost: Figure = Field(
        None, description="Employer match + core (grandfathered when selected)"
    )
    employer_cost_vs_anchor: Figure = None
    cost_pct_of_capped_pay: Figure = Field(
        None,
        description="Employer cost / IRS-capped prorated pay, in percent (4.5 = 4.5%)",
    )
    cost_pct_vs_anchor_pp: Figure = Field(
        None, description="Difference from the anchor, in percentage points"
    )
    employer_match: Figure = None
    employer_core: Figure = None
    forfeiture_offset: Figure = None
    reallocated_to_participants: Figure = None
    net_employer_cost: Figure = None
    net_employer_cost_vs_anchor: Figure = None
    total_compensation: Figure = None
    total_compensation_vs_anchor: Figure = None
    notes: Dict[SummaryField, Note] = Field(
        default_factory=dict,
        description="Why a figure is blank, keyed by field name",
    )


class CostSummaryYear(CostSummaryFigures):
    year: int = Field(..., ge=1900, le=2200)
    has_data: bool = Field(
        True, description="False when the selected cohort has no employees this year"
    )


class CostSummaryScenario(APIModel):
    scenario_id: str = Field(..., min_length=1, max_length=200)
    run_id: Optional[str] = Field(
        None,
        max_length=200,
        description="Selected run the page loaded; a newer run makes the export stale",
    )
    years: List[CostSummaryYear] = Field(..., max_length=MAX_SUMMARY_YEARS)
    totals: CostSummaryFigures


class CostSummaryView(APIModel):
    """The page settings the figures were derived under."""

    anchor_scenario_id: str = Field(..., min_length=1, max_length=200)
    cohort: Literal["all", "new_hires", "baseline"] = "all"
    first_simulation_year: Optional[int] = Field(None, ge=1900, le=2200)
    cost_view: Literal["gross", "net"] = "gross"
    breakdown: Literal["total", "split"] = "total"
    vesting_schedule: Optional[VestingScheduleType] = None
    forfeiture_policy: Optional[ForfeiturePolicy] = None
    grandfather_cutoff_year: Optional[int] = Field(
        None,
        ge=1900,
        le=2200,
        description="Set when existing employees are grandfathered on the anchor design",
    )


class CostSummaryExportRequest(APIModel):
    view: CostSummaryView
    scenarios: List[CostSummaryScenario] = Field(
        ..., min_length=1, max_length=MAX_SCENARIO_COMPARISON
    )
