"""Pydantic models for termination rate calculation."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TerminationRateCalculation(BaseModel):
    """Intermediate calculation state for deriving termination rate suggestion."""

    calculation_id: UUID = Field(
        ..., description="Unique identifier for this calculation"
    )
    scenario_id: str = Field(..., description="Scenario context")
    plan_design_id: str = Field(..., description="Benefit plan identifier")
    snapshot_date: str = Field(..., description="Census snapshot date (YYYY-MM-DD)")
    period_year: int = Field(..., description="Calendar year for calculation")

    # Calculation Components
    total_active_employees: int = Field(
        ..., ge=0, description="Count of ACTIVE employees (denominator)"
    )
    total_terminated_employees: int = Field(
        ..., ge=0, description="Count of TERMINATED employees in period (numerator)"
    )

    calculation_numerator: Decimal = Field(..., ge=0, description="Termination count")
    calculation_denominator: Decimal = Field(
        ..., ge=0, description="Active employee count"
    )

    # Result
    calculated_rate: Optional[Decimal] = Field(
        None, ge=0, le=100, description="Calculated rate (0-100%), null if error"
    )

    # Error Handling
    calculation_status: Literal[
        "SUCCESS", "INSUFFICIENT_DATA", "DIVISION_BY_ZERO"
    ] = Field(..., description="Status of calculation")
    error_message: Optional[str] = Field(
        None, description="Error message if calculation failed"
    )

    calculated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of calculation"
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {Decimal: str}

    @field_validator("calculated_rate")
    @classmethod
    def validate_rate_range(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure rate is in valid range."""
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Calculated rate must be between 0 and 100")
        return v

    @field_validator("calculated_rate", mode="before")
    @classmethod
    def ensure_decimal(cls, v):
        """Ensure calculated_rate is Decimal."""
        if v is None:
            return None
        if isinstance(v, str):
            return Decimal(v)
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        return v
