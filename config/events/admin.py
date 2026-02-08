# filename: config/events/admin.py
"""
Plan administration event payloads for compliance and governance.

Contains:
- ForfeiturePayload: Unvested contribution recapture
- HCEStatusPayload: Highly compensated employee determination
- ComplianceEventPayload: IRS limit monitoring
"""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .validators import quantize_amount, quantize_rate


class ForfeiturePayload(BaseModel):
    """Unvested employer contribution recapture"""

    event_type: Literal["forfeiture"] = "forfeiture"
    plan_id: str = Field(..., min_length=1)
    forfeited_from_source: Literal[
        "employer_match", "employer_nonelective", "employer_profit_sharing"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    reason: Literal["unvested_termination", "break_in_service"]
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amount has proper precision (18,6)"""
        return quantize_amount(v)

    @field_validator("vested_percentage")
    @classmethod
    def validate_vested_percentage(cls, v: Decimal) -> Decimal:
        """Ensure vested percentage has proper precision"""
        return quantize_rate(v)


class HCEStatusPayload(BaseModel):
    """Highly compensated employee determination"""

    event_type: Literal["hce_status"] = "hce_status"
    plan_id: str = Field(..., min_length=1)
    determination_method: Literal["prior_year", "current_year"]
    ytd_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    annualized_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    hce_threshold: Decimal = Field(..., gt=0, decimal_places=6)
    is_hce: bool
    determination_date: date
    prior_year_hce: Optional[bool] = None

    @field_validator("ytd_compensation", "annualized_compensation", "hce_threshold")
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision (18,6)"""
        return quantize_amount(v)


class ComplianceEventPayload(BaseModel):
    """Basic IRS limit monitoring"""

    event_type: Literal["compliance"] = "compliance"
    plan_id: str = Field(..., min_length=1)
    compliance_type: Literal[
        "402g_limit_approach",
        "415c_limit_approach",
        "catch_up_eligible",
    ]
    limit_type: Literal["elective_deferral", "annual_additions", "catch_up"]
    applicable_limit: Decimal = Field(..., gt=0, decimal_places=6)
    current_amount: Decimal = Field(..., ge=0, decimal_places=6)
    monitoring_date: date

    @field_validator("applicable_limit", "current_amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amounts have proper precision (18,6)"""
        return quantize_amount(v)


__all__ = [
    "ForfeiturePayload",
    "HCEStatusPayload",
    "ComplianceEventPayload",
]
