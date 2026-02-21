"""File upload and validation models."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class StructuredWarning(BaseModel):
    """A structured validation warning about a census column."""

    field_name: str = Field(..., description="Expected census column name")
    severity: Literal["critical", "optional", "info"] = Field(
        ..., description="Warning severity tier"
    )
    warning_type: Literal["missing", "alias_found", "auto_mapped"] = Field(
        ..., description="Type of warning"
    )
    impact_description: str = Field(
        ..., description="Human-readable simulation impact"
    )
    detected_alias: Optional[str] = Field(
        None, description="Alias column name found in file"
    )
    suggested_action: str = Field(..., description="Recommended user action")


class DataQualitySample(BaseModel):
    """A sample row exhibiting a data quality issue."""

    row_number: int = Field(..., description="1-based row number")
    value: Optional[str] = Field(None, description="Problematic value (None if null)")


class DataQualityWarning(BaseModel):
    """A row-level data quality warning for a census field."""

    field_name: str = Field(..., description="Column name with the issue")
    check_type: Literal[
        "null_or_empty", "unparseable_date", "mixed_date_formats", "negative_value"
    ] = Field(..., description="Type of quality check that found the issue")
    severity: Literal["error", "warning", "info"] = Field(
        ..., description="Issue severity"
    )
    affected_count: int = Field(..., description="Number of rows affected")
    total_count: int = Field(..., description="Total number of rows checked")
    affected_percentage: float = Field(
        ..., description="Percentage of rows affected (0-100)"
    )
    message: str = Field(..., description="Human-readable description")
    samples: List[DataQualitySample] = Field(
        default_factory=list, description="Up to 5 sample rows"
    )
    suggested_action: str = Field(..., description="Recommended fix")


class FileUploadResponse(BaseModel):
    """Response after successful file upload."""

    success: bool = Field(..., description="Whether upload was successful")
    file_path: str = Field(..., description="Relative path to uploaded file within workspace")
    file_name: str = Field(..., description="Original filename")
    file_size_bytes: int = Field(..., description="File size in bytes")
    row_count: int = Field(..., description="Number of rows in the file")
    columns: List[str] = Field(..., description="List of column names")
    upload_timestamp: datetime = Field(..., description="When the file was uploaded")
    validation_warnings: List[str] = Field(
        default_factory=list, description="Non-fatal validation warnings"
    )
    structured_warnings: List[StructuredWarning] = Field(
        default_factory=list,
        description="Structured validation warnings with severity and impact",
    )
    data_quality_warnings: List[DataQualityWarning] = Field(
        default_factory=list,
        description="Row-level data quality warnings",
    )
    column_renames: List[dict] = Field(
        default_factory=list,
        description="Columns that were auto-renamed from aliases to canonical names",
    )
    original_filename: Optional[str] = Field(
        None, description="Original uploaded filename before normalization"
    )


class FileValidationRequest(BaseModel):
    """Request to validate a file path."""

    file_path: str = Field(..., description="File path to validate (relative or absolute)")


class CompensationAnalysisRequest(BaseModel):
    """Request for compensation analysis with lookback option."""

    file_path: str = Field(..., description="File path to census file (relative or absolute)")
    lookback_years: int = Field(
        default=4,
        ge=0,
        le=20,
        description="Number of years to look back for recent hires (0 = all employees). Default: 4 years"
    )


class FileValidationResponse(BaseModel):
    """Response from file path validation."""

    valid: bool = Field(..., description="Whether the file is valid and readable")
    file_path: str = Field(..., description="The validated file path")
    exists: bool = Field(..., description="Whether the file exists")
    readable: bool = Field(default=False, description="Whether the file can be read")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    row_count: Optional[int] = Field(None, description="Number of rows in the file")
    columns: Optional[List[str]] = Field(None, description="List of column names")
    last_modified: Optional[datetime] = Field(None, description="Last modification timestamp")
    error_message: Optional[str] = Field(None, description="Error message if validation failed")
    validation_warnings: List[str] = Field(
        default_factory=list, description="Non-fatal validation warnings"
    )
    structured_warnings: List[StructuredWarning] = Field(
        default_factory=list,
        description="Structured validation warnings with severity and impact",
    )
    data_quality_warnings: List[DataQualityWarning] = Field(
        default_factory=list,
        description="Row-level data quality warnings",
    )


class CompensationSolverRequest(BaseModel):
    """Request to solve for compensation parameters."""

    file_path: Optional[str] = Field(
        None,
        description="Path to census file for workforce analysis. If not provided, uses defaults.",
    )
    target_growth_rate: float = Field(
        ...,
        ge=-0.10,  # Allow negative targets (declining avg comp)
        le=0.20,
        description="Target average compensation growth rate as decimal (e.g., 0.02 for 2%)",
    )
    promotion_increase: Optional[float] = Field(
        None,
        ge=0.0,
        le=0.50,
        description="Lock promotion increase at this value (as decimal). If not provided, uses 12.5%.",
    )
    cola_to_merit_ratio: Optional[float] = Field(
        None,
        ge=0.1,
        le=2.0,
        description="Ratio of COLA to merit (e.g., 0.6 means COLA is 60% of merit). Default: 0.6",
    )
    # Workforce dynamics parameters
    turnover_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=0.50,
        description="Annual turnover rate as decimal (e.g., 0.15 for 15%). Default: 15%",
    )
    workforce_growth_rate: Optional[float] = Field(
        None,
        ge=-0.20,
        le=0.50,
        description="Annual workforce growth rate as decimal (e.g., 0.03 for 3%). Default: 3%",
    )
    new_hire_comp_ratio: Optional[float] = Field(
        None,
        ge=0.50,
        le=1.50,
        description="New hire avg compensation as ratio of current avg (e.g., 0.85 = 85%). Default: 85%",
    )


class LevelDistributionResponse(BaseModel):
    """Distribution info for a job level."""

    level: int = Field(..., description="Job level ID")
    name: str = Field(..., description="Level name")
    headcount: int = Field(..., description="Number of employees at this level")
    percentage: float = Field(..., description="Percentage of workforce")
    avg_compensation: float = Field(..., description="Average compensation at this level")
    promotion_rate: float = Field(..., description="Expected annual promotion rate")


class CompensationSolverResponse(BaseModel):
    """Response from compensation solver."""

    # Target
    target_growth_rate: float = Field(..., description="Target growth rate as percentage (e.g., 2.0)")

    # Solved parameters (as percentages)
    cola_rate: float = Field(..., description="COLA rate as percentage (e.g., 2.0 for 2%)")
    merit_budget: float = Field(..., description="Merit budget as percentage")
    promotion_increase: float = Field(..., description="Promotion increase as percentage")
    promotion_budget: float = Field(..., description="Promotion budget as percentage")

    # Validation
    achieved_growth_rate: float = Field(..., description="Actual achieved growth rate as percentage")
    growth_gap: float = Field(..., description="Difference from target as percentage")

    # Breakdown - how each factor contributes to average comp growth
    cola_contribution: float = Field(..., description="Growth contribution from COLA (stayer raises)")
    merit_contribution: float = Field(..., description="Growth contribution from merit (stayer raises)")
    promo_contribution: float = Field(..., description="Growth contribution from promotions (stayer raises)")
    turnover_contribution: float = Field(
        default=0.0,
        description="Growth contribution from turnover/new hires (usually negative if new hires paid less)"
    )

    # Context
    total_headcount: int = Field(..., description="Total workforce size")
    avg_compensation: float = Field(..., description="Average compensation")
    weighted_promotion_rate: float = Field(..., description="Weighted promotion rate as percentage")

    # Workforce dynamics used in calculation
    turnover_rate: float = Field(default=0.0, description="Annual turnover rate as percentage")
    workforce_growth_rate: float = Field(default=0.0, description="Annual workforce growth rate as percentage")
    new_hire_comp_ratio: float = Field(default=0.0, description="New hire comp as percentage of avg")

    # Recommendation for new hire compensation
    recommended_new_hire_ratio: float = Field(
        default=0.0,
        description="Recommended new hire comp as % of avg to achieve target with standard raises"
    )
    recommended_scale_factor: float = Field(
        default=0.0,
        description="Scale factor to apply to census-derived ranges (e.g., 1.5 = 1.5x)"
    )

    # Level distribution (optional, if census was analyzed)
    level_distribution: Optional[List[LevelDistributionResponse]] = Field(
        None, description="Distribution across job levels"
    )

    # Warnings
    warnings: List[str] = Field(default_factory=list, description="Warnings or notes")
