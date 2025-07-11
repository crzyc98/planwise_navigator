# filename: config/events.py
"""Unified event model with Pydantic v2 discriminated unions for DC plan and workforce events."""

from typing import Annotated, Union, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4


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

    # Note: Discriminated union payload will be added in subsequent stories (S072-02 through S072-05)
    # For now, we support direct event metadata without payload discrimination
    # This maintains compatibility during the foundation phase

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
        return SimulationEvent(
            employee_id=employee_id,
            effective_date=effective_date,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            source_system=source_system,
            correlation_id=correlation_id
        )


# Backward compatibility: Alias for migration from legacy SimulationEvent
LegacySimulationEvent = SimulationEvent
