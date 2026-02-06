# filename: config/events/core.py
"""
Core event model and factory classes for Fidelity PlanAlign Engine.

Contains:
- SimulationEvent: Unified event model with discriminated union payload
- EventFactory: Base factory with validation and schema checking
- WorkforceEventFactory: Factory for workforce events
- DCPlanEventFactory: Factory for DC plan events
- PlanAdministrationEventFactory: Factory for admin events
- LegacySimulationEvent: Backward compatibility alias
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Dict, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Import all payload types from domain modules
from .workforce import (
    HirePayload,
    PromotionPayload,
    TerminationPayload,
    MeritPayload,
    SabbaticalPayload,
)
from .dc_plan import (
    EligibilityPayload,
    EnrollmentPayload,
    ContributionPayload,
    VestingPayload,
    AutoEnrollmentWindowPayload,
    EnrollmentChangePayload,
)
from .admin import (
    ForfeiturePayload,
    HCEStatusPayload,
    ComplianceEventPayload,
)


class SimulationEvent(BaseModel):
    """Unified event model for all workforce and DC plan events"""

    model_config = ConfigDict(
        extra="forbid", use_enum_values=True, validate_assignment=True
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
        Annotated[HirePayload, Field(discriminator="event_type")],
        Annotated[PromotionPayload, Field(discriminator="event_type")],
        Annotated[TerminationPayload, Field(discriminator="event_type")],
        Annotated[MeritPayload, Field(discriminator="event_type")],
        # DC Plan Events (S072-03) - Core 4 events
        Annotated[EligibilityPayload, Field(discriminator="event_type")],
        Annotated[EnrollmentPayload, Field(discriminator="event_type")],
        Annotated[ContributionPayload, Field(discriminator="event_type")],
        Annotated[VestingPayload, Field(discriminator="event_type")],
        # Auto-Enrollment Events (E023)
        Annotated[AutoEnrollmentWindowPayload, Field(discriminator="event_type")],
        Annotated[EnrollmentChangePayload, Field(discriminator="event_type")],
        # Plan Administration Events (S072-04)
        Annotated[ForfeiturePayload, Field(discriminator="event_type")],
        Annotated[HCEStatusPayload, Field(discriminator="event_type")],
        Annotated[ComplianceEventPayload, Field(discriminator="event_type")],
        # Extended Workforce Events (E004 - Event Type Abstraction Layer)
        Annotated[SabbaticalPayload, Field(discriminator="event_type")],
    ] = Field(..., discriminator="event_type")

    # Optional correlation for event tracing
    correlation_id: Optional[str] = None

    @field_validator("employee_id")
    @classmethod
    def validate_employee_id(cls, v: str) -> str:
        """Validate employee_id is not empty"""
        if not v or not v.strip():
            raise ValueError("employee_id cannot be empty")
        return v.strip()

    @field_validator("scenario_id")
    @classmethod
    def validate_scenario_id(cls, v: str) -> str:
        """Validate scenario_id is not empty"""
        if not v or not v.strip():
            raise ValueError("scenario_id cannot be empty")
        return v.strip()

    @field_validator("plan_design_id")
    @classmethod
    def validate_plan_design_id(cls, v: str) -> str:
        """Validate plan_design_id is not empty"""
        if not v or not v.strip():
            raise ValueError("plan_design_id cannot be empty")
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
        model = SimulationEvent.model_validate(event_data)
        return model.model_dump()

    @staticmethod
    def create_basic_event(
        employee_id: str,
        effective_date: date,
        scenario_id: str,
        plan_design_id: str,
        source_system: str = "event_factory",
        correlation_id: Optional[str] = None,
    ) -> SimulationEvent:
        """Create basic event with required context fields"""
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
        plan_id: Optional[str] = None,
    ) -> SimulationEvent:
        """Create hire event with optional plan context"""

        payload = HirePayload(
            hire_date=hire_date,
            department=department,
            job_level=job_level,
            annual_compensation=annual_compensation,
            plan_id=plan_id,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=hire_date,
            source_system="workforce_simulation",
            payload=payload,
        )

    @staticmethod
    def create_promotion_event(
        employee_id: str,
        scenario_id: str,
        plan_design_id: str,
        effective_date: date,
        new_job_level: int,
        new_annual_compensation: Decimal,
        plan_id: Optional[str] = None,
    ) -> SimulationEvent:
        """Create promotion event affecting HCE status"""

        payload = PromotionPayload(
            new_job_level=new_job_level,
            new_annual_compensation=new_annual_compensation,
            effective_date=effective_date,
            plan_id=plan_id,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="workforce_simulation",
            payload=payload,
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
        plan_id: Optional[str] = None,
    ) -> SimulationEvent:
        """Create termination event triggering distribution eligibility"""

        payload = TerminationPayload(
            termination_reason=termination_reason,
            final_pay_date=final_pay_date,
            plan_id=plan_id,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="workforce_simulation",
            payload=payload,
        )

    @staticmethod
    def create_merit_event(
        employee_id: str,
        scenario_id: str,
        plan_design_id: str,
        effective_date: date,
        new_compensation: Decimal,
        merit_percentage: Decimal,
        plan_id: Optional[str] = None,
    ) -> SimulationEvent:
        """Create merit event with HCE impact tracking"""

        payload = MeritPayload(
            new_compensation=new_compensation,
            merit_percentage=merit_percentage,
            plan_id=plan_id,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="workforce_simulation",
            payload=payload,
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
        reason: Literal["age_and_service", "immediate", "hours_requirement", "rehire"],
    ) -> SimulationEvent:
        """Create eligibility event for plan participation tracking"""

        payload = EligibilityPayload(
            plan_id=plan_id,
            eligible=eligible,
            eligibility_date=eligibility_date,
            reason=reason,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=eligibility_date,
            source_system="dc_plan_administration",
            payload=payload,
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
        after_tax_contribution_rate: Decimal = Decimal("0"),
        auto_enrollment: bool = False,
        opt_out_window_expires: Optional[date] = None,
        enrollment_source: Literal["proactive", "auto", "voluntary"] = "voluntary",
        auto_enrollment_window_start: Optional[date] = None,
        auto_enrollment_window_end: Optional[date] = None,
        proactive_enrollment_eligible: bool = False,
        window_timing_compliant: bool = True,
    ) -> SimulationEvent:
        """Create enrollment event for deferral elections"""

        payload = EnrollmentPayload(
            plan_id=plan_id,
            enrollment_date=enrollment_date,
            pre_tax_contribution_rate=pre_tax_contribution_rate,
            roth_contribution_rate=roth_contribution_rate,
            after_tax_contribution_rate=after_tax_contribution_rate,
            auto_enrollment=auto_enrollment,
            opt_out_window_expires=opt_out_window_expires,
            enrollment_source=enrollment_source,
            auto_enrollment_window_start=auto_enrollment_window_start,
            auto_enrollment_window_end=auto_enrollment_window_end,
            proactive_enrollment_eligible=proactive_enrollment_eligible,
            window_timing_compliant=window_timing_compliant,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=enrollment_date,
            source_system="dc_plan_administration",
            payload=payload,
        )

    @staticmethod
    def create_contribution_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
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
        ],
        amount: Decimal,
        pay_period_end: date,
        contribution_date: date,
        ytd_amount: Decimal,
        payroll_id: str,
        irs_limit_applied: bool = False,
        inferred_value: bool = False,
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
            inferred_value=inferred_value,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=contribution_date,
            source_system="dc_plan_administration",
            payload=payload,
        )

    @staticmethod
    def create_vesting_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        vested_percentage: Decimal,
        source_balances_vested: Dict[
            Literal[
                "employer_match", "employer_nonelective", "employer_profit_sharing"
            ],
            Decimal,
        ],
        vesting_schedule_type: Literal["graded", "cliff", "immediate"],
        service_computation_date: date,
        service_credited_hours: int,
        service_period_end_date: date,
    ) -> SimulationEvent:
        """Create vesting event with service hour tracking"""

        payload = VestingPayload(
            plan_id=plan_id,
            vested_percentage=vested_percentage,
            source_balances_vested=source_balances_vested,
            vesting_schedule_type=vesting_schedule_type,
            service_computation_date=service_computation_date,
            service_credited_hours=service_credited_hours,
            service_period_end_date=service_period_end_date,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=service_computation_date,
            source_system="dc_plan_administration",
            payload=payload,
        )

    @staticmethod
    def create_auto_enrollment_window_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        window_action: Literal["opened", "closed", "expired"],
        window_start_date: date,
        window_end_date: date,
        window_duration_days: int,
        default_deferral_rate: Decimal,
        eligible_for_proactive: bool = True,
        proactive_window_end: Optional[date] = None,
    ) -> SimulationEvent:
        """Create auto-enrollment window lifecycle event"""

        payload = AutoEnrollmentWindowPayload(
            plan_id=plan_id,
            window_action=window_action,
            window_start_date=window_start_date,
            window_end_date=window_end_date,
            window_duration_days=window_duration_days,
            default_deferral_rate=default_deferral_rate,
            eligible_for_proactive=eligible_for_proactive,
            proactive_window_end=proactive_window_end,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=window_start_date
            if window_action == "opened"
            else window_end_date,
            source_system="auto_enrollment_engine",
            payload=payload,
        )

    @staticmethod
    def create_enrollment_change_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        effective_date: date,
        change_type: Literal["opt_out", "rate_change", "source_change", "cancellation"],
        change_reason: Literal[
            "employee_opt_out",
            "plan_amendment",
            "compliance_correction",
            "system_correction",
        ],
        new_pre_tax_rate: Decimal,
        new_roth_rate: Decimal = Decimal("0"),
        previous_enrollment_date: Optional[date] = None,
        previous_pre_tax_rate: Optional[Decimal] = None,
        previous_roth_rate: Optional[Decimal] = None,
        within_opt_out_window: bool = False,
        penalty_applied: bool = False,
    ) -> SimulationEvent:
        """Create enrollment change event for opt-outs and modifications"""

        payload = EnrollmentChangePayload(
            plan_id=plan_id,
            change_type=change_type,
            change_reason=change_reason,
            previous_enrollment_date=previous_enrollment_date,
            new_pre_tax_rate=new_pre_tax_rate,
            new_roth_rate=new_roth_rate,
            previous_pre_tax_rate=previous_pre_tax_rate,
            previous_roth_rate=previous_roth_rate,
            within_opt_out_window=within_opt_out_window,
            penalty_applied=penalty_applied,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="enrollment_change_processing",
            payload=payload,
        )


class PlanAdministrationEventFactory(EventFactory):
    """
    Factory for creating plan administration events (S072-04).

    Provides type-safe creation methods for essential plan governance and compliance
    monitoring events including forfeiture processing, HCE determination, and basic
    IRS limit monitoring.
    """

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
        effective_date: date,
    ) -> SimulationEvent:
        """Create forfeiture event for unvested contributions"""

        payload = ForfeiturePayload(
            plan_id=plan_id,
            forfeited_from_source=forfeited_from_source,
            amount=amount,
            reason=reason,
            vested_percentage=vested_percentage,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="plan_administration",
            payload=payload,
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
        prior_year_hce: Optional[bool] = None,
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
            prior_year_hce=prior_year_hce,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=determination_date,
            source_system="hce_determination",
            payload=payload,
        )

    @staticmethod
    def create_compliance_monitoring_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        compliance_type: Literal[
            "402g_limit_approach", "415c_limit_approach", "catch_up_eligible"
        ],
        limit_type: Literal["elective_deferral", "annual_additions", "catch_up"],
        applicable_limit: Decimal,
        current_amount: Decimal,
        monitoring_date: date,
    ) -> SimulationEvent:
        """Create compliance monitoring event for limit tracking"""

        payload = ComplianceEventPayload(
            plan_id=plan_id,
            compliance_type=compliance_type,
            limit_type=limit_type,
            applicable_limit=applicable_limit,
            current_amount=current_amount,
            monitoring_date=monitoring_date,
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=monitoring_date,
            source_system="compliance_monitoring",
            payload=payload,
        )


# Backward compatibility alias
LegacySimulationEvent = SimulationEvent


__all__ = [
    # Core event model
    "SimulationEvent",
    "LegacySimulationEvent",
    # Factories
    "EventFactory",
    "WorkforceEventFactory",
    "DCPlanEventFactory",
    "PlanAdministrationEventFactory",
]
