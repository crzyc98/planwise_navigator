# Quickstart: Fix Census Compensation Annualization Logic

**Feature Branch**: `043-fix-annualization-logic`

## What This Fix Does

Corrects the annualization logic in `stg_census_data.sql` by clarifying the relationship between `employee_gross_compensation` (annual rate), `employee_annualized_compensation` (full-year equivalent), and `employee_plan_year_compensation` (prorated). Removes HOTFIX/bypass patterns from `int_baseline_workforce.sql` and adds annualization-specific tests.

## Files Modified

1. **`dbt/models/staging/stg_census_data.sql`** — Clarify annualization logic and comments
2. **`dbt/models/intermediate/int_baseline_workforce.sql`** — Remove HOTFIX comments, use corrected staging field
3. **`dbt/tests/data_quality/test_annualization_logic.sql`** — New: validate proration math and edge cases
4. **`dbt/models/staging/schema.yml`** — Update/add schema tests for annualization fields

## Verification Steps

```bash
# 1. Build the affected models
cd dbt
dbt run --select stg_census_data int_baseline_workforce --threads 1

# 2. Run the new annualization test
dbt test --select test_annualization_logic --vars "simulation_year: 2025" --threads 1

# 3. Run existing compensation tests (regression check)
dbt test --select test_compensation_bounds test_negative_compensation --vars "simulation_year: 2025" --threads 1

# 4. Verify schema tests pass
dbt test --select stg_census_data --threads 1

# 5. Full regression: build all downstream models
dbt build --threads 1 --fail-fast
```

## Key Validation Queries

```sql
-- Verify annualized = gross for all employees
SELECT COUNT(*) AS mismatches
FROM stg_census_data
WHERE employee_annualized_compensation != employee_gross_compensation;
-- Expected: 0

-- Verify plan year comp is properly prorated
SELECT
    employee_id,
    employee_gross_compensation,
    employee_plan_year_compensation,
    employee_annualized_compensation,
    ROUND(employee_plan_year_compensation / NULLIF(employee_gross_compensation, 0), 4) AS proration_ratio
FROM stg_census_data
WHERE employee_plan_year_compensation != employee_gross_compensation
LIMIT 10;

-- Verify baseline uses corrected field
SELECT
    b.employee_id,
    b.current_compensation,
    s.employee_annualized_compensation,
    b.current_compensation - s.employee_annualized_compensation AS diff
FROM int_baseline_workforce b
JOIN stg_census_data s ON b.employee_id = s.employee_id
WHERE b.current_compensation != s.employee_annualized_compensation;
-- Expected: 0 rows
```

## Risk Mitigation

- **No value changes expected**: Since `employee_gross_compensation` is already an annual rate, `employee_annualized_compensation` equals `employee_gross_compensation` before and after the fix.
- **52 downstream models**: All use `current_compensation` which remains unchanged in value. Run full `dbt build` to confirm zero regression.
- **Test coverage**: New tests validate the proration math and cross-model consistency that were previously untested.
