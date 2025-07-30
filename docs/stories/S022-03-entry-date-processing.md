# Story S022-03: Entry Date Processing (MVP)

## Story Overview

### Summary
Calculate plan entry dates for eligible employees supporting immediate and quarterly entry patterns. This MVP implementation uses vectorized date arithmetic to efficiently determine when employees can begin participating in the DC plan.

### Business Value
- Ensures employees enter the plan at correct times per plan document
- Automates entry date calculations reducing HR workload
- Supports most common entry patterns (immediate and quarterly)

### Acceptance Criteria (Updated)
- ✅ Calculate immediate entry (same day as eligibility)
- ✅ Calculate monthly entry dates (1st of each month)
- ✅ Calculate quarterly entry dates (1/1, 4/1, 7/1, 10/1)
- ✅ SQL-based implementation for maximum performance
- ✅ Configuration via dbt variables
- ✅ Handle year boundaries correctly
- ✅ Fix entry date logic to include same-day entry (>= not >)
- ✅ Generate entry_date field for all eligible employees

## Technical Specifications

### Configuration Schema (Updated)
```yaml
# dbt_project.yml variables section
vars:
  entry_date_type: "monthly"  # immediate, monthly, or quarterly
  simulation_year: 2025
```

### SQL-Based Entry Date Calculation (Updated)
**Key Changes**: Moved to SQL for performance, fixed same-day entry logic, added monthly option.

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

            -- Monthly entry: 1st of next month (or same month if eligible on 1st)
            WHEN '{{ var("entry_date_type", "quarterly") }}' = 'monthly' THEN
                CASE
                    WHEN DAY(DATE('{{ var("simulation_year") }}-01-01')) = 1 THEN DATE('{{ var("simulation_year") }}-01-01')
                    ELSE DATE_ADD('month', 1, DATE_TRUNC('month', DATE('{{ var("simulation_year") }}-01-01')))
                END

            -- Quarterly entry: next quarter date (1/1, 4/1, 7/1, 10/1)
            WHEN '{{ var("entry_date_type", "quarterly") }}' = 'quarterly' THEN
                CASE
                    -- Q1: January 1
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-01-01') THEN DATE('{{ var("simulation_year") }}-01-01')
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-04-01') THEN DATE('{{ var("simulation_year") }}-04-01')
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-07-01') THEN DATE('{{ var("simulation_year") }}-07-01')
                    WHEN DATE('{{ var("simulation_year") }}-01-01') <= DATE('{{ var("simulation_year") }}-10-01') THEN DATE('{{ var("simulation_year") }}-10-01')
                    -- Next year Q1 if past Q4
                    ELSE DATE({{ var("simulation_year") + 1 }} || '-01-01')
                END

        END as entry_date

    FROM final_eligibility
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
**Now handled directly in SQL - no separate Python integration needed.**

The entry date calculation is integrated into the `int_eligibility_determination.sql` model:

```bash
# Run the dbt model to calculate eligibility and entry dates
dbt run --select int_eligibility_determination

# Results are available for filtering in other operations
# No separate Python processing required
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

### Included in MVP (Updated)
- Immediate entry (no delay)
- Monthly entry (1st of each month) - **NEW**
- Quarterly entry (4 fixed dates per year)
- Year boundary handling
- SQL-based calculations for performance
- dbt variable configuration
- Same-day entry compliance fix

### Deferred to Post-MVP
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

## Story Points: 6 (Updated)

### Effort Breakdown
- Entry date logic: 2 points
- SQL implementation: 2 points
- Monthly entry addition: 1 point
- Testing: 1 point

## Dependencies
- S022-01 (Core Eligibility Calculator)
- DuckDB date functions
- dbt variable configuration

## Definition of Done
- [ ] Immediate, monthly, and quarterly entry dates calculated correctly
- [ ] SQL implementation performs at scale
- [ ] Year boundaries handled properly
- [ ] Same-day entry compliance issue fixed
- [ ] Configuration-driven via dbt variables
- [ ] Unit tests cover all date scenarios
- [ ] Performance benchmark documented
