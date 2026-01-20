# Research: Fix Current Tenure Calculation

**Feature**: 020-fix-tenure-calculation
**Date**: 2026-01-20

## Current Implementation Analysis

### SQL Pipeline (dbt)

**Location**: `dbt/models/intermediate/int_baseline_workforce.sql` (line 31)

**Current Code**:
```sql
GREATEST(0, EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) AS current_tenure
```

**Problem**: Uses year-only subtraction, which is imprecise:
- Employee hired 2021-01-01, simulation year 2025 → returns 4 years
- Actual tenure as of 2025-12-31 = 4.999 years → should be 4 years (truncated)
- Employee hired 2020-06-15, simulation year 2025 → returns 5 years
- Actual tenure as of 2025-12-31 = 5.54 years → should be 5 years (correct by coincidence)

**Year-over-Year Increment** (`int_active_employees_prev_year_snapshot.sql` line 65):
```sql
current_tenure + 1 as current_tenure
```
This is **correct** - incrementing by 1 for continuing employees is the right approach.

### Polars Pipeline

**Location**: `planalign_orchestrator/polars_state_pipeline.py` (lines 1860-1866)

**Current Code**:
```python
pl.when(pl.col('employee_hire_date').is_not_null())
.then(
    (pl.lit(year_end) - pl.col('employee_hire_date').cast(pl.Date)).dt.total_days() / 365.25
)
.otherwise(5.0)
.cast(pl.Int32)
.alias('current_tenure')
```

**Analysis**: This is **correct** per the spec:
- Uses day-based calculation
- Divides by 365.25 (accounts for leap years)
- Casts to Int32 (truncates, doesn't round)
- Has fallback for null hire dates (5.0 years)

### Inconsistency Impact

| Hire Date | Sim Year | SQL Result | Polars Result | Expected |
|-----------|----------|------------|---------------|----------|
| 2021-01-01 | 2025 | 4 | 4 | 4 |
| 2020-06-15 | 2025 | 5 | 5 | 5 |
| 2021-12-15 | 2025 | 4 | 4 | 4 |
| 2020-01-01 | 2025 | 5 | 5 | 5 |
| 2020-12-31 | 2025 | 5 | 5 | 5 |

In many cases the results match, but edge cases around year boundaries can differ.

## Decision: DuckDB Date Arithmetic

**Decision**: Use DuckDB's native date subtraction with FLOOR function

**Rationale**:
1. DuckDB supports `date - date` which returns integer days
2. `FLOOR(days / 365.25)` provides truncation semantics
3. Matches Polars formula exactly
4. More performant than EXTRACT-based calculations

**Alternatives Considered**:

| Alternative | Rejected Because |
|-------------|------------------|
| Keep year subtraction | Inaccurate for mid-year hires |
| Use DATEDIFF function | DuckDB uses `date - date` natively |
| Round instead of floor | Spec explicitly requires truncation |
| Use 365 instead of 365.25 | Doesn't account for leap years |

## DuckDB Date Arithmetic Patterns

### Correct Formula (DuckDB)
```sql
-- Calculate tenure as of simulation year end (12/31)
FLOOR(
    (MAKE_DATE({{ var('simulation_year') }}, 12, 31) - employee_hire_date) / 365.25
)::INTEGER AS current_tenure
```

### Edge Case Handling
```sql
-- Handle null hire dates and future hires
CASE
    WHEN employee_hire_date IS NULL THEN 0
    WHEN employee_hire_date > MAKE_DATE({{ var('simulation_year') }}, 12, 31) THEN 0
    ELSE FLOOR(
        (MAKE_DATE({{ var('simulation_year') }}, 12, 31) - employee_hire_date) / 365.25
    )::INTEGER
END AS current_tenure
```

### Verification Query
```sql
-- Test cases to verify calculation
SELECT
    '2020-06-15'::DATE as hire_date,
    MAKE_DATE(2025, 12, 31) as year_end,
    (MAKE_DATE(2025, 12, 31) - '2020-06-15'::DATE) as days,
    FLOOR((MAKE_DATE(2025, 12, 31) - '2020-06-15'::DATE) / 365.25) as tenure;
-- Expected: 2025 days, 5 years
```

## Macro Design

**Decision**: Create reusable `calculate_tenure` macro

**Rationale**:
1. Single source of truth for tenure calculation
2. Ensures consistency across all models
3. Easier to update if formula changes
4. Self-documenting with clear parameters

**Macro Interface**:
```sql
{{ calculate_tenure(
    hire_date_column='employee_hire_date',
    as_of_date="MAKE_DATE(" ~ var('simulation_year') ~ ", 12, 31)"
) }}
```

## Testing Strategy

**Decision**: Property-based testing with Hypothesis

**Rationale**:
1. Tenure calculation has clear mathematical properties
2. Property-based tests catch edge cases automatically
3. Hypothesis generates diverse test inputs

**Properties to Test**:
1. `tenure >= 0` for all valid hire dates
2. `tenure(year+1) = tenure(year) + 1` for continuing employees
3. `tenure = 0` when hire_date >= year_end
4. SQL and Polars produce identical results

## Files Requiring Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `dbt/macros/calculate_tenure.sql` | NEW | Reusable tenure macro |
| `dbt/models/intermediate/int_baseline_workforce.sql` | MODIFY | Use new macro |
| `dbt/models/intermediate/int_employee_compensation_by_year.sql` | VERIFY | Check tenure usage |
| `planalign_orchestrator/polars_state_pipeline.py` | VERIFY | Already correct |
| `tests/test_tenure_calculation.py` | NEW | Property-based tests |

## References

- DuckDB Date Functions: https://duckdb.org/docs/sql/functions/date
- Polars Date Arithmetic: https://docs.pola.rs/py-polars/html/reference/expressions/temporal.html
- Hypothesis Property-Based Testing: https://hypothesis.readthedocs.io/
