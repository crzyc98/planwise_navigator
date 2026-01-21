# Quickstart: Fix Termination Event Data Quality

**Feature**: 021-fix-termination-events
**Date**: 2026-01-21

## Prerequisites

- Python 3.11 virtual environment activated
- dbt installed and configured
- Access to `dbt/simulation.duckdb`

```bash
# Verify environment
source .venv/bin/activate
cd dbt
dbt debug
```

## Implementation Steps

### Step 1: Create the Date Generation Macro

Create `dbt/macros/generate_termination_date.sql`:

```sql
{#
    generate_termination_date - Generate distributed termination dates

    Uses year-aware hashing to ensure dates are distributed across the year
    while maintaining determinism for reproducibility.

    Parameters:
        employee_id_column: Column containing employee ID
        simulation_year: The simulation year (integer or variable)
        random_seed: Random seed for determinism (default: 42)

    Returns: DATE within the simulation year
#}

{% macro generate_termination_date(employee_id_column, simulation_year, random_seed=42) %}
    CAST('{{ simulation_year }}-01-01' AS DATE)
    + INTERVAL (
        (ABS(HASH({{ employee_id_column }} || '|' || {{ simulation_year }} || '|DATE|{{ random_seed }}')) % 365)
    ) DAY
{% endmacro %}
```

### Step 2: Update int_termination_events.sql

Replace line ~100:

```sql
-- BEFORE (buggy):
(CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id)) % 365)) DAY) AS effective_date,

-- AFTER (fixed):
{{ generate_termination_date('w.employee_id', simulation_year, var('random_seed', 42)) }} AS effective_date,
```

Also update the tenure calculation reference (line ~107) to use the same macro.

### Step 3: Update int_new_hire_termination_events.sql

Rename output column at line ~122:

```sql
-- BEFORE:
'new_hire_termination' AS termination_type,

-- AFTER:
'new_hire_termination' AS event_category,
```

### Step 4: Update fct_workforce_snapshot.sql

Add explicit hire event validation in the `detailed_status_code` CASE (around line 749):

```sql
-- BEFORE:
WHEN COALESCE(ec.is_new_hire, false) = true
     AND fwc.employment_status = 'active'
THEN 'new_hire_active'

-- AFTER:
WHEN COALESCE(ec.is_new_hire, false) = true
     AND fwc.employment_status = 'active'
     AND fwc.employee_hire_date IS NOT NULL
     AND EXTRACT(YEAR FROM fwc.employee_hire_date) = sp.current_year
THEN 'new_hire_active'
```

Apply same pattern to the `new_hire_termination` case:

```sql
WHEN COALESCE(ec.is_new_hire, false) = true
     AND fwc.employment_status = 'terminated'
     AND fwc.employee_hire_date IS NOT NULL
     AND EXTRACT(YEAR FROM fwc.employee_hire_date) = sp.current_year
THEN 'new_hire_termination'
```

### Step 5: Add Data Quality Tests

Create `dbt/tests/data_quality/test_termination_date_distribution.sql`:

```sql
-- Test: No single month should have >20% of terminations
WITH monthly_counts AS (
    SELECT
        EXTRACT(MONTH FROM effective_date) AS term_month,
        COUNT(*) AS month_count,
        SUM(COUNT(*)) OVER() AS total_count
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'termination'
      AND simulation_year = {{ var('simulation_year') }}
    GROUP BY 1
)
SELECT
    term_month,
    month_count,
    total_count,
    ROUND(month_count * 100.0 / total_count, 2) AS pct
FROM monthly_counts
WHERE month_count * 100.0 / total_count > 20
```

Create `dbt/tests/data_quality/test_new_hire_status_accuracy.sql`:

```sql
-- Test: No new_hire_active without current-year hire event
SELECT
    ws.employee_id,
    ws.detailed_status_code,
    ws.employee_hire_date,
    ws.simulation_year
FROM {{ ref('fct_workforce_snapshot') }} ws
WHERE ws.detailed_status_code = 'new_hire_active'
  AND ws.simulation_year = {{ var('simulation_year') }}
  AND (
      ws.employee_hire_date IS NULL
      OR EXTRACT(YEAR FROM ws.employee_hire_date) != ws.simulation_year
  )
```

Create `dbt/tests/data_quality/test_new_hire_termination_completeness.sql`:

```sql
-- Test: All new_hire_termination records must have termination_date
SELECT
    ws.employee_id,
    ws.detailed_status_code,
    ws.employment_status,
    ws.termination_date
FROM {{ ref('fct_workforce_snapshot') }} ws
WHERE ws.detailed_status_code = 'new_hire_termination'
  AND ws.simulation_year = {{ var('simulation_year') }}
  AND (
      ws.termination_date IS NULL
      OR ws.employment_status != 'terminated'
  )
```

## Validation

### Run the Build

```bash
cd dbt

# Clean and rebuild affected models
dbt run --select int_termination_events int_new_hire_termination_events fct_workforce_snapshot --threads 1 --vars "simulation_year: 2026"

# Run data quality tests
dbt test --select test_termination_date_distribution test_new_hire_status_accuracy test_new_hire_termination_completeness --threads 1 --vars "simulation_year: 2026"
```

### Manual Validation Queries

```bash
# Check date distribution
duckdb dbt/simulation.duckdb "
SELECT
    EXTRACT(MONTH FROM effective_date) AS month,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM fct_yearly_events
WHERE event_type = 'termination' AND simulation_year = 2026
GROUP BY 1 ORDER BY 1
"

# Check status code accuracy
duckdb dbt/simulation.duckdb "
SELECT detailed_status_code, employment_status, COUNT(*)
FROM fct_workforce_snapshot
WHERE simulation_year = 2026
GROUP BY 1, 2 ORDER BY 1
"

# Check new hire termination completeness
duckdb dbt/simulation.duckdb "
SELECT
    COUNT(*) AS total,
    COUNT(termination_date) AS with_date,
    COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) AS with_status
FROM fct_workforce_snapshot
WHERE detailed_status_code = 'new_hire_termination' AND simulation_year = 2026
"
```

## Expected Results

### Date Distribution (SC-001)
- Each month should have 5-15% of terminations
- No single date should have >5% of terminations

### Status Code Accuracy (SC-002, SC-004)
- Zero employees with `new_hire_active` who lack a current-year hire event
- Zero employees with `new_hire_termination` who have `employment_status = 'active'`

### Data Completeness (SC-003)
- 100% of employees with termination events have non-null `termination_date`
- 100% of employees with termination events have `employment_status = 'terminated'`

## Rollback

If issues arise, revert the changes:

```bash
git checkout main -- dbt/models/intermediate/events/int_termination_events.sql
git checkout main -- dbt/models/intermediate/events/int_new_hire_termination_events.sql
git checkout main -- dbt/models/marts/fct_workforce_snapshot.sql
rm dbt/macros/generate_termination_date.sql
rm dbt/tests/data_quality/test_termination_date_distribution.sql
rm dbt/tests/data_quality/test_new_hire_status_accuracy.sql
rm dbt/tests/data_quality/test_new_hire_termination_completeness.sql
```
