"""Pydantic models for voluntary-enrollment deferral segment analysis."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class DeferralSegmentAnalysisRequest(BaseModel):
    """Request for census-based deferral segment analysis."""

    file_path: str = Field(
        ..., description="Path to census file (relative to workspace or absolute)"
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description="Date ages are measured at. Inferred from the census when omitted.",
    )


class DeferralSegment(BaseModel):
    """Observed deferral behavior for one age x income segment."""

    segment: str = Field(
        ...,
        description="Segment key, '{age_segment}_{income_segment}' (e.g. 'young_low')",
    )
    age_segment: str = Field(
        ..., description="One of young, mid_career, mature, senior"
    )
    income_segment: str = Field(
        ..., description="One of low, moderate, high, executive"
    )
    average_deferral_rate: Optional[float] = Field(
        None,
        description=(
            "Mean deferral rate as a decimal among participants in this segment. "
            "None when the segment has no participants, in which case the segment "
            "carries no suggestion and should keep its configured value."
        ),
    )
    participant_count: int = Field(
        ..., description="Employees in this segment with a deferral rate above zero"
    )
    employee_count: int = Field(
        ...,
        description="All employees in this segment, including non-participants",
    )
    low_confidence: bool = Field(
        ...,
        description="True when the participant count is too small to be reliable",
    )


class DeferralSegmentAnalysisResult(BaseModel):
    """Result from census-based deferral segment analysis."""

    segments: List[DeferralSegment] = Field(
        ...,
        description=(
            "One entry per age x income segment that has at least one employee. "
            "Segments absent from the census are omitted."
        ),
    )
    total_employees_analyzed: int = Field(
        ..., description="Employees with usable age, compensation, and deferral values"
    )
    total_participants: int = Field(
        ..., description="Analyzed employees with a deferral rate above zero"
    )
    overall_average_deferral_rate: Optional[float] = Field(
        None, description="Mean deferral rate across all participants, as a decimal"
    )
    excluded_count: int = Field(
        ...,
        description=(
            "Employees dropped for a missing or unusable age, compensation, or "
            "deferral value, including deferral rates outside the 0-1 decimal range"
        ),
    )
    as_of_date: date = Field(..., description="Date ages were measured at")
    as_of_date_source: str = Field(
        ..., description="'provided' or 'inferred' from the census"
    )
    low_confidence_threshold: int = Field(
        ...,
        description="Participant count below which a segment is flagged low confidence",
    )
    source_file: str = Field(..., description="Path to source census file")
    message: Optional[str] = Field(None, description="Informational or warning message")
