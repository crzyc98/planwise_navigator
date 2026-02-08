# Quickstart: Fix Census Compensation Annualization Logic

**Branch**: `037-fix-annualization-logic` | **Date**: 2026-02-07

## What This Fix Does

Corrects the compensation annualization logic in `stg_census_data.sql` and removes the HOTFIX workaround in `int_baseline_workforce.sql`. This is a code clarity fix — output values are numerically identical before and after.

## Files to Modify

1. **`dbt/models/staging/stg_census_data.sql`** — Simplify the `employee_annualized_compensation` formula
2. **`dbt/models/intermediate/int_baseline_workforce.sql`** — Replace HOTFIX with canonical `employee_annualized_compensation` reference
3. **`dbt/models/staging/schema.yml`** — Add data tests for annualization correctness

## Verification Steps

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Build affected models
cd dbt
dbt run --select stg_census_data int_baseline_workforce --threads 1

# 3. Run all tests including new annualization tests
dbt test --select stg_census_data int_baseline_workforce --threads 1

# 4. Verify no regression: full build
dbt build --threads 1 --fail-fast

# 5. Verify compensation values unchanged (from /workspace)
python3 -c "
import duckdb
conn = duckdb.connect('dbt/simulation.duckdb', read_only=True)
result = conn.execute('''
  SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE employee_annualized_compensation = employee_gross_compensation) as matching
  FROM stg_census_data
''').fetchone()
print(f'Total: {result[0]}, Matching: {result[1]}, All match: {result[0] == result[1]}')
conn.close()
"
```

## Key Constraint

- `employee_gross_compensation` is already an annual salary rate per the data contract
- Therefore `employee_annualized_compensation` = `employee_gross_compensation` by definition
- The pro-rated field `employee_plan_year_compensation` remains `gross * days_active / 365`
