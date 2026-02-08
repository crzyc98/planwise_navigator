# filename: config/events/workforce.py
"""
Workforce event payloads for employee lifecycle events.

Contains:
- HirePayload: Employee onboarding
- PromotionPayload: Level/compensation changes
- TerminationPayload: Employment end
- MeritPayload: Compensation adjustments
- SabbaticalPayload: Extended leave tracking
"""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .validators import quantize_amount, quantize_rate


class HirePayload(BaseModel):
    """Employee onboarding with plan eligibility context"""

    event_type: Literal["hire"] = "hire"
    plan_id: Optional[str] = None  # Links to DC plan when applicable
    hire_date: date
    department: str = Field(..., min_length=1)
    job_level: int = Field(..., ge=1, le=10)
    annual_compensation: Decimal = Field(..., gt=0)

    @field_validator("annual_compensation")
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision"""
        return quantize_amount(v)


class PromotionPayload(BaseModel):
    """Level changes affecting contribution capacity and HCE status"""

    event_type: Literal["promotion"] = "promotion"
    plan_id: Optional[str] = None
    new_job_level: int = Field(..., ge=1, le=10)
    new_annual_compensation: Decimal = Field(..., gt=0)
    effective_date: date

    @field_validator("new_annual_compensation")
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision"""
        return quantize_amount(v)


class TerminationPayload(BaseModel):
    """Employment end triggering distribution eligibility"""

    event_type: Literal["termination"] = "termination"
    plan_id: Optional[str] = None
    termination_reason: Literal[
        "voluntary", "involuntary", "retirement", "death", "disability"
    ]
    final_pay_date: date


class MeritPayload(BaseModel):
    """Compensation changes affecting HCE status and contribution limits"""

    event_type: Literal["merit"] = "merit"
    plan_id: Optional[str] = None
    new_compensation: Decimal = Field(..., gt=0)
    merit_percentage: Decimal = Field(..., ge=0, le=1)

    @field_validator("new_compensation")
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision"""
        return quantize_amount(v)

    @field_validator("merit_percentage")
    @classmethod
    def validate_percentage(cls, v: Decimal) -> Decimal:
        """Ensure percentage has proper precision"""
        return quantize_rate(v)


class SabbaticalPayload(BaseModel):
    """Employee sabbatical leave event for extended time off.

    Sabbaticals are typically offered to long-tenured employees for
    personal development, academic pursuits, or rest. This event
    tracks the leave period and compensation continuation.
    """

    event_type: Literal["sabbatical"] = "sabbatical"
    plan_id: Optional[str] = None
    start_date: date
    end_date: date
    reason: Literal["academic", "personal", "medical", "community_service"]
    compensation_percentage: Decimal = Field(
        ..., ge=0, le=1, decimal_places=4,
        description="Percentage of salary continued during sabbatical (0.0 to 1.0)"
    )

    @field_validator("compensation_percentage")
    @classmethod
    def validate_percentage(cls, v: Decimal) -> Decimal:
        """Ensure percentage has proper precision"""
        return quantize_rate(v)

    @field_validator("end_date")
    @classmethod
    def validate_end_after_start(cls, v: date, info) -> date:
        """Ensure end_date is after start_date"""
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date must be after start_date")
        return v


__all__ = [
    "HirePayload",
    "PromotionPayload",
    "TerminationPayload",
    "MeritPayload",
    "SabbaticalPayload",
]
