# Story S072-02: Workforce Event Integration

**Epic**: E021-A - DC Plan Event Schema Foundation
**Story Points**: 3
**Priority**: High
**Sprint**: 1
**Owner**: Platform Team

## Story

**As a** platform engineer
**I want** existing workforce events integrated into the unified event model
**So that** hire, promotion, termination, and merit events work seamlessly with DC plan events

## Business Context

This story ensures backward compatibility by integrating the existing workforce simulation events (hire, promotion, termination, merit) into the new unified event architecture. This maintains existing functionality while preparing for DC plan event expansion.

## Acceptance Criteria

### Workforce Event Integration
- [ ] **All 4 workforce events** integrated: hire, promotion, termination, merit
- [ ] **Backward compatibility maintained** with existing workforce simulation
- [ ] **Enhanced payloads** with optional `plan_id` field for DC plan linking
- [ ] **Discriminated union integration** working with core SimulationEvent model

### Enhanced Event Coverage
- [ ] **HirePayload** includes plan eligibility context
- [ ] **PromotionPayload** includes compensation impact for HCE determination
- [ ] **TerminationPayload** includes reason codes for distribution processing
- [ ] **MeritPayload** includes percentage tracking for compliance calculations

## Technical Specifications

### Workforce Event Payloads

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal

class HirePayload(BaseModel):
    """Employee onboarding with plan eligibility context"""

    event_type: Literal["hire"] = "hire"
    plan_id: Optional[str] = None  # Links to DC plan when applicable
    hire_date: date
    department: str = Field(..., min_length=1)
    job_level: int = Field(..., ge=1, le=10)
    annual_compensation: Decimal = Field(..., gt=0, decimal_places=6)

class PromotionPayload(BaseModel):
    """Level changes affecting contribution capacity and HCE status"""

    event_type: Literal["promotion"] = "promotion"
    plan_id: Optional[str] = None
    new_job_level: int = Field(..., ge=1, le=10)
    new_annual_compensation: Decimal = Field(..., gt=0, decimal_places=6)
    effective_date: date

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
    new_compensation: Decimal = Field(..., gt=0, decimal_places=6)
    merit_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)
```

### Updated SimulationEvent Model

```python
# Extending the core model from S072-01
class SimulationEvent(BaseModel):
    # ... core fields from S072-01 ...

    # Updated discriminated union with workforce events
    payload: Union[
        Annotated[HirePayload, Field(discriminator='event_type')],
        Annotated[PromotionPayload, Field(discriminator='event_type')],
        Annotated[TerminationPayload, Field(discriminator='event_type')],
        Annotated[MeritPayload, Field(discriminator='event_type')],
        # Placeholder for DC plan events (S072-03, S072-04, S072-05)
    ] = Field(..., discriminator='event_type')
```

### Workforce Event Factory

```python
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
```

## Implementation Tasks

### Phase 1: Payload Implementation
- [ ] **Create 4 workforce payload classes** with proper Literal event_type
- [ ] **Add optional plan_id field** to all workforce payloads
- [ ] **Implement field validation** for compensation, job_level, dates
- [ ] **Add termination_reason enum** with 5 specific values

### Phase 2: Integration with Core Model
- [ ] **Extend SimulationEvent discriminated union** with workforce payloads
- [ ] **Test discriminator pattern** works correctly for all 4 types
- [ ] **Validate Pydantic v2 compatibility** with Annotated types
- [ ] **Ensure backward compatibility** with existing workforce data

### Phase 3: Factory Methods
- [ ] **Create WorkforceEventFactory** with helper methods
- [ ] **Implement factory methods** for all 4 workforce event types
- [ ] **Add validation logic** in factory methods
- [ ] **Test factory integration** with core SimulationEvent

## Dependencies

### Story Dependencies
- **S072-01**: Core Event Model & Pydantic v2 Architecture (blocking)

### Technical Dependencies
- **Existing workforce simulation** data structures
- **Current employee demographic** data model
- **Compensation calculation** logic

## Success Metrics

### Functionality
- [ ] **All workforce events working** in unified model
- [ ] **Existing simulations compatible** with new event structure
- [ ] **Plan linking functional** when plan_id provided
- [ ] **Event serialization working** for all 4 payload types

### Integration
- [ ] **Zero breaking changes** to existing workforce simulation
- [ ] **Smooth migration path** from old to new event model
- [ ] **Performance maintained** for workforce operations

## Testing Strategy

### Unit Tests
- [ ] **Each payload type** creation and validation
- [ ] **Field validation** for all required/optional fields
- [ ] **Event_type discriminator** working correctly
- [ ] **Factory methods** creating valid events

### Integration Tests
- [ ] **Existing workforce simulation** still works
- [ ] **Plan_id linking** when DC plan context available
- [ ] **Serialization/deserialization** round-trip testing
- [ ] **Discriminated union** routing to correct payload type

### Backward Compatibility Tests
- [ ] **Existing workforce data** loads correctly
- [ ] **Current simulation pipeline** unchanged
- [ ] **Event processing** maintains same behavior
- [ ] **Performance characteristics** unchanged

## Definition of Done

- [ ] **All 4 workforce payloads** implemented and tested
- [ ] **SimulationEvent discriminated union** includes workforce events
- [ ] **WorkforceEventFactory** provides convenient creation methods
- [ ] **Backward compatibility verified** with existing workforce simulation
- [ ] **Integration tests passing** for all workforce scenarios
- [ ] **Documentation updated** with workforce event examples
- [ ] **Code review approved** with platform team validation

## Migration Strategy

### Gradual Migration
1. **New events** use unified SimulationEvent model
2. **Existing events** continue working with legacy format
3. **Migration utility** converts legacy events to new format
4. **Validation period** ensures both formats work
5. **Cutover** to unified model after validation

### Data Compatibility
- **Optional plan_id** allows gradual DC plan integration
- **Same field names** maintain compatibility where possible
- **Enhanced validation** improves data quality
- **Factory methods** provide consistent event creation

## Notes

This story maintains the existing workforce simulation functionality while preparing the foundation for DC plan events. The optional `plan_id` field allows gradual integration with retirement plan features without breaking existing workforce-only simulations.
