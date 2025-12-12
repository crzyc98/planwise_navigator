"""Pydantic models for band configuration management.

This module defines the data models for age and tenure band configurations
used by the PlanAlign simulation engine.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Band(BaseModel):
    """A single band definition representing a range segment for age or tenure grouping."""

    band_id: int = Field(..., ge=1, description="Unique identifier for the band")
    band_label: str = Field(..., max_length=50, description="Human-readable label (e.g., '25-34', '< 25')")
    min_value: int = Field(..., ge=0, description="Lower bound (inclusive)")
    max_value: int = Field(..., gt=0, description="Upper bound (exclusive)")
    display_order: int = Field(..., ge=1, description="Sort order for UI display")

    @field_validator("max_value")
    @classmethod
    def max_greater_than_min(cls, v: int, info) -> int:
        """Validate that max_value is greater than min_value."""
        if "min_value" in info.data and v <= info.data["min_value"]:
            raise ValueError("max_value must be greater than min_value")
        return v


class BandConfig(BaseModel):
    """Container for all band configurations (age and tenure)."""

    age_bands: List[Band] = Field(..., description="Age band definitions")
    tenure_bands: List[Band] = Field(..., description="Tenure band definitions")


class BandValidationError(BaseModel):
    """A validation error for band configurations."""

    band_type: Literal["age", "tenure"] = Field(..., description="Type of bands with the error")
    error_type: Literal["gap", "overlap", "invalid_range", "coverage"] = Field(
        ..., description="Type of validation error"
    )
    message: str = Field(..., description="Human-readable error message")
    band_ids: List[int] = Field(default_factory=list, description="IDs of bands involved in the error")


class BandSaveRequest(BaseModel):
    """Request payload for saving band configurations."""

    age_bands: List[Band] = Field(..., description="Updated age band definitions")
    tenure_bands: List[Band] = Field(..., description="Updated tenure band definitions")


class BandSaveResponse(BaseModel):
    """Response after saving band configurations."""

    success: bool = Field(..., description="Whether save was successful")
    validation_errors: List[BandValidationError] = Field(
        default_factory=list, description="Validation errors (if save failed)"
    )
    message: str = Field(..., description="Status message")


class BandAnalysisRequest(BaseModel):
    """Request for census-based band analysis."""

    file_path: str = Field(..., description="Path to census file (relative to workspace or absolute)")


class DistributionStats(BaseModel):
    """Statistics from census distribution analysis."""

    total_employees: int = Field(..., description="Number of employees analyzed")
    min_value: int = Field(..., description="Minimum value in distribution")
    max_value: int = Field(..., description="Maximum value in distribution")
    median_value: float = Field(..., description="Median value")
    mean_value: float = Field(..., description="Mean value")
    percentiles: dict[int, float] = Field(
        default_factory=dict,
        description="Percentile values keyed by percentile (10, 25, 50, 75, 90)",
    )


class BandAnalysisResult(BaseModel):
    """Result from census-based band analysis."""

    suggested_bands: List[Band] = Field(..., description="Suggested band definitions based on analysis")
    distribution_stats: DistributionStats = Field(..., description="Statistics about the analyzed distribution")
    analysis_type: str = Field(..., description="Description of analysis performed (e.g., 'Recent hires from 2024')")
    source_file: str = Field(..., description="Path to source census file")
