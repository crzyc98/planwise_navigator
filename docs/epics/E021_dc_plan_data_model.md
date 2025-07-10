# Epic E021: DC Plan Data Model & Events

## Epic Overview

### Summary
Establish the foundational data model and event schema for Defined Contribution retirement plan modeling within PlanWise Navigator's event-sourced architecture.

### Business Value
- Creates the technical foundation for all retirement plan features
- Ensures compliance with SOX audit requirements through immutable event logging
- Enables complete reconstruction of participant account history

### Success Criteria
- ✅ Complete event schema supporting all DC plan transactions
- ✅ Integration with existing workforce event stream
- ✅ Audit trail meeting ERISA compliance requirements
- ✅ Performance benchmarks met for event processing

---

## User Stories

### Story 1: Define Retirement Plan Event Schema (13 points)
**As a** platform architect
**I want** comprehensive event types for all DC plan activities
**So that** we can track every participant interaction and calculation

**Acceptance Criteria:**
- Event types cover: eligibility, enrollment, contributions, distributions
- Each event includes employee_id, timestamp, plan_year, and details
- Events are immutable once written
- Schema supports future extensibility

### Story 2: Extend dbt Models for Plan Data (8 points)
**As a** data engineer
**I want** staging and intermediate models for plan configuration
**So that** downstream models can access plan rules and parameters

**Acceptance Criteria:**
- New staging models for plan_design and irs_limits
- Intermediate models for effective plan parameters
- Integration with existing employee dimension tables

### Story 3: Create Plan Configuration Schema (5 points)
**As a** benefits analyst
**I want** YAML schema for plan design parameters
**So that** I can configure plans without code changes

**Acceptance Criteria:**
- YAML schema supports all common 401(k) features
- Validation ensures configuration integrity
- Documentation includes examples for common plans

### Story 4: Implement Event Validation Framework (8 points)
**As a** compliance officer
**I want** automated validation of plan events
**So that** we catch data quality issues before they impact calculations

**Acceptance Criteria:**
- Events validated against business rules
- Invalid events quarantined with error details
- Daily data quality reports generated
- Alert on validation failure rates >1%

---

## Technical Specifications

### Event Schema
```python
@dataclass
class RetirementPlanEvent:
    event_id: str  # UUID
    employee_id: str
    event_type: RetirementEventType
    effective_date: date
    plan_year: int
    amount: Optional[Decimal]
    details: Dict[str, Any]
    created_at: datetime
    source_system: str
```

### Plan Configuration
```yaml
plan_config:
  plan_id: "401k_standard"
  plan_year: 2025
  plan_type: "401(k)"

  features:
    roth: enabled
    after_tax: enabled
    catch_up: enabled
    loans: disabled

  limits:
    employee_deferral: 23000
    catch_up: 7500
    annual_additions: 69000
```

---

## Dependencies
- Existing event sourcing infrastructure
- Employee master data from workforce simulation
- IRS limit tables (annual updates required)

## Risks
- **Risk**: Complex ERISA compliance requirements
- **Mitigation**: Partner with benefits counsel for validation

## Estimated Effort
**Total Story Points**: 34 points
**Estimated Duration**: 2 sprints

---

## Definition of Done
- [ ] All event types implemented and tested
- [ ] dbt models passing all tests
- [ ] YAML configuration validated
- [ ] Performance benchmarks met
- [ ] Documentation complete
- [ ] Code reviewed and approved
