"""Pydantic models for turnover rate analysis from census data."""

from typing import Optional

from pydantic import BaseModel, Field


class TurnoverAnalysisRequest(BaseModel):
    """Request for census-based turnover rate analysis."""

    file_path: str = Field(..., description="Path to census file (relative to workspace or absolute)")


class TurnoverRateSuggestion(BaseModel):
    """A suggested termination rate with supporting statistics."""

    rate: float = Field(..., description="Suggested termination rate as a decimal (e.g., 0.12 for 12%)")
    sample_size: int = Field(..., description="Number of employees in the group")
    terminated_count: int = Field(..., description="Number of terminated employees in the group")
    confidence: str = Field(..., description="Confidence level: 'high', 'moderate', or 'low'")


class TurnoverAnalysisResult(BaseModel):
    """Result from census-based turnover rate analysis."""

    experienced_rate: Optional[TurnoverRateSuggestion] = Field(
        None, description="Suggested termination rate for experienced employees (tenure >= 1 year)"
    )
    new_hire_rate: Optional[TurnoverRateSuggestion] = Field(
        None, description="Suggested termination rate for new hires (tenure < 1 year)"
    )
    total_employees: int = Field(..., description="Total employees analyzed")
    total_terminated: int = Field(..., description="Total terminated employees found")
    analysis_type: str = Field(..., description="Description of analysis performed")
    source_file: str = Field(..., description="Path to source census file")
    message: Optional[str] = Field(None, description="Informational message about the analysis")
