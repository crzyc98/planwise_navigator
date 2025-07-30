# Story S022-01: Core Eligibility Calculator (Ultra-Simplified MVP)

## Story Overview

### Summary
Build a simple eligibility calculator that determines employee eligibility based on days of service since hire date. Generate ELIGIBILITY events for employees who meet the waiting period. No entry date processing needed - just eligibility determination and event generation.

### Business Value
- Automates the most common eligibility pattern (waiting period after hire)
- Generates audit trail of eligibility events
- Provides flexible configuration (0 days = immediate, 365 days = 1 year wait)

### Acceptance Criteria
- ✅ Process 100K employees in <30 seconds using SQL/dbt operations
- ✅ Evaluate service requirements in days since hire date
- ✅ Configuration via simulation_config.yaml (eligibility.waiting_period_days)
- ✅ Generate ELIGIBILITY events for newly eligible employees
- ✅ Track eligibility status changes in event stream

## Technical Specifications

### Implementation Approach (Simplified)
**Key Change**: Focus only on days-based eligibility with configurable waiting period.

```python
# orchestrator_mvp/core/eligibility_engine.py
class EligibilityEngine:
    def __init__(self, config):
        self.config = config
        self.waiting_period_days = config['eligibility']['waiting_period_days']

    def determine_eligibility(self, simulation_year: int, duckdb_conn) -> pd.DataFrame:
        """Determine eligibility for all active employees"""

        query = f"""
        SELECT
            employee_id,
            employee_hire_date,
            employment_status,
            DATEDIFF('day', employee_hire_date, DATE('{simulation_year}-01-01')) as days_since_hire,
            DATEDIFF('day', employee_hire_date, DATE('{simulation_year}-01-01')) >= {self.waiting_period_days} as is_eligible,
            CASE
                WHEN DATEDIFF('day', employee_hire_date, DATE('{simulation_year}-01-01')) >= {self.waiting_period_days} THEN 'eligible'
                ELSE 'pending_service'
            END as eligibility_reason
        FROM int_baseline_workforce
        WHERE employment_status = 'active'
        """

        return duckdb_conn.execute(query).df()
```

### Integration Pattern (Pure Eligibility Events)
**Key Change**: Generate ELIGIBILITY events for employees who meet the waiting period requirement. No entry date processing.

```python
# orchestrator_mvp/core/eligibility_engine.py
def generate_eligibility_events(self, simulation_year: int) -> List[Dict]:
    """Generate ELIGIBILITY events for newly eligible employees"""

    # Find employees who became eligible this year
    query = f"""
    WITH current_eligibility AS (
        SELECT employee_id, is_eligible, eligibility_reason, days_since_hire
        FROM int_eligibility_determination
        WHERE simulation_year = {simulation_year}
    ),
    previous_eligibility AS (
        SELECT employee_id, is_eligible as was_eligible
        FROM int_eligibility_determination
        WHERE simulation_year = {simulation_year - 1}
    )
    SELECT
        c.employee_id,
        c.eligibility_reason,
        c.days_since_hire,
        COALESCE(p.was_eligible, false) as was_previously_eligible
    FROM current_eligibility c
    LEFT JOIN previous_eligibility p ON c.employee_id = p.employee_id
    WHERE c.is_eligible = true
    AND COALESCE(p.was_eligible, false) = false
    """

    newly_eligible_df = self.duckdb_conn.execute(query).df()

    events = []
    for _, row in newly_eligible_df.iterrows():
        event = {
            "event_type": "ELIGIBILITY",
            "employee_id": row['employee_id'],
            "simulation_year": simulation_year,
            "event_date": f"{simulation_year}-01-01",
            "event_payload": {
                "eligibility_type": "plan_participation",
                "previous_status": "ineligible",
                "new_status": "eligible",
                "days_since_hire": int(row['days_since_hire']),
                "waiting_period_days": self.config.eligibility_waiting_days
            }
        }
        events.append(event)

    return events

# Simple usage - just generate eligibility events
def process_eligibility_for_year(simulation_year: int) -> List[Dict]:
    eligibility_engine = EligibilityEngine()
    return eligibility_engine.generate_eligibility_events(simulation_year)
```

### Integration Points
1. **Data Source**: Uses `int_baseline_workforce` (employee_id, hire_date, employment_status)
2. **Configuration**: Uses `config/simulation_config.yaml` → `eligibility.waiting_period_days`
3. **Processing**: Python-based eligibility engine with SQL queries
4. **Event Generation**: Creates ELIGIBILITY events for newly eligible employees
5. **Event Storage**: Store in fct_yearly_events for audit trail
6. **Integration**: Works with orchestrator_mvp multi-year simulation framework via `orchestrator_mvp/run_multi_year.py`

## MVP Simplifications

### Included in MVP
- Days since hire calculation
- Configurable waiting period (0 = immediate, 365 = 1 year)
- Single eligibility rule for all active employees
- ELIGIBILITY event generation for newly eligible employees
- Pure eligibility determination (no entry dates)

### Deferred to Post-MVP
- Entry date processing (immediate/quarterly/monthly entry dates)
- Age requirements (minimum age checks)
- Hours-based eligibility (1000 hour rules)
- Employee type exclusions (intern, contractor)
- Multiple service computation methods
- Breaks in service handling
- Complex rehire rules
- Multiple eligibility tracks (401k vs match)

## Test Scenarios

1. **Immediate Eligibility**: eligibility_waiting_days = 0, all active employees eligible immediately
2. **One Year Wait**: eligibility_waiting_days = 365, employees eligible after 1 year of service
3. **Custom Wait**: eligibility_waiting_days = 180, employees eligible after 6 months
4. **New Hire**: Employee hired recently, not yet eligible
5. **Newly Eligible**: Employee crosses waiting period threshold, generates ELIGIBILITY event
6. **Bulk Processing**: 100K employee performance test

## Story Points: 5

### Effort Breakdown
- Days-based eligibility logic: 2 points
- SQL/dbt implementation: 1 point
- Event generation: 1 point
- Testing: 1 point

**Note**: This is the complete MVP - no entry date processing needed.

## Dependencies
- Workforce data models (int_baseline_workforce with hire_date)
- Event storage infrastructure (fct_yearly_events)
- Centralized configuration (config/simulation_config.yaml)
- SimulationEvent schema for ELIGIBILITY events
- orchestrator_mvp multi-year simulation framework

## Definition of Done
- [ ] Eligibility engine processes 100K employees in <30 seconds
- [ ] Days-based eligibility logic implemented and tested
- [ ] ELIGIBILITY events generated for newly eligible employees
- [ ] Event payload matches SimulationEvent schema
- [ ] Configuration works via simulation_config.yaml (eligibility.waiting_period_days)
- [ ] Unit tests achieve 95% coverage
- [ ] Integration test with `orchestrator_mvp/run_multi_year.py`
- [ ] Performance benchmark documented
