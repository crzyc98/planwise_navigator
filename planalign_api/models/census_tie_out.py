"""Pydantic models for the census tie-out (census year vs first simulated year).

Each row compares one metric under one definition on both sides, so the
Studio panel and the report can show the same rows and wording.
"""

from datetime import date
from typing import List, Literal, Optional

from pydantic import Field

from .base import APIModel

TieOutMetric = Literal[
    "active_headcount",
    "eligible_count",
    "participation_rate",
    "average_deferral_rate",
    "total_pay",
    "employer_match",
    "employer_core",
]
TieOutUnit = Literal["count", "rate", "dollars"]
TieOutStatus = Literal["ties", "gap", "not_in_census"]


class CensusTieOutRow(APIModel):
    """One metric: census value, first-simulated-year value and how they compare."""

    metric: TieOutMetric
    label: str
    unit: TieOutUnit = Field(description="Rates are fractions (0.06 = 6%).")
    definition: str = Field(description="The definition applied to both sides.")
    census_value: Optional[float] = Field(
        description="Census-year value; null when the census lacks the data."
    )
    simulated_value: float
    expected_value: Optional[float] = Field(
        description="Census value carried forward by the configured growth and raises."
    )
    difference: Optional[float] = Field(
        description="Simulated minus census, in the row's unit."
    )
    relative_difference: Optional[float] = Field(
        description=(
            "Simulated over census minus 1, for counts and dollars with a "
            "non-zero census value; null for rates."
        )
    )
    tolerance: Optional[float] = Field(
        description=(
            "The row ties when the simulated value is within this distance of "
            "the expected value (same unit)."
        )
    )
    status: TieOutStatus
    message: str = Field(description="What the comparison shows and what to check.")


class CensusTieOut(APIModel):
    """Census tie-out for one scenario's selected run."""

    scenario_id: str
    scenario_name: str
    available: bool
    unavailable_reason: Optional[str] = None
    run_id: Optional[str] = None
    census_file: Optional[str] = Field(
        default=None, description="Census file name recorded in the run's config."
    )
    census_year: Optional[int] = None
    census_as_of_date: Optional[date] = Field(
        default=None, description="End of the census plan year."
    )
    first_simulated_year: Optional[int] = None
    growth_rate: Optional[float] = Field(
        default=None, description="Configured annual headcount growth (fraction)."
    )
    raise_rate: Optional[float] = Field(
        default=None, description="Configured annual COLA plus merit (fraction)."
    )
    source_note: Optional[str] = Field(
        default=None,
        description=(
            "One sentence naming the census file, census year and first simulated "
            "year, and when the comparison is meaningful. Shown as is by the "
            "Studio panel and the report."
        ),
    )
    rows: List[CensusTieOutRow] = Field(default_factory=list)
