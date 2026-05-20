"""Pydantic models for opt-out rate analysis from census data."""

from typing import Optional

from pydantic import BaseModel, Field


class OptOutRateAnalysisRequest(BaseModel):
    """Request for census-based opt-out rate analysis."""

    file_path: str = Field(..., description="Path to census file (relative to workspace or absolute)")
    lookback_years: int = Field(
        default=3,
        ge=1,
        le=50,
        description="Only include employees hired within this many years of the most recent hire in the census",
    )


class OptOutRateAnalysisResult(BaseModel):
    """Result from census-based opt-out rate analysis."""

    suggested_rate: Optional[float] = Field(
        None,
        description="Suggested opt-out rate as decimal (0.0–1.0). None if no eligible employees in the lookback window.",
    )
    eligible_count: int = Field(
        ..., description="Total eligible active employees within the lookback tenure window"
    )
    non_participant_count: int = Field(
        ..., description="Employees within the window with deferral_rate = 0 or NULL"
    )
    total_eligible_in_census: int = Field(
        ..., description="Total eligible active employees in the entire census (pre-lookback filter)"
    )
    excluded_null_tenure: int = Field(
        ..., description="Employees excluded because hire_date was missing or NULL"
    )
    lookback_years: int = Field(..., description="Echoed back from the request")
    hire_date_column_used: str = Field(
        ..., description="The census column name detected for hire date"
    )
    analysis_type: str = Field(..., description="Human-readable description of the analysis performed")
    source_file: str = Field(..., description="Path to source census file")
    message: Optional[str] = Field(None, description="Informational or warning message")
