# Epic E021: DC Plan Data Model MVP

## Epic Overview

### Summary
Establish the foundational data model and event schema for basic Defined Contribution retirement plan modeling within Fidelity PlanAlign Engine's event-sourced architecture. This MVP focuses on core functionality needed to integrate DC plan events with the existing orchestrator_mvp workflow.

### Business Value
- Creates the technical foundation for retirement plan features
- Ensures audit trail for participant account history
- Integrates seamlessly with existing workforce event stream

### Success Criteria
- ✅ Core event schema supporting basic DC plan transactions
- ✅ Integration with existing workforce event stream via orchestrator_mvp
- ✅ Basic audit trail meeting standard requirements
- ✅ Performance suitable for MVP workloads (10K employees)

---

## Dependencies

This epic builds upon the existing orchestrator_mvp infrastructure:

### Foundational Components
- **`orchestrator_mvp/core/event_emitter.py`**: Existing workforce event generation
- **`config/events.py`**: Unified event model with Pydantic v2 (S072-01 completed)
- **`fct_yearly_events`**: Existing workforce event table
- **`fct_workforce_snapshot`**: Point-in-time workforce state snapshots
- **Multi-year simulation framework**: Full 2025-2029 simulation support

### Integration Strategy
The MVP will extend the existing orchestrator_mvp pattern by:
1. Adding DC plan event generation to the existing 5-step event sequence
2. Using the same multi-year simulation framework
3. Integrating with existing dbt models and validation patterns

---

## User Stories

### ✅ Story S072-01: Core Event Model & Pydantic v2 Architecture (5 points) [COMPLETED]
**As a** platform engineer
**I want** a unified event model with Pydantic v2 discriminated unions
**So that** all workforce and DC plan events share a consistent, type-safe architecture

**Status**: ✅ **COMPLETED** (2025-07-11)
**Implementation**: `config/events.py`
**Tests**: `tests/unit/test_simulation_event.py` (20 tests, 100% pass rate)

### Story S072-02: Basic DC Plan Events (8 points)
**As a** benefits analyst
**I want** core DC plan event types for basic plan operations
**So that** we can track participant eligibility, enrollment, and contributions

**Acceptance Criteria:**
- Event types: `eligibility`, `enrollment`, `contribution`, `vesting`
- Pydantic v2 payload validation for each event type
- Integration with existing `SimulationEvent` discriminated union
- Basic validation rules (e.g., contribution amounts ≥ 0)
- Events stored in existing `fct_yearly_events` table structure

**Event Schema:**
```python
class EligibilityPayload(BaseModel):
    plan_id: str
    is_eligible: bool
    eligibility_date: date
    hours_worked_ytd: int
    service_months: int

class EnrollmentPayload(BaseModel):
    plan_id: str
    enrollment_date: date
    pre_tax_rate: float = Field(..., ge=0, le=1)
    roth_rate: float = Field(..., ge=0, le=1)

class ContributionPayload(BaseModel):
    plan_id: str
    source: Literal["employee_pre_tax", "employee_roth", "employer_match"]
    amount: Decimal
    pay_period_end: date

class VestingPayload(BaseModel):
    plan_id: str
    vested_percentage: float = Field(..., ge=0, le=1)
    service_years: int
```

### Story S072-03: Integration with orchestrator_mvp (5 points)
**As a** platform engineer
**I want** DC plan event generation integrated into the existing multi-year simulation
**So that** DC plan events are generated alongside workforce events

**Acceptance Criteria:**
- Extend `orchestrator_mvp/core/event_emitter.py` with DC plan event generation
- Add DC plan events as step 6 in the existing 5-step event sequence
- Support multi-year simulation (2025-2029) with DC plan events
- Use same random seed approach for deterministic results
- Integrate with existing validation and inspection framework

**Implementation Pattern:**
```python
# In event_emitter.py
def generate_dc_plan_events(simulation_year: int, config: dict) -> int:
    """Generate DC plan events for active workforce"""
    conn = get_connection()

    # 1. Generate eligibility events
    eligibility_count = generate_eligibility_events(simulation_year, conn)

    # 2. Generate enrollment events
    enrollment_count = generate_enrollment_events(simulation_year, conn)

    # 3. Generate contribution events
    contribution_count = generate_contribution_events(simulation_year, conn)

    return eligibility_count + enrollment_count + contribution_count
```

### Story S072-04: Basic dbt Models for DC Plan Data (8 points)
**As a** data engineer
**I want** staging and intermediate models for DC plan data
**So that** DC plan events are processed consistently with workforce events

**Acceptance Criteria:**
- `stg_dc_plan_events`: Staging model for DC plan events from `fct_yearly_events`
- `int_participant_eligibility`: Determine plan eligibility by employee and year
- `int_participant_contributions`: Aggregate contributions by source and period
- `fct_dc_plan_summary`: Final fact table with participant account summaries
- All models follow existing dbt contract patterns
- Integration with existing workforce snapshot models

**dbt Model Structure:**
```sql
-- stg_dc_plan_events.sql
SELECT
    event_id,
    employee_id,
    event_type,
    effective_date,
    simulation_year,
    event_payload
FROM {{ ref('fct_yearly_events') }}
WHERE event_type IN ('eligibility', 'enrollment', 'contribution', 'vesting')

-- int_participant_eligibility.sql
WITH eligibility_events AS (
    SELECT
        employee_id,
        simulation_year,
        JSON_EXTRACT(event_payload, '$.is_eligible') as is_eligible,
        JSON_EXTRACT(event_payload, '$.eligibility_date') as eligibility_date
    FROM {{ ref('stg_dc_plan_events') }}
    WHERE event_type = 'eligibility'
)
SELECT * FROM eligibility_events
```

### Story S072-05: Basic HCE Determination (5 points)
**As a** plan administrator
**I want** basic HCE (Highly Compensated Employee) determination
**So that** we can identify HCEs for basic compliance purposes

**Acceptance Criteria:**
- HCE determination based on annual compensation threshold ($160,000 for 2025)
- Integration with existing workforce compensation data
- Support for both current-year and prior-year determination methods
- dbt model: `int_hce_determination`
- Basic validation tests

**HCE Logic:**
```sql
-- int_hce_determination.sql
WITH employee_compensation AS (
    SELECT
        employee_id,
        simulation_year,
        SUM(gross_compensation) as annual_compensation
    FROM {{ ref('fct_workforce_snapshot') }}
    GROUP BY employee_id, simulation_year
)
SELECT
    employee_id,
    simulation_year,
    annual_compensation,
    CASE
        WHEN annual_compensation >= 160000 THEN true
        ELSE false
    END as is_hce
FROM employee_compensation
```

### Story S072-06: Basic IRS Compliance Validation (8 points)
**As a** compliance officer
**I want** basic IRS limit validation for employee contributions
**So that** we can prevent basic limit violations

**Acceptance Criteria:**
- Validate 402(g) elective deferral limits ($23,500 for 2025)
- Validate catch-up contributions for employees age 50+
- Basic limit enforcement in contribution events
- dbt model: `int_contribution_compliance`
- Warning alerts when approaching limits

**Compliance Logic:**
```sql
-- int_contribution_compliance.sql
WITH employee_deferrals AS (
    SELECT
        employee_id,
        simulation_year,
        SUM(CASE WHEN source IN ('employee_pre_tax', 'employee_roth')
            THEN amount ELSE 0 END) as total_deferrals
    FROM {{ ref('stg_dc_plan_events') }}
    WHERE event_type = 'contribution'
    GROUP BY employee_id, simulation_year
),
age_calculation AS (
    SELECT
        e.employee_id,
        e.simulation_year,
        e.total_deferrals,
        w.birth_date,
        YEAR(CURRENT_DATE) - YEAR(w.birth_date) as current_age,
        CASE WHEN YEAR(CURRENT_DATE) - YEAR(w.birth_date) >= 50
             THEN 31000 ELSE 23500 END as applicable_limit
    FROM employee_deferrals e
    JOIN {{ ref('int_baseline_workforce') }} w ON e.employee_id = w.employee_id
)
SELECT
    *,
    CASE
        WHEN total_deferrals > applicable_limit THEN 'VIOLATION'
        WHEN total_deferrals >= applicable_limit * 0.95 THEN 'WARNING'
        ELSE 'COMPLIANT'
    END as compliance_status
FROM age_calculation
```

---

## Technical Implementation

### Event Generation Integration
DC plan events will be generated as part of the existing multi-year simulation workflow:

```python
# In multi_year_simulation.py
def run_single_year_simulation(year: int, config: dict) -> dict:
    """Extended to include DC plan events"""

    # Existing workforce events (steps 1-5)
    termination_events = generate_termination_events(year, config)
    hire_events = generate_hire_events(year, config)
    new_hire_termination_events = generate_new_hire_termination_events(year, config)
    merit_events = generate_merit_events(year, config)
    promotion_events = generate_promotion_events(year, config)

    # NEW: DC plan events (step 6)
    dc_plan_events = generate_dc_plan_events(year, config)

    # Generate workforce snapshot
    snapshot_result = generate_workforce_snapshot(year, config)

    return {
        'workforce_events': termination_events + hire_events + new_hire_termination_events + merit_events + promotion_events,
        'dc_plan_events': dc_plan_events,
        'snapshot': snapshot_result
    }
```

### Configuration Extensions
Add DC plan parameters to existing `config/simulation_config.yaml`:

```yaml
# Existing workforce parameters
workforce:
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25

# NEW: DC plan parameters
dc_plan:
  eligibility_requirements:
    minimum_age: 21
    minimum_service_months: 12
    hours_requirement: 1000

  contribution_rates:
    default_pre_tax_rate: 0.06
    default_roth_rate: 0.00
    max_deferral_rate: 0.50

  matching:
    formula: "100% on first 3%"
    max_match_percentage: 0.03

  compliance:
    hce_threshold: 160000  # 2025 limit
    employee_deferral_limit: 23500  # 2025 limit
    catch_up_limit: 7500  # 2025 limit
```

### Database Schema Extensions
Extend existing tables to support DC plan events:

```sql
-- Extend fct_yearly_events to include DC plan event types
-- This uses the existing table structure, just adds new event_type values:
-- 'eligibility', 'enrollment', 'contribution', 'vesting'

-- New models will reference existing tables:
-- int_baseline_workforce -> provides employee demographics
-- fct_workforce_snapshot -> provides compensation data
-- fct_yearly_events -> stores all events including DC plan events
```

---

## Performance Requirements (MVP)

| Metric | MVP Requirement | Implementation |
|--------|-----------------|----------------|
| Employee Capacity | 10,000 employees | Use existing orchestrator_mvp patterns |
| Event Processing | <5 minutes per simulation year | Extend existing event generation |
| Multi-Year Simulation | 2025-2029 in <30 minutes | Use existing multi-year framework |
| Memory Usage | <4GB total | Follow existing memory-efficient patterns |

---

## Testing Strategy

### Unit Tests
- Event payload validation using existing patterns
- HCE determination logic
- Basic compliance validation
- Integration with existing event_emitter tests

### Integration Tests
- Full multi-year simulation with DC plan events
- dbt model data quality tests
- Integration with existing workforce events

### Example Test:
```python
def test_dc_plan_event_generation():
    """Test DC plan events are generated correctly"""
    config = load_test_config()

    # Generate DC plan events for 2025
    event_count = generate_dc_plan_events(2025, config)

    # Verify events were created
    assert event_count > 0

    # Verify event types
    conn = get_connection()
    result = conn.execute("""
        SELECT DISTINCT event_type
        FROM fct_yearly_events
        WHERE simulation_year = 2025
        AND event_type IN ('eligibility', 'enrollment', 'contribution')
    """).fetchall()

    assert len(result) >= 3  # At least 3 event types generated
```

---

## Dependencies & Risks

### Dependencies
- Existing orchestrator_mvp framework
- Completed S072-01 (Core Event Model)
- Employee master data from workforce simulation
- Basic IRS limit values (hardcoded for MVP)

### Risks & Mitigations
- **Risk**: Performance impact on multi-year simulation
- **Mitigation**: Use existing patterns, profile performance, optimize incrementally

- **Risk**: Complex integration with existing events
- **Mitigation**: Extend existing patterns rather than replacing them

---

## Definition of Done

- [ ] **Story S072-02**: Basic DC plan events implemented and tested
- [ ] **Story S072-03**: Integration with orchestrator_mvp complete
- [ ] **Story S072-04**: Basic dbt models created with contracts
- [ ] **Story S072-05**: HCE determination working
- [ ] **Story S072-06**: Basic IRS compliance validation
- [ ] **Integration**: Multi-year simulation (2025-2029) works with DC plan events
- [ ] **Testing**: All unit and integration tests pass
- [ ] **Performance**: MVP performance requirements met
- [ ] **Documentation**: Updated orchestrator_mvp documentation

**Total Story Points**: 39 points
**Estimated Duration**: 3-4 sprints

---

## Future Enhancements (Moved to E021-B)

The following items have been moved to Epic E021-B (Advanced DC Plan Features):
- ERISA compliance review and documentation
- True-up calculation engine with complex matching formulas
- Loan & investment events
- Advanced plan administration events (forfeitures, distributions)
- Regulatory limits service with versioning
- Data encryption & PII security framework
- Scenario isolation architecture
- Performance optimization with Polars
- Advanced compliance enforcement engine

This MVP provides a solid foundation for DC plan modeling while maintaining focus on core functionality and integration with the existing orchestrator_mvp framework.
