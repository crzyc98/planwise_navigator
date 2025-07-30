# Story S022-03: Entry Date Processing (Epic E026)

## Story Overview

### Summary
Calculate plan entry dates for eligible employees supporting immediate, monthly, and quarterly entry patterns. This story has been moved from Epic E022 to Epic E026 since the E022 MVP only needs eligibility determination, not entry date processing.

**Epic**: E026 - Advanced Eligibility Features
**Dependencies**: Epic E022 (Simple Eligibility Engine) must be completed first

### Business Value
- Ensures employees enter the plan at correct times per plan document
- Automates entry date calculations reducing HR workload
- Supports most common entry patterns (immediate and quarterly)

### Acceptance Criteria (Simplified)
- ✅ Calculate immediate entry (same day as eligibility)
- ✅ Calculate quarterly entry dates (1/1, 4/1, 7/1, 10/1)
- ✅ SQL-based implementation for maximum performance
- ✅ Configuration via dbt variables
- ✅ Handle year boundaries correctly
- ✅ Generate entry_date field for all eligible employees
- ✅ Generate ENTRY_DATE events for newly eligible employees

## Technical Specifications

### Configuration Schema (Simplified)
```yaml
# dbt_project.yml variables section
vars:
  entry_date_type: "quarterly"  # immediate or quarterly
  simulation_year: 2025
```

### SQL-Based Entry Date Calculation (Simplified)
**Key Changes**: Focus on immediate and quarterly entry patterns only.

```sql
-- Added to int_eligibility_determination.sql
WITH entry_date_calculation AS (
    SELECT
        *,
        -- Entry date calculation based on type
        CASE
            -- Immediate entry: same day as eligibility assessment
            WHEN '{{ var("entry_date_type", "quarterly") }}' = 'immediate' THEN
                DATE('{{ var("simulation_year") }}-01-01')

            -- Quarterly entry: next quarter date (1/1, 4/1, 7/1, 10/1)
            WHEN '{{ var("entry_date_type", "quarterly") }}' = 'quarterly' THEN
                CASE
                    -- For simulation year start, use Q1
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-01-01') THEN DATE('{{ var("simulation_year") }}-01-01')
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-04-01') THEN DATE('{{ var("simulation_year") }}-04-01')
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-07-01') THEN DATE('{{ var("simulation_year") }}-07-01')
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-10-01') THEN DATE('{{ var("simulation_year") }}-10-01')
                    -- Next year Q1 if past Q4
                    ELSE DATE({{ var("simulation_year") + 1 }} || '-01-01')
                END

        END as entry_date

    FROM eligibility_checks
    WHERE is_eligible = true
)

SELECT * FROM entry_date_calculation
```

### Simplified Entry Date Logic (Fixed Compliance Issue)
```sql
-- Fixed logic that includes same-day entry
-- Old (incorrect): d > eligibility_date
-- New (correct): d >= eligibility_date

-- Example for quarterly entry
CASE
    WHEN eligibility_date <= quarter_date_1 THEN quarter_date_1  -- INCLUDES same day
    WHEN eligibility_date <= quarter_date_2 THEN quarter_date_2  -- INCLUDES same day
    -- etc.
END
```

### Integration Pattern (Updated)
**Enhanced to generate entry date events for audit trail and downstream processing.**

The entry date calculation is integrated into the `int_eligibility_determination.sql` model with event generation:

```python
def generate_entry_date_events(self, simulation_year: int) -> List[Dict]:
    """Generate ENTRY_DATE events for newly eligible employees"""

    query = f"""
    SELECT
        employee_id,
        entry_date,
        eligibility_reason
    FROM int_eligibility_determination
    WHERE simulation_year = {simulation_year}
    AND is_eligible = true
    AND entry_date IS NOT NULL
    """

    eligible_df = self.duckdb_conn.execute(query).df()

    events = []
    for _, row in eligible_df.iterrows():
        event = {
            "event_type": "ENTRY_DATE",
            "employee_id": row['employee_id'],
            "simulation_year": simulation_year,
            "event_date": row['entry_date'].strftime("%Y-%m-%d"),
            "event_payload": {
                "entry_type": "plan_participation",
                "scheduled_entry_date": row['entry_date'].strftime("%Y-%m-%d"),
                "eligibility_reason": row['eligibility_reason'],
                "entry_date_rule": self.config.entry_date_type
            }
        }
        events.append(event)

    return events

# Integration with main event generation
def generate_all_eligibility_events(simulation_year: int) -> List[Dict]:
    engine = EligibilityEngine()

    # Generate all eligibility-related events
    eligibility_events = engine.generate_eligibility_events(simulation_year)
    exclusion_events = engine.generate_exclusion_events(simulation_year)
    entry_date_events = engine.generate_entry_date_events(simulation_year)

    return eligibility_events + exclusion_events + entry_date_events
```

### Data Quality Validation
```python
def validate_entry_dates(self, conn, simulation_year: int) -> Dict[str, Any]:
    """Validate entry date calculations"""

    validation_query = f"""
    SELECT
        entry_date_type,
        COUNT(*) as employee_count,
        MIN(entry_date) as earliest_entry,
        MAX(entry_date) as latest_entry,
        COUNT(CASE WHEN entry_date < DATE('{simulation_year}-01-01') THEN 1 END) as invalid_past_dates,
        COUNT(CASE WHEN entry_date > DATE('{simulation_year + 1}-12-31') THEN 1 END) as invalid_future_dates
    FROM int_eligibility_determination
    WHERE is_eligible = true
    GROUP BY entry_date_type
    """

    results = conn.execute(validation_query).fetchall()
    return dict(results)
```

## MVP Simplifications

### Included in MVP (Simplified)
- Immediate entry (no delay)
- Quarterly entry (4 fixed dates per year)
- Year boundary handling
- SQL-based calculations for performance
- dbt variable configuration

### Deferred to Post-MVP
- Monthly entry dates (1st of each month)
- Semi-annual entry dates
- Dual entry dates (401k vs match)
- Business day adjustments
- Advance notifications (30/60/90 days)
- Payroll calendar integration
- Complex entry date rules
- Entry date changes mid-year

## Test Scenarios

1. **Immediate Entry**: Verify same-day entry for immediate rule
2. **Q1 Entry**: Employee eligible in Q1 enters on next quarter
3. **Year Boundary**: Employee eligible in Q4 enters next year Q1
4. **Exact Quarter Date**: Employee eligible on 4/1 enters same day
5. **Bulk Processing**: 10K eligible employees performance test

## Performance Considerations

- Vectorized date calculations using pandas
- Pre-compute quarter dates once per run
- Minimize date object creation
- Target: <1 second for 100K employees

## Story Points: 4 (Simplified)

### Effort Breakdown
- Entry date logic: 2 points
- SQL implementation: 1 point
- Testing: 1 point

## Dependencies
- **Epic E022**: Simple Eligibility Engine (must be completed first)
- S022-01 (Core Eligibility Calculator) - provides eligibility determination
- DuckDB date functions
- dbt variable configuration
- orchestrator_mvp multi-year simulation framework

## Related Epic
This story is part of **Epic E026: Advanced Eligibility Features**. See `/docs/epics/E026_advanced_eligibility_features.md` for the complete advanced eligibility roadmap.

## Definition of Done
- [ ] Immediate and quarterly entry dates calculated correctly
- [ ] SQL implementation performs at scale
- [ ] Year boundaries handled properly
- [ ] Same-day entry compliance issue fixed
- [ ] Configuration-driven via dbt variables
- [ ] Unit tests cover all date scenarios
- [ ] Performance benchmark documented
- [ ] ENTRY_DATE events generated for eligible employees
- [ ] Event payload matches SimulationEvent schema
