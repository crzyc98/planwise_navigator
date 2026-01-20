# Quickstart: Fix Current Tenure Calculation

**Feature**: 020-fix-tenure-calculation
**Date**: 2026-01-20

## Overview

This fix corrects the `current_tenure` calculation to use day-based arithmetic instead of year-only subtraction. The formula is:

```
tenure = floor((December 31 of simulation year - hire_date) / 365.25)
```

## Prerequisites

- Python 3.11+ with virtual environment activated
- dbt-core 1.8.8 and dbt-duckdb 1.8.1 installed
- Access to `dbt/simulation.duckdb` database

## Quick Verification

### 1. Check Current Behavior

```bash
# Verify current tenure calculation (before fix)
cd dbt
duckdb simulation.duckdb "
SELECT
    employee_id,
    employee_hire_date,
    current_tenure,
    -- Expected tenure with day-based calculation
    FLOOR((MAKE_DATE(2025, 12, 31) - employee_hire_date) / 365.25)::INTEGER as expected_tenure
FROM fct_workforce_snapshot
WHERE simulation_year = 2025
LIMIT 10;
"
```

### 2. Apply Fix

```bash
# Run dbt with updated models
cd dbt
dbt run --select int_baseline_workforce --threads 1 --vars '{simulation_year: 2025}'
```

### 3. Verify Fix

```bash
# Confirm tenure matches expected values
duckdb simulation.duckdb "
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE current_tenure = FLOOR((MAKE_DATE(2025, 12, 31) - employee_hire_date) / 365.25)::INTEGER) as correct
FROM fct_workforce_snapshot
WHERE simulation_year = 2025;
"
```

## Key Files

| File | Purpose |
|------|---------|
| `dbt/macros/calculate_tenure.sql` | New macro for consistent tenure calculation |
| `dbt/models/intermediate/int_baseline_workforce.sql` | Updated to use macro |
| `tests/test_tenure_calculation.py` | Property-based tests |

## Test Commands

```bash
# Run tenure-specific tests
pytest tests/test_tenure_calculation.py -v

# Run fast test suite
pytest -m fast

# Run dbt tests
cd dbt && dbt test --select int_baseline_workforce --threads 1
```

## Troubleshooting

### Issue: Tenure values don't match expected

1. Check hire_date format: `SELECT DISTINCT typeof(employee_hire_date) FROM stg_census_data;`
2. Verify simulation year variable: `dbt run --vars '{simulation_year: 2025}' --debug`
3. Check for null hire dates: `SELECT COUNT(*) FROM stg_census_data WHERE employee_hire_date IS NULL;`

### Issue: SQL and Polars modes produce different results

1. Run parity test: `pytest tests/test_tenure_calculation.py::test_sql_polars_parity -v`
2. Compare specific employees with known hire dates
3. Check Polars `year_end` calculation matches simulation year

## Formula Reference

| Scenario | Formula | Example |
|----------|---------|---------|
| Initial tenure | `floor((12/31/year - hire_date) / 365.25)` | Hired 2020-06-15, Year 2025 → 5 |
| Year-over-year | `previous_tenure + 1` | Tenure 5 in 2025 → 6 in 2026 |
| New hire (same year) | `floor((12/31/year - hire_date) / 365.25)` | Hired 2025-07-01, Year 2025 → 0 |
