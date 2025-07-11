# filename: config/events.py
"""Unified event model with Pydantic v2 discriminated unions for DC plan and workforce events."""

from typing import Annotated, Union, Optional, Any, Literal, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4


# Workforce Event Payloads
class HirePayload(BaseModel):
    """Employee onboarding with plan eligibility context"""

    event_type: Literal["hire"] = "hire"
    plan_id: Optional[str] = None  # Links to DC plan when applicable
    hire_date: date
    department: str = Field(..., min_length=1)
    job_level: int = Field(..., ge=1, le=10)
    annual_compensation: Decimal = Field(..., gt=0)

    @field_validator('annual_compensation')
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision"""
        # Round to 6 decimal places for consistency
        return v.quantize(Decimal('0.000001'))


class PromotionPayload(BaseModel):
    """Level changes affecting contribution capacity and HCE status"""

    event_type: Literal["promotion"] = "promotion"
    plan_id: Optional[str] = None
    new_job_level: int = Field(..., ge=1, le=10)
    new_annual_compensation: Decimal = Field(..., gt=0)
    effective_date: date

    @field_validator('new_annual_compensation')
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision"""
        return v.quantize(Decimal('0.000001'))


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

    @field_validator('new_compensation')
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision"""
        return v.quantize(Decimal('0.000001'))

    @field_validator('merit_percentage')
    @classmethod
    def validate_percentage(cls, v: Decimal) -> Decimal:
        """Ensure percentage has proper precision"""
        return v.quantize(Decimal('0.0001'))


# DC Plan Event Payloads
class EligibilityPayload(BaseModel):
    """Plan participation qualification tracking"""

    event_type: Literal["eligibility"] = "eligibility"
    plan_id: str = Field(..., min_length=1)
    eligible: bool
    eligibility_date: date
    reason: Literal[
        "age_and_service",
        "immediate",
        "hours_requirement",
        "rehire"
    ]


class EnrollmentPayload(BaseModel):
    """Deferral election and auto-enrollment handling"""

    event_type: Literal["enrollment"] = "enrollment"
    plan_id: str = Field(..., min_length=1)
    enrollment_date: date
    pre_tax_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    roth_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    after_tax_contribution_rate: Decimal = Field(
        default=Decimal('0'), ge=0, le=1, decimal_places=4
    )
    auto_enrollment: bool = False
    opt_out_window_expires: Optional[date] = None

    @field_validator('pre_tax_contribution_rate', 'roth_contribution_rate',
                     'after_tax_contribution_rate')
    @classmethod
    def validate_contribution_rate(cls, v: Decimal) -> Decimal:
        """Ensure contribution rate has proper precision"""
        return v.quantize(Decimal('0.0001'))


class ContributionPayload(BaseModel):
    """All contribution sources with IRS categorization"""

    event_type: Literal["contribution"] = "contribution"
    plan_id: str = Field(..., min_length=1)
    source: Literal[
        "employee_pre_tax", "employee_roth", "employee_after_tax", "employee_catch_up",
        "employer_match", "employer_match_true_up", "employer_nonelective",
        "employer_profit_sharing", "forfeiture_allocation"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    pay_period_end: date
    contribution_date: date  # Date funds are deposited - critical for performance
    ytd_amount: Decimal = Field(..., ge=0, decimal_places=6)
    payroll_id: str = Field(..., min_length=1)  # Required for audit trail
    irs_limit_applied: bool = False
    inferred_value: bool = False

    @field_validator('amount', 'ytd_amount')
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amounts have proper precision (18,6)"""
        return v.quantize(Decimal('0.000001'))


class VestingPayload(BaseModel):
    """Service-based employer contribution vesting"""

    event_type: Literal["vesting"] = "vesting"
    plan_id: str = Field(..., min_length=1)
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

    # The balance in each source to which the new percentage is applied
    source_balances_vested: Dict[
        Literal["employer_match", "employer_nonelective", "employer_profit_sharing"],
        Decimal
    ]

    vesting_schedule_type: Literal["graded", "cliff", "immediate"]
    service_computation_date: date
    service_credited_hours: int = Field(..., ge=0)  # Required for audit
    service_period_end_date: date  # Required for audit

    @field_validator('vested_percentage')
    @classmethod
    def validate_vested_percentage(cls, v: Decimal) -> Decimal:
        """Ensure vested percentage has proper precision"""
        return v.quantize(Decimal('0.0001'))

    @field_validator('source_balances_vested')
    @classmethod
    def validate_source_balances(cls, v: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Ensure source balances have proper precision"""
        return {source: amount.quantize(Decimal('0.000001'))
                for source, amount in v.items()}


# Plan Administration Event Payloads (S072-04)
class ForfeiturePayload(BaseModel):
    """Unvested employer contribution recapture"""

    event_type: Literal["forfeiture"] = "forfeiture"
    plan_id: str = Field(..., min_length=1)
    forfeited_from_source: Literal[
        "employer_match",
        "employer_nonelective",
        "employer_profit_sharing"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    reason: Literal["unvested_termination", "break_in_service"]
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amount has proper precision (18,6)"""
        return v.quantize(Decimal('0.000001'))

    @field_validator('vested_percentage')
    @classmethod
    def validate_vested_percentage(cls, v: Decimal) -> Decimal:
        """Ensure vested percentage has proper precision"""
        return v.quantize(Decimal('0.0001'))


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

    @field_validator('ytd_compensation', 'annualized_compensation', 'hce_threshold')
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        """Ensure compensation has proper precision (18,6)"""
        return v.quantize(Decimal('0.000001'))


class ComplianceEventPayload(BaseModel):
    """Basic IRS limit monitoring"""

    event_type: Literal["compliance"] = "compliance"
    plan_id: str = Field(..., min_length=1)
    compliance_type: Literal[
        "402g_limit_approach",    # Approaching elective deferral limit
        "415c_limit_approach",    # Approaching annual additions limit
        "catch_up_eligible"       # Participant becomes catch-up eligible
    ]
    limit_type: Literal[
        "elective_deferral",
        "annual_additions",
        "catch_up"
    ]
    applicable_limit: Decimal = Field(..., gt=0, decimal_places=6)
    current_amount: Decimal = Field(..., ge=0, decimal_places=6)
    monitoring_date: date

    @field_validator('applicable_limit', 'current_amount')
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amounts have proper precision (18,6)"""
        return v.quantize(Decimal('0.000001'))


class SimulationEvent(BaseModel):
    """Unified event model for all workforce and DC plan events"""

    model_config = ConfigDict(
        extra='forbid',
        use_enum_values=True,
        validate_assignment=True
    )

    # Core identification
    event_id: UUID = Field(default_factory=uuid4)
    employee_id: str = Field(..., min_length=1)
    effective_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Required context fields (not optional for proper isolation)
    scenario_id: str = Field(..., min_length=1)
    plan_design_id: str = Field(..., min_length=1)
    source_system: str = Field(..., min_length=1)

    # Discriminated union payload for event-specific data
    payload: Union[
        # Workforce Events
        Annotated[HirePayload, Field(discriminator='event_type')],
        Annotated[PromotionPayload, Field(discriminator='event_type')],
        Annotated[TerminationPayload, Field(discriminator='event_type')],
        Annotated[MeritPayload, Field(discriminator='event_type')],
        # DC Plan Events (S072-03) - Core 4 events
        Annotated[EligibilityPayload, Field(discriminator='event_type')],
        Annotated[EnrollmentPayload, Field(discriminator='event_type')],
        Annotated[ContributionPayload, Field(discriminator='event_type')],
        Annotated[VestingPayload, Field(discriminator='event_type')],
        # Plan Administration Events (S072-04)
        Annotated[ForfeiturePayload, Field(discriminator='event_type')],
        Annotated[HCEStatusPayload, Field(discriminator='event_type')],
        Annotated[ComplianceEventPayload, Field(discriminator='event_type')],
        # Placeholder for additional DC plan events (S072-05)
    ] = Field(..., discriminator='event_type')

    # Optional correlation for event tracing
    correlation_id: Optional[str] = None

    @field_validator('employee_id')
    @classmethod
    def validate_employee_id(cls, v: str) -> str:
        """Validate employee_id is not empty"""
        if not v or not v.strip():
            raise ValueError('employee_id cannot be empty')
        return v.strip()

    @field_validator('scenario_id')
    @classmethod
    def validate_scenario_id(cls, v: str) -> str:
        """Validate scenario_id is not empty"""
        if not v or not v.strip():
            raise ValueError('scenario_id cannot be empty')
        return v.strip()

    @field_validator('plan_design_id')
    @classmethod
    def validate_plan_design_id(cls, v: str) -> str:
        """Validate plan_design_id is not empty"""
        if not v or not v.strip():
            raise ValueError('plan_design_id cannot be empty')
        return v.strip()


class EventFactory:
    """Factory for creating validated simulation events"""

    @staticmethod
    def create_event(raw_data: dict[str, Any]) -> SimulationEvent:
        """Create properly validated event from raw data"""
        return SimulationEvent.model_validate(raw_data)

    @staticmethod
    def validate_schema(event_data: dict[str, Any]) -> dict[str, Any]:
        """Validate event data against schema without creating instance"""
        # Use Pydantic v2 validation
        model = SimulationEvent.model_validate(event_data)
        return model.model_dump()

    @staticmethod
    def create_basic_event(
        employee_id: str,
        effective_date: date,
        scenario_id: str,
        plan_design_id: str,
        source_system: str = "event_factory",
        correlation_id: Optional[str] = None
    ) -> SimulationEvent:
        """Create basic event with required context fields"""
        # This method is deprecated - use specific event factories instead
        raise NotImplementedError(
            "create_basic_event is deprecated. Use WorkforceEventFactory methods instead."
        )


class WorkforceEventFactory(EventFactory):
    """Factory for creating workforce events with DC plan context"""

    @staticmethod
    def create_hire_event(
        employee_id: str,
        scenario_id: str,
        plan_design_id: str,
        hire_date: date,
        department: str,
        job_level: int,
        annual_compensation: Decimal,
        plan_id: Optional[str] = None
    ) -> SimulationEvent:
        """Create hire event with optional plan context"""

        payload = HirePayload(
            hire_date=hire_date,
            department=department,
            job_level=job_level,
            annual_compensation=annual_compensation,
            plan_id=plan_id
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=hire_date,
            source_system="workforce_simulation",
            payload=payload
        )

    @staticmethod
    def create_promotion_event(
        employee_id: str,
        scenario_id: str,
        plan_design_id: str,
        effective_date: date,
        new_job_level: int,
        new_annual_compensation: Decimal,
        plan_id: Optional[str] = None
    ) -> SimulationEvent:
        """Create promotion event affecting HCE status"""

        payload = PromotionPayload(
            new_job_level=new_job_level,
            new_annual_compensation=new_annual_compensation,
            effective_date=effective_date,
            plan_id=plan_id
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="workforce_simulation",
            payload=payload
        )

    @staticmethod
    def create_termination_event(
        employee_id: str,
        scenario_id: str,
        plan_design_id: str,
        effective_date: date,
        termination_reason: Literal[
            "voluntary", "involuntary", "retirement", "death", "disability"
        ],
        final_pay_date: date,
        plan_id: Optional[str] = None
    ) -> SimulationEvent:
        """Create termination event triggering distribution eligibility"""

        payload = TerminationPayload(
            termination_reason=termination_reason,
            final_pay_date=final_pay_date,
            plan_id=plan_id
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="workforce_simulation",
            payload=payload
        )

    @staticmethod
    def create_merit_event(
        employee_id: str,
        scenario_id: str,
        plan_design_id: str,
        effective_date: date,
        new_compensation: Decimal,
        merit_percentage: Decimal,
        plan_id: Optional[str] = None
    ) -> SimulationEvent:
        """Create merit event with HCE impact tracking"""

        payload = MeritPayload(
            new_compensation=new_compensation,
            merit_percentage=merit_percentage,
            plan_id=plan_id
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="workforce_simulation",
            payload=payload
        )


class DCPlanEventFactory(EventFactory):
    """Factory for creating DC plan events with validation"""

    @staticmethod
    def create_eligibility_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        eligible: bool,
        eligibility_date: date,
        reason: Literal["age_and_service", "immediate", "hours_requirement", "rehire"]
    ) -> SimulationEvent:
        """Create eligibility event for plan participation tracking"""

        payload = EligibilityPayload(
            plan_id=plan_id,
            eligible=eligible,
            eligibility_date=eligibility_date,
            reason=reason
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=eligibility_date,
            source_system="dc_plan_administration",
            payload=payload
        )

    @staticmethod
    def create_enrollment_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        enrollment_date: date,
        pre_tax_contribution_rate: Decimal,
        roth_contribution_rate: Decimal,
        after_tax_contribution_rate: Decimal = Decimal('0'),
        auto_enrollment: bool = False,
        opt_out_window_expires: Optional[date] = None
    ) -> SimulationEvent:
        """Create enrollment event for deferral elections"""

        payload = EnrollmentPayload(
            plan_id=plan_id,
            enrollment_date=enrollment_date,
            pre_tax_contribution_rate=pre_tax_contribution_rate,
            roth_contribution_rate=roth_contribution_rate,
            after_tax_contribution_rate=after_tax_contribution_rate,
            auto_enrollment=auto_enrollment,
            opt_out_window_expires=opt_out_window_expires
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=enrollment_date,
            source_system="dc_plan_administration",
            payload=payload
        )

    @staticmethod
    def create_contribution_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        source: Literal[
            "employee_pre_tax", "employee_roth", "employee_after_tax", "employee_catch_up",
            "employer_match", "employer_match_true_up", "employer_nonelective",
            "employer_profit_sharing", "forfeiture_allocation"
        ],
        amount: Decimal,
        pay_period_end: date,
        contribution_date: date,
        ytd_amount: Decimal,
        payroll_id: str,
        irs_limit_applied: bool = False,
        inferred_value: bool = False
    ) -> SimulationEvent:
        """Create contribution event with required audit fields"""

        payload = ContributionPayload(
            plan_id=plan_id,
            source=source,
            amount=amount,
            pay_period_end=pay_period_end,
            contribution_date=contribution_date,
            ytd_amount=ytd_amount,
            payroll_id=payroll_id,
            irs_limit_applied=irs_limit_applied,
            inferred_value=inferred_value
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=contribution_date,
            source_system="dc_plan_administration",
            payload=payload
        )

    @staticmethod
    def create_vesting_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        vested_percentage: Decimal,
        source_balances_vested: Dict[
            Literal["employer_match", "employer_nonelective", "employer_profit_sharing"],
            Decimal
        ],
        vesting_schedule_type: Literal["graded", "cliff", "immediate"],
        service_computation_date: date,
        service_credited_hours: int,
        service_period_end_date: date
    ) -> SimulationEvent:
        """Create vesting event with service hour tracking"""

        payload = VestingPayload(
            plan_id=plan_id,
            vested_percentage=vested_percentage,
            source_balances_vested=source_balances_vested,
            vesting_schedule_type=vesting_schedule_type,
            service_computation_date=service_computation_date,
            service_credited_hours=service_credited_hours,
            service_period_end_date=service_period_end_date
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=service_computation_date,
            source_system="dc_plan_administration",
            payload=payload
        )


class PlanAdministrationEventFactory(EventFactory):
    """Factory for creating plan administration events"""

    @staticmethod
    def create_forfeiture_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        forfeited_from_source: Literal[
            "employer_match", "employer_nonelective", "employer_profit_sharing"
        ],
        amount: Decimal,
        reason: Literal["unvested_termination", "break_in_service"],
        vested_percentage: Decimal,
        effective_date: date
    ) -> SimulationEvent:
        """Create forfeiture event for unvested contributions"""

        payload = ForfeiturePayload(
            plan_id=plan_id,
            forfeited_from_source=forfeited_from_source,
            amount=amount,
            reason=reason,
            vested_percentage=vested_percentage
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="plan_administration",
            payload=payload
        )

    @staticmethod
    def create_hce_status_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        determination_method: Literal["prior_year", "current_year"],
        ytd_compensation: Decimal,
        annualized_compensation: Decimal,
        hce_threshold: Decimal,
        is_hce: bool,
        determination_date: date,
        prior_year_hce: Optional[bool] = None
    ) -> SimulationEvent:
        """Create HCE status determination event"""

        payload = HCEStatusPayload(
            plan_id=plan_id,
            determination_method=determination_method,
            ytd_compensation=ytd_compensation,
            annualized_compensation=annualized_compensation,
            hce_threshold=hce_threshold,
            is_hce=is_hce,
            determination_date=determination_date,
            prior_year_hce=prior_year_hce
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=determination_date,
            source_system="hce_determination",
            payload=payload
        )

    @staticmethod
    def create_compliance_monitoring_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        compliance_type: Literal["402g_limit_approach", "415c_limit_approach", "catch_up_eligible"],
        limit_type: Literal["elective_deferral", "annual_additions", "catch_up"],
        applicable_limit: Decimal,
        current_amount: Decimal,
        monitoring_date: date
    ) -> SimulationEvent:
        """Create compliance monitoring event for limit tracking"""

        payload = ComplianceEventPayload(
            plan_id=plan_id,
            compliance_type=compliance_type,
            limit_type=limit_type,
            applicable_limit=applicable_limit,
            current_amount=current_amount,
            monitoring_date=monitoring_date
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=monitoring_date,
            source_system="compliance_monitoring",
            payload=payload
        )


# Backward compatibility: Alias for migration from legacy SimulationEvent
LegacySimulationEvent = SimulationEvent
