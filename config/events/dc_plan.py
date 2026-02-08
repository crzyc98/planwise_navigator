# filename: config/events/dc_plan.py
"""
DC Plan event payloads for retirement plan administration.

Contains:
- EligibilityPayload: Plan participation qualification
- EnrollmentPayload: Deferral election handling
- ContributionPayload: All contribution sources
- VestingPayload: Service-based vesting
- AutoEnrollmentWindowPayload: Auto-enrollment lifecycle
- EnrollmentChangePayload: Enrollment modifications
"""

from datetime import date
from decimal import Decimal
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .validators import quantize_amount, quantize_rate, quantize_amount_dict, quantize_rate_optional


class EligibilityPayload(BaseModel):
    """Plan participation qualification tracking"""

    event_type: Literal["eligibility"] = "eligibility"
    plan_id: str = Field(..., min_length=1)
    eligible: bool
    eligibility_date: date
    reason: Literal["age_and_service", "immediate", "hours_requirement", "rehire"]


class EnrollmentPayload(BaseModel):
    """Deferral election and auto-enrollment handling with enhanced window tracking"""

    event_type: Literal["enrollment"] = "enrollment"
    plan_id: str = Field(..., min_length=1)
    enrollment_date: date
    pre_tax_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    roth_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    after_tax_contribution_rate: Decimal = Field(
        default=Decimal("0"), ge=0, le=1, decimal_places=4
    )

    # Enhanced auto-enrollment tracking for E023
    auto_enrollment: bool = False
    opt_out_window_expires: Optional[date] = None
    enrollment_source: Literal["proactive", "auto", "voluntary"] = "voluntary"
    auto_enrollment_window_start: Optional[date] = None
    auto_enrollment_window_end: Optional[date] = None
    proactive_enrollment_eligible: bool = False
    window_timing_compliant: bool = True

    @field_validator(
        "pre_tax_contribution_rate",
        "roth_contribution_rate",
        "after_tax_contribution_rate",
    )
    @classmethod
    def validate_contribution_rate(cls, v: Decimal) -> Decimal:
        """Ensure contribution rate has proper precision"""
        return quantize_rate(v)


class ContributionPayload(BaseModel):
    """All contribution sources with IRS categorization"""

    event_type: Literal["contribution"] = "contribution"
    plan_id: str = Field(..., min_length=1)
    source: Literal[
        "employee_pre_tax",
        "employee_roth",
        "employee_after_tax",
        "employee_catch_up",
        "employer_match",
        "employer_match_true_up",
        "employer_nonelective",
        "employer_profit_sharing",
        "forfeiture_allocation",
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    pay_period_end: date
    contribution_date: date
    ytd_amount: Decimal = Field(..., ge=0, decimal_places=6)
    payroll_id: str = Field(..., min_length=1)
    irs_limit_applied: bool = False
    inferred_value: bool = False

    @field_validator("amount", "ytd_amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amounts have proper precision (18,6)"""
        return quantize_amount(v)


class VestingPayload(BaseModel):
    """Service-based employer contribution vesting"""

    event_type: Literal["vesting"] = "vesting"
    plan_id: str = Field(..., min_length=1)
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

    source_balances_vested: Dict[
        Literal["employer_match", "employer_nonelective", "employer_profit_sharing"],
        Decimal,
    ]

    vesting_schedule_type: Literal["graded", "cliff", "immediate"]
    service_computation_date: date
    service_credited_hours: int = Field(..., ge=0)
    service_period_end_date: date

    @field_validator("vested_percentage")
    @classmethod
    def validate_vested_percentage(cls, v: Decimal) -> Decimal:
        """Ensure vested percentage has proper precision"""
        return quantize_rate(v)

    @field_validator("source_balances_vested")
    @classmethod
    def validate_source_balances(cls, v: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Ensure source balances have proper precision"""
        return quantize_amount_dict(v)


class AutoEnrollmentWindowPayload(BaseModel):
    """Auto-enrollment window lifecycle tracking"""

    event_type: Literal["auto_enrollment_window"] = "auto_enrollment_window"
    plan_id: str = Field(..., min_length=1)
    window_action: Literal["opened", "closed", "expired"]
    window_start_date: date
    window_end_date: date
    window_duration_days: int = Field(..., ge=1, le=365)
    default_deferral_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    eligible_for_proactive: bool = True
    proactive_window_end: Optional[date] = None

    @field_validator("default_deferral_rate")
    @classmethod
    def validate_deferral_rate(cls, v: Decimal) -> Decimal:
        """Ensure deferral rate has proper precision"""
        return quantize_rate(v)


class EnrollmentChangePayload(BaseModel):
    """Enrollment status changes including opt-outs and modifications"""

    event_type: Literal["enrollment_change"] = "enrollment_change"
    plan_id: str = Field(..., min_length=1)
    change_type: Literal["opt_out", "rate_change", "source_change", "cancellation"]
    change_reason: Literal[
        "employee_opt_out",
        "plan_amendment",
        "compliance_correction",
        "system_correction",
    ]
    previous_enrollment_date: Optional[date] = None
    new_pre_tax_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    new_roth_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1, decimal_places=4)
    previous_pre_tax_rate: Optional[Decimal] = None
    previous_roth_rate: Optional[Decimal] = None
    within_opt_out_window: bool = False
    penalty_applied: bool = False

    @field_validator(
        "new_pre_tax_rate",
        "new_roth_rate",
        "previous_pre_tax_rate",
        "previous_roth_rate",
    )
    @classmethod
    def validate_contribution_rates(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure contribution rates have proper precision"""
        return quantize_rate_optional(v)


__all__ = [
    "EligibilityPayload",
    "EnrollmentPayload",
    "ContributionPayload",
    "VestingPayload",
    "AutoEnrollmentWindowPayload",
    "EnrollmentChangePayload",
]
