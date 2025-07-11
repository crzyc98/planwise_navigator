# Story S072-01: Core Event Model & Pydantic v2 Architecture

**Epic**: E021-A - DC Plan Event Schema Foundation
**Story Points**: 5
**Priority**: High
**Sprint**: 1
**Owner**: Platform Team

## Story

**As a** platform engineer
**I want** a unified event model with Pydantic v2 discriminated unions
**So that** all workforce and DC plan events share a consistent, type-safe architecture

## Business Context

This foundational story establishes the core event architecture that will support all DC plan operations. It replaces the current dual event model confusion with a single, unified `SimulationEvent` model using Pydantic v2's discriminated union pattern. This creates the technical foundation that all other event types will build upon.

## Acceptance Criteria

### Core Architecture
- [ ] **Single `SimulationEvent` model** implemented with Pydantic v2 `ConfigDict`
- [ ] **Discriminated union pattern** working correctly with `event_type` discriminator
- [ ] **Required context fields** enforced: `scenario_id`, `plan_design_id` (no Optional)
- [ ] **Base event infrastructure** supporting all 18 planned event types

### Type Safety & Validation
- [ ] **Pydantic v2 compatibility** with proper imports and syntax
- [ ] **Runtime type validation** working with `model_validate()` method
- [ ] **Schema serialization** working with `model_dump()` method
- [ ] **Field validation** working with `field_validator` decorators

### Development Standards
- [ ] **No untyped Dict patterns** - all `Optional[Dict[str, Any]]` eliminated
- [ ] **Decimal precision** set to `Decimal(18,6)` for monetary amounts
- [ ] **UUID generation** working for `event_id` field
- [ ] **Timestamp generation** working for `created_at` field

## Technical Specifications

### Core Event Model

```python
from typing import Annotated, Union, Optional
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

    # Discriminated union payload (to be expanded in subsequent stories)
    payload: Union[
        # Placeholder for all 18 event types
        # Will be populated in S072-02 through S072-05
    ] = Field(..., discriminator='event_type')

    # Optional correlation for event tracing
    correlation_id: Optional[str] = None
```

### EventFactory Pattern

```python
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
```

### Base Payload Pattern

```python
from typing import Literal
from pydantic import BaseModel

class BaseEventPayload(BaseModel):
    """Base class for all event payloads"""

    model_config = ConfigDict(
        extra='forbid',
        use_enum_values=True
    )

    # Every payload must have event_type for discriminator
    event_type: str  # Will be Literal in concrete implementations
```

## Implementation Tasks

### Phase 1: Core Model Setup
- [ ] **Create `SimulationEvent` class** with proper Pydantic v2 syntax
- [ ] **Implement required fields** with validation (scenario_id, plan_design_id)
- [ ] **Add ConfigDict configuration** with extra='forbid', use_enum_values=True
- [ ] **Set up UUID and timestamp generation** with proper defaults

### Phase 2: Validation Framework
- [ ] **Implement EventFactory** with model_validate() method
- [ ] **Add schema validation** utilities for runtime checking
- [ ] **Create BaseEventPayload** class for inheritance pattern
- [ ] **Add field validators** for employee_id, scenario_id validation

### Phase 3: Testing & Documentation
- [ ] **Create comprehensive unit tests** for core model functionality
- [ ] **Test Pydantic v2 features** (model_validate, model_dump, field_validator)
- [ ] **Validate discriminator pattern** works correctly
- [ ] **Document architecture decisions** and usage patterns

## Dependencies

### Technical Dependencies
- **Pydantic 2.7.4+** for enhanced type safety
- **Python 3.11+** for proper typing support
- **UUID library** for unique event identification
- **Decimal library** for monetary precision

### Story Dependencies
- **None** (foundational story)

## Blocking Dependencies for Other Stories
- **S072-02**: Workforce Event Integration (needs core model)
- **S072-03**: Core DC Plan Events (needs core model)
- **S072-04**: Plan Administration Events (needs core model)
- **S072-05**: Loan & Investment Events (needs core model)

## Success Metrics

### Functionality
- [ ] **Model instantiation**: Core model creates instances successfully
- [ ] **Type validation**: Pydantic v2 validation catches type errors
- [ ] **Serialization**: Model dumps to JSON correctly
- [ ] **Factory pattern**: EventFactory creates valid events

### Performance
- [ ] **Schema validation**: <5ms per event validation
- [ ] **Memory efficiency**: <100MB for 10K event instances
- [ ] **Serialization speed**: <1ms per event serialization

## Testing Strategy

### Unit Tests
- [ ] **Model creation** with valid/invalid data
- [ ] **Field validation** for all required fields
- [ ] **ConfigDict behavior** (extra='forbid', validation)
- [ ] **UUID/timestamp generation** correctness

### Integration Tests
- [ ] **EventFactory usage** in realistic scenarios
- [ ] **Discriminator pattern** preparation for payload types
- [ ] **Serialization/deserialization** round-trip testing

## Definition of Done

- [ ] **Core SimulationEvent model** implemented with Pydantic v2
- [ ] **All acceptance criteria met** with comprehensive testing
- [ ] **EventFactory pattern** working correctly
- [ ] **Documentation complete** with usage examples
- [ ] **Unit tests passing** with >95% coverage
- [ ] **Code review approved** following PlanWise patterns
- [ ] **Ready for payload integration** in subsequent stories

## Notes

This story creates the architectural foundation for the entire DC plan event system. All subsequent stories (S072-02 through S072-05) will extend the discriminated union with specific payload types. The design prioritizes type safety, performance, and enterprise-grade validation while maintaining backward compatibility with existing workforce events.
