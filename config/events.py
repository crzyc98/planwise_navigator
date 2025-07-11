# filename: config/events.py
"""Unified event model with Pydantic v2 discriminated unions for DC plan and workforce events."""

from typing import Annotated, Union, Optional, Any, Literal
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
        Annotated[HirePayload, Field(discriminator='event_type')],
        Annotated[PromotionPayload, Field(discriminator='event_type')],
        Annotated[TerminationPayload, Field(discriminator='event_type')],
        Annotated[MeritPayload, Field(discriminator='event_type')],
        # Placeholder for DC plan events (S072-03, S072-04, S072-05)
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
        termination_reason: Literal["voluntary", "involuntary", "retirement", "death", "disability"],
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


# Backward compatibility: Alias for migration from legacy SimulationEvent
LegacySimulationEvent = SimulationEvent
