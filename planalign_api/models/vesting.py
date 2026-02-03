"""Pydantic models for vesting analysis."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_serializer


class VestingScheduleType(str, Enum):
    """Pre-defined vesting schedule types."""

    IMMEDIATE = "immediate"
    CLIFF_2_YEAR = "cliff_2_year"
    CLIFF_3_YEAR = "cliff_3_year"
    CLIFF_4_YEAR = "cliff_4_year"
    QACA_2_YEAR = "qaca_2_year"
    GRADED_3_YEAR = "graded_3_year"
    GRADED_4_YEAR = "graded_4_year"
    GRADED_5_YEAR = "graded_5_year"


class VestingScheduleInfo(BaseModel):
    """Information about a vesting schedule for display."""

    schedule_type: VestingScheduleType
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., max_length=200)
    percentages: dict[int, float] = Field(
        ...,
        description="Year -> vesting percentage mapping"
    )


class VestingScheduleConfig(BaseModel):
    """User-selected vesting schedule configuration."""

    schedule_type: VestingScheduleType
    name: str = Field(..., min_length=1, max_length=50)
    require_hours_credit: bool = Field(
        default=False,
        description="If true, employees must meet hours threshold for vesting credit"
    )
    hours_threshold: int = Field(
        default=1000,
        ge=0,
        le=2080,
        description="Minimum annual hours for vesting credit (default: 1000)"
    )


class VestingAnalysisRequest(BaseModel):
    """Request to run vesting analysis comparing two schedules."""

    current_schedule: VestingScheduleConfig = Field(
        ...,
        description="Current vesting schedule to analyze"
    )
    proposed_schedule: VestingScheduleConfig = Field(
        ...,
        description="Proposed vesting schedule to compare"
    )
    simulation_year: Optional[int] = Field(
        default=None,
        ge=2020,
        le=2050,
        description="Simulation year to analyze (default: final year)"
    )


class EmployeeVestingDetail(BaseModel):
    """Vesting calculation details for a single employee."""

    employee_id: str = Field(..., min_length=1)
    hire_date: date
    termination_date: date
    tenure_years: int = Field(..., ge=0)
    tenure_band: str
    annual_hours_worked: int = Field(..., ge=0)
    total_employer_contributions: Decimal = Field(..., ge=0)

    # Current schedule results
    current_vesting_pct: Decimal = Field(..., ge=0, le=1)
    current_vested_amount: Decimal = Field(..., ge=0)
    current_forfeiture: Decimal = Field(..., ge=0)

    # Proposed schedule results
    proposed_vesting_pct: Decimal = Field(..., ge=0, le=1)
    proposed_vested_amount: Decimal = Field(..., ge=0)
    proposed_forfeiture: Decimal = Field(..., ge=0)

    # Comparison
    forfeiture_variance: Decimal = Field(
        ...,
        description="Proposed - Current forfeiture (negative = less forfeiture)"
    )

    @field_serializer(
        'total_employer_contributions', 'current_vesting_pct', 'current_vested_amount',
        'current_forfeiture', 'proposed_vesting_pct', 'proposed_vested_amount',
        'proposed_forfeiture', 'forfeiture_variance'
    )
    def serialize_decimal(self, v: Decimal) -> float:
        """Serialize Decimal as float for JSON responses."""
        return float(v)


class TenureBandSummary(BaseModel):
    """Forfeiture summary for a tenure band."""

    tenure_band: str
    employee_count: int = Field(..., ge=0)
    total_contributions: Decimal = Field(..., ge=0)
    current_forfeitures: Decimal = Field(..., ge=0)
    proposed_forfeitures: Decimal = Field(..., ge=0)
    forfeiture_variance: Decimal

    @field_serializer(
        'total_contributions', 'current_forfeitures', 'proposed_forfeitures',
        'forfeiture_variance'
    )
    def serialize_decimal(self, v: Decimal) -> float:
        """Serialize Decimal as float for JSON responses."""
        return float(v)


class VestingAnalysisSummary(BaseModel):
    """High-level summary of vesting analysis."""

    analysis_year: int
    terminated_employee_count: int = Field(..., ge=0)
    total_employer_contributions: Decimal = Field(..., ge=0)

    # Current schedule totals
    current_total_vested: Decimal = Field(..., ge=0)
    current_total_forfeited: Decimal = Field(..., ge=0)

    # Proposed schedule totals
    proposed_total_vested: Decimal = Field(..., ge=0)
    proposed_total_forfeited: Decimal = Field(..., ge=0)

    # Comparison
    forfeiture_variance: Decimal = Field(
        ...,
        description="Proposed - Current total forfeiture"
    )
    forfeiture_variance_pct: Decimal = Field(
        ...,
        description="Percentage change in forfeitures"
    )

    @field_serializer(
        'total_employer_contributions', 'current_total_vested', 'current_total_forfeited',
        'proposed_total_vested', 'proposed_total_forfeited', 'forfeiture_variance',
        'forfeiture_variance_pct'
    )
    def serialize_decimal(self, v: Decimal) -> float:
        """Serialize Decimal as float for JSON responses."""
        return float(v)


class VestingAnalysisResponse(BaseModel):
    """Complete response from vesting analysis."""

    scenario_id: str
    scenario_name: str
    current_schedule: VestingScheduleConfig
    proposed_schedule: VestingScheduleConfig
    summary: VestingAnalysisSummary
    by_tenure_band: List[TenureBandSummary]
    employee_details: List[EmployeeVestingDetail]


class VestingScheduleListResponse(BaseModel):
    """Response listing available vesting schedules."""

    schedules: List[VestingScheduleInfo]
