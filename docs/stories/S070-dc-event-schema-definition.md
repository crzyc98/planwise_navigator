# Story S070: Define Retirement Plan Event Schema

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 13
**Priority**: High
**Status**: Ready for Development

## User Story
**As a** platform architect
**I want** comprehensive event types for all DC plan activities
**So that** we can track every participant interaction and calculation

## Context
This story establishes the foundational event schema for all DC plan operations. Every subsequent feature will build upon these event types, making it critical to get the schema right from the start.

## Acceptance Criteria
1. **Event Type Definition**
   - Create enum for all DC plan event types
   - Include: ELIGIBILITY_START, ENROLLMENT, DEFERRAL_CHANGE, CONTRIBUTION, MATCH_CALCULATION, DISTRIBUTION, LOAN
   - Each event type has clear documentation

2. **Event Schema Structure**
   - Extends base RetirementPlanEvent class
   - Includes all required fields: event_id, employee_id, event_type, effective_date, plan_year
   - Supports flexible details field for event-specific data
   - Includes audit fields: created_at, source_system

3. **Data Validation**
   - Schema enforces required fields
   - Date validations (effective_date cannot be future)
   - Amount validations (non-negative for contributions)
   - Employee ID foreign key validation

4. **Integration Points**
   - Compatible with existing event sourcing infrastructure
   - Can be serialized/deserialized for event stream
   - Supports event replay functionality

## Technical Details

### Event Schema Implementation
```python
from enum import Enum
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import UUID

class RetirementEventType(Enum):
    # Eligibility Events
    ELIGIBILITY_START = "eligibility_start"
    ELIGIBILITY_END = "eligibility_end"

    # Enrollment Events
    ENROLLMENT = "enrollment"
    DEFERRAL_CHANGE = "deferral_change"
    OPT_OUT = "opt_out"

    # Contribution Events
    CONTRIBUTION = "contribution"
    MATCH_CALCULATION = "match_calculation"
    TRUE_UP = "true_up"

    # Distribution Events
    DISTRIBUTION = "distribution"
    ROLLOVER_IN = "rollover_in"
    ROLLOVER_OUT = "rollover_out"

    # Loan Events
    LOAN_INITIATION = "loan_initiation"
    LOAN_PAYMENT = "loan_payment"
    LOAN_DEFAULT = "loan_default"

@dataclass
class RetirementPlanEvent:
    event_id: UUID
    employee_id: str
    event_type: RetirementEventType
    effective_date: date
    plan_year: int
    amount: Optional[Decimal] = None
    details: Dict[str, Any] = None
    created_at: datetime = None
    source_system: str = "planalign_engine"

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.details is None:
            self.details = {}

    def validate(self):
        """Validate event data integrity"""
        if self.effective_date > date.today():
            raise ValueError("Effective date cannot be in future")

        if self.amount is not None and self.amount < 0:
            raise ValueError("Amount cannot be negative")

        if self.plan_year < 2020 or self.plan_year > 2050:
            raise ValueError("Invalid plan year")
```

### Event Examples
```python
# Enrollment Event
enrollment_event = RetirementPlanEvent(
    event_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
    employee_id="EMP001",
    event_type=RetirementEventType.ENROLLMENT,
    effective_date=date(2025, 1, 1),
    plan_year=2025,
    details={
        "enrollment_type": "auto",
        "deferral_rate": 0.03,
        "investment_elections": {
            "target_date_2050": 1.0
        }
    }
)

# Contribution Event
contribution_event = RetirementPlanEvent(
    event_id=UUID("550e8400-e29b-41d4-a716-446655440001"),
    employee_id="EMP001",
    event_type=RetirementEventType.CONTRIBUTION,
    effective_date=date(2025, 1, 15),
    plan_year=2025,
    amount=Decimal("500.00"),
    details={
        "pay_period_start": "2025-01-01",
        "pay_period_end": "2025-01-15",
        "contribution_type": "pretax",
        "gross_compensation": Decimal("5000.00"),
        "ytd_contributions": Decimal("500.00")
    }
)
```

## Testing Requirements
1. **Unit Tests**
   - Event creation and validation
   - Schema enforcement
   - Serialization/deserialization

2. **Integration Tests**
   - Event stream publishing
   - Event retrieval and replay
   - Foreign key constraints

3. **Performance Tests**
   - Event creation performance (target: <1ms)
   - Bulk event processing (target: 10K events/second)

## Implementation Notes
- Event IDs should be UUIDs for global uniqueness
- All monetary amounts use Decimal type for precision
- Details field allows extensibility without schema changes
- Consider adding event versioning for future migrations

## Dependencies
- Base event sourcing infrastructure must be in place
- Employee master data model must exist

## Definition of Done
- [ ] Event schema implemented and documented
- [ ] All event types have example usage
- [ ] Unit tests achieve 100% coverage
- [ ] Integration tests pass
- [ ] Performance benchmarks met
- [ ] Code review completed
- [ ] Documentation updated
