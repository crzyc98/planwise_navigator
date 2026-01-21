# Quickstart: Fix Hire Date Before Termination Date Ordering

**Feature**: 022-fix-hire-termination-order
**Date**: 2026-01-21

## Prerequisites

```bash
# Activate virtual environment
source .venv/bin/activate

# Ensure dbt is available
cd dbt
dbt --version  # Should show 1.8.8
```

## Validation Queries

Use these queries to verify the bugs exist before implementation and are fixed after.

### Bug 1: Termination Date Before Hire Date

```bash
# Check for terminations before hire (should find violations BEFORE fix)
duckdb dbt/simulation.duckdb "
SELECT
    COUNT(*) AS violations,
    MIN(termination_date - employee_hire_date) AS min_diff_days,
    MAX(termination_date - employee_hire_date) AS max_diff_days
FROM simulation.main.fct_workforce_snapshot
WHERE termination_date IS NOT NULL
  AND termination_date < employee_hire_date
  AND simulation_year = 2026;
"

# Expected BEFORE fix: violations > 0, min_diff_days < 0
# Expected AFTER fix: violations = 0
```

### Bug 2: Tenure Calculated to Year-End Instead of Termination Date

```bash
# Specific regression test: hire=2024-08-01, term=2026-01-10
duckdb dbt/simulation.duckdb "
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    current_tenure AS actual_tenure,
    FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER AS expected_tenure,
    CASE
        WHEN current_tenure = FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status
FROM simulation.main.fct_workforce_snapshot
WHERE employment_status = 'terminated'
  AND termination_date IS NOT NULL
  AND simulation_year = 2026
LIMIT 10;
"

# Check aggregate violations
duckdb dbt/simulation.duckdb "
SELECT
    COUNT(*) AS total_terminated,
    SUM(CASE
        WHEN current_tenure != FLOOR(DATEDIFF('day', employee_hire_date, termination_date) / 365.25)::INTEGER
        THEN 1 ELSE 0
    END) AS tenure_violations
FROM simulation.main.fct_workforce_snapshot
WHERE employment_status = 'terminated'
  AND termination_date IS NOT NULL
  AND simulation_year = 2026;
"

# Expected BEFORE fix: tenure_violations > 0
# Expected AFTER fix: tenure_violations = 0
```

## Run Tests

### Data Quality Tests (dbt)

```bash
cd dbt

# Run termination-after-hire test
dbt test --select test_termination_after_hire --vars "simulation_year: 2026" --threads 1

# Run tenure-at-termination test
dbt test --select test_tenure_at_termination --vars "simulation_year: 2026" --threads 1

# Run all data quality tests
dbt test --select tag:data_quality --vars "simulation_year: 2026" --threads 1
```

### Unit Tests (pytest)

```bash
# Run termination event tests
pytest tests/test_termination_events.py -v

# Run with specific test
pytest tests/test_termination_events.py::test_tenure_at_termination_regression -v
```

## Development Workflow

### 1. Create Tests First (Constitution III)

```bash
# Create test files (they should FAIL before implementation)
cd dbt
dbt test --select test_termination_after_hire --vars "simulation_year: 2026" --threads 1
# Expected: FAIL (violations found)
```

### 2. Modify Macro

Edit `dbt/macros/generate_termination_date.sql`:
- Add `hire_date_column` parameter
- Change base from Jan 1 to hire_date
- Calculate days_available from hire to year_end

### 3. Update Models

```bash
# Rebuild termination events
dbt run --select int_termination_events --vars "simulation_year: 2026" --threads 1

# Rebuild snapshot
dbt run --select fct_workforce_snapshot --vars "simulation_year: 2026" --threads 1
```

### 4. Verify Fix

```bash
# Re-run validation queries (should now pass)
dbt test --select test_termination_after_hire --vars "simulation_year: 2026" --threads 1
dbt test --select test_tenure_at_termination --vars "simulation_year: 2026" --threads 1
```

## Full Simulation Test

```bash
# Run complete simulation for year 2026
cd /workspace
planalign simulate 2026 --verbose

# Verify all success criteria
duckdb dbt/simulation.duckdb "
-- SC-001: Zero employees with termination_date < hire_date
SELECT 'SC-001' AS criteria,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       COUNT(*) AS violations
FROM simulation.main.fct_workforce_snapshot
WHERE termination_date < employee_hire_date
  AND simulation_year = 2026

UNION ALL

-- SC-005: Non-negative tenure
SELECT 'SC-005' AS criteria,
       CASE WHEN MIN(current_tenure) >= 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       SUM(CASE WHEN current_tenure < 0 THEN 1 ELSE 0 END) AS violations
FROM simulation.main.fct_workforce_snapshot
WHERE employment_status = 'terminated'
  AND simulation_year = 2026

UNION ALL

-- SC-007: Specific regression test
SELECT 'SC-007' AS criteria,
       CASE
           WHEN COUNT(*) = 0 THEN 'N/A (no matching employee)'
           WHEN MIN(current_tenure) = 1 THEN 'PASS'
           ELSE 'FAIL'
       END AS status,
       COUNT(*) AS matching_employees
FROM simulation.main.fct_workforce_snapshot
WHERE employee_hire_date = '2024-08-01'
  AND termination_date BETWEEN '2026-01-01' AND '2026-01-31'
  AND simulation_year = 2026;
"
```

## Polars Pipeline Verification

```bash
# Run simulation in Polars mode and verify parity
planalign simulate 2026 --mode polars --verbose

# Compare results between SQL and Polars modes
duckdb dbt/simulation.duckdb "
SELECT
    'SQL violations' AS mode,
    COUNT(*) AS termination_before_hire_count
FROM simulation.main.fct_workforce_snapshot
WHERE termination_date < employee_hire_date
  AND simulation_year = 2026;
"
```
