# Story S022-01: Core Eligibility Calculator (MVP)

## Story Overview

### Summary
Build a vectorized eligibility calculator that processes 100K+ employees in <30 seconds using pandas DataFrame operations. This MVP implementation focuses on the most common eligibility patterns while deferring complex edge cases.

### Business Value
- Automates eligibility determination for 95% of standard cases
- Reduces manual HR processing time by 80%
- Ensures consistent application of eligibility rules

### Acceptance Criteria
- ✅ Process 100K employees in <30 seconds using vectorized operations
- ✅ Evaluate age requirements (18 or 21 minimum)
- ✅ Evaluate service requirements (0, 6, or 12 months)
- ✅ Simple hours check (0 or 1000 annual hours minimum)
- ✅ Generate ELIGIBILITY events with proper event model integration
- ✅ Support configuration via YAML without code changes

## Technical Specifications

### Implementation Approach (Updated)
**Key Change**: Use dbt/SQL for maximum performance instead of pandas operations.

```sql
-- dbt/models/intermediate/int_eligibility_determination.sql
{{ config(materialized='table') }}

WITH employees AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_type,
        annual_hours,
        current_age,
        current_tenure,
        level_id,
        employment_status
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
),

eligibility_checks AS (
    SELECT
        *,
        -- Age eligibility check
        current_age >= {{ var('minimum_age', 21) }} as is_age_eligible,

        -- Service eligibility check (elapsed time method)
        current_tenure >= {{ var('minimum_service_months', 12) }} as is_service_eligible,

        -- Hours eligibility check
        annual_hours >= {{ var('minimum_hours_annual', 1000) }} as is_hours_eligible,

        -- Employee type exclusions
        employee_type NOT IN ({{ var('excluded_employee_types', "('intern', 'contractor')") }}) as is_classification_eligible

    FROM employees
),

final_eligibility AS (
    SELECT
        *,
        (is_age_eligible AND is_service_eligible AND is_hours_eligible AND is_classification_eligible) as is_eligible,

        -- Determine specific reason for ineligibility
        CASE
            WHEN NOT is_classification_eligible THEN 'excluded:' || employee_type
            WHEN NOT is_age_eligible THEN 'pending_age'
            WHEN NOT is_service_eligible THEN 'pending_service'
            WHEN NOT is_hours_eligible THEN 'pending_hours'
            ELSE 'eligible'
        END as eligibility_reason

    FROM eligibility_checks
)

SELECT * FROM final_eligibility
```

### Integration Pattern (No Events Generated)
**Key Change**: Don't generate eligibility events - use eligibility as a filter in other event generation.

```python
# orchestrator_mvp/core/eligibility_engine.py
def apply_eligibility_filter(self, event_type: str, simulation_year: int) -> str:
    """Return SQL WHERE clause for eligibility filtering"""
    eligibility_table = "int_eligibility_determination"

    return f"""
        employee_id IN (
            SELECT employee_id
            FROM {eligibility_table}
            WHERE simulation_year = {simulation_year}
            AND is_eligible = true
        )
    """

# Usage in existing event generation
def generate_promotion_events_with_eligibility(simulation_year: int) -> List[Dict]:
    eligibility_engine = EligibilityEngine()
    eligibility_filter = eligibility_engine.apply_eligibility_filter('promotion', simulation_year)

    query = f"""
        SELECT * FROM int_baseline_workforce
        WHERE employment_status = 'active'
        AND level_id < 5
        AND {eligibility_filter}
    """
    # Continue with existing promotion logic...
```

### Integration Points
1. **Data Source**: Uses `int_baseline_workforce` or `fct_workforce_snapshot`
2. **dbt Model**: Creates `int_eligibility_determination` table for filtering
3. **Configuration**: Uses dbt variables instead of separate YAML file
4. **Orchestration**: Run as dbt model, then used as filter in event generation
5. **No Event Storage**: Eligibility used as filter, not stored as events

## MVP Simplifications

### Included in MVP
- Basic age check (single minimum age)
- Simple service calculation (elapsed time only)
- Annual hours threshold (basic check)
- Immediate and quarterly entry dates
- Single set of rules for all employees

### Deferred to Post-MVP
- Multiple service computation methods
- Breaks in service handling
- Complex rehire rules
- Hours counting method with period tracking
- Multiple eligibility tracks (401k vs match)
- Advance notifications

## Test Scenarios

1. **Standard Eligibility**: Employee meets all requirements
2. **Age Failure**: Employee under minimum age
3. **Service Failure**: Employee hasn't met service requirement
4. **Hours Failure**: Part-time employee under hours threshold
5. **Bulk Processing**: 100K employee performance test

## Story Points: 8

### Effort Breakdown
- Core eligibility logic: 3 points
- Vectorization optimization: 2 points
- Event generation: 2 points
- Testing: 1 point

## Dependencies
- Existing event model (EligibilityPayload in config/events.py)
- Workforce data models (int_baseline_workforce)
- Event storage infrastructure (fct_yearly_events)

## Definition of Done
- [ ] Eligibility engine processes 100K employees in <30 seconds
- [ ] All basic eligibility rules implemented
- [ ] Events generated in correct format
- [ ] Unit tests achieve 95% coverage
- [ ] Integration test with orchestrator_mvp
- [ ] Performance benchmark documented
