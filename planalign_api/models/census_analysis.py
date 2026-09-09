"""Pydantic models for pre-simulation census analysis.

Powers the Census Analysis page: participation, savings-rate, and cost-proxy
metrics computed directly from the uploaded/staged census (as-of a resolved
date), independent of any simulation run.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class CensusAnalysisRequest(BaseModel):
    """Request for census-based pre-simulation analysis."""

    file_path: str = Field(
        ..., description="Path to census file (relative to workspace or absolute)"
    )
    as_of_date: Optional[date] = Field(
        default=None,
        description="Date the census is evaluated as-of. Inferred from the census when omitted.",
    )


class CensusMetrics(BaseModel):
    """Participation, savings-rate, and cost metrics for one population slice."""

    employee_count: int = Field(..., description="Employees in this slice")
    eligible_count: int = Field(
        ..., description="Employees in this slice treated as plan-eligible"
    )
    enrolled_count: int = Field(
        ..., description="Eligible employees with a deferral rate above zero"
    )
    participation_rate: Optional[float] = Field(
        None,
        description="enrolled_count / eligible_count, as a decimal. None if no eligible employees.",
    )
    zero_deferral_count: int = Field(
        ..., description="Eligible employees with a deferral rate of zero or null"
    )
    average_deferral_rate: Optional[float] = Field(
        None, description="Mean deferral rate among enrolled employees, as a decimal"
    )
    median_deferral_rate: Optional[float] = Field(
        None, description="Median deferral rate among enrolled employees, as a decimal"
    )
    total_eligible_compensation: float = Field(
        ..., description="Sum of gross compensation across eligible employees"
    )
    total_employer_match: float = Field(
        ..., description="Sum of employer_match_contribution as loaded in the census"
    )
    total_employer_core: float = Field(
        ..., description="Sum of employer_core_contribution as loaded in the census"
    )
    total_employer_cost: float = Field(
        ..., description="total_employer_match + total_employer_core"
    )
    hce_count: int = Field(
        ...,
        description="Employees in this slice classified as HCE by current-year compensation",
    )


class CensusSegmentMetrics(CensusMetrics):
    """Metrics for a single value within a segment dimension (e.g. one department)."""

    dimension: str = Field(
        ...,
        description="Segment dimension, e.g. 'department', 'age_band', 'tenure_band', 'hce_status'",
    )
    value: str = Field(..., description="Segment value, e.g. 'Engineering' or '30-39'")


class CensusDataQualityIssue(BaseModel):
    """A data quality flag surfaced instead of failing an import outright."""

    issue_type: str = Field(
        ...,
        description=(
            "One of: missing_required_field, duplicate_employee_id, "
            "out_of_range_value, unparseable_date"
        ),
    )
    field: Optional[str] = Field(
        None, description="Affected census field, if applicable"
    )
    severity: str = Field(..., description="'error' or 'warning'")
    count: int = Field(..., description="Number of affected rows")
    message: str = Field(..., description="Human-readable description")


class CensusAnalysisResult(BaseModel):
    """Result from census-based pre-simulation analysis."""

    total_employees: int = Field(..., description="Total rows in the census file")
    active_employees: int = Field(
        ..., description="Rows flagged active as of the census"
    )
    overall: CensusMetrics = Field(
        ..., description="Metrics across all active employees, unsegmented"
    )
    segments: List[CensusSegmentMetrics] = Field(
        ...,
        description=(
            "Per-value breakdown for each available segment dimension. Only "
            "dimensions the census actually carries data for are included."
        ),
    )
    available_segment_dimensions: List[str] = Field(
        ...,
        description="Segment dimensions with usable data in this census, e.g. ['department', 'age_band']",
    )
    data_quality_issues: List[CensusDataQualityIssue] = Field(
        ...,
        description="Missing/null critical fields, duplicate IDs, out-of-range values",
    )
    as_of_date: date = Field(
        ..., description="Date used for age/tenure/HCE calculations"
    )
    as_of_date_source: str = Field(
        ..., description="'provided' or 'inferred' from the census"
    )
    hce_compensation_threshold: Optional[float] = Field(
        None,
        description="IRS HCE compensation threshold used for the as-of year, if known",
    )
    source_file: str = Field(..., description="Path to source census file")
    message: Optional[str] = Field(None, description="Informational or warning message")
