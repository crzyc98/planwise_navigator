# Quickstart: Fix 401(a)(17) Compensation Limit

**Feature**: 026-fix-401a17-comp-limit
**Date**: 2026-01-22

## Prerequisites

- Python 3.11 with virtual environment activated
- dbt-duckdb 1.8.1 installed
- Access to `/workspace/dbt/` directory

## Quick Verification

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Navigate to dbt directory
cd dbt

# 3. Load the updated seed (after implementation)
dbt seed --select config_irs_limits --threads 1

# 4. Run affected models for a single year
dbt run --select int_employee_match_calculations int_employer_core_contributions \
    --threads 1 --vars "simulation_year: 2026"

# 5. Run the compliance test
dbt test --select test_401a17_compliance --threads 1
```

## Verification Query

After running the models, verify high earners have capped contributions:

```bash
# Query high earners (>$360K compensation for 2026)
duckdb dbt/simulation.duckdb "
SELECT
    m.employee_id,
    m.simulation_year,
    m.eligible_compensation,
    m.employer_match_amount,
    m.irs_401a17_limit_applied,
    c.employer_core_amount,
    c.irs_401a17_limit_applied AS core_limit_applied
FROM int_employee_match_calculations m
JOIN int_employer_core_contributions c
    ON m.employee_id = c.employee_id
    AND m.simulation_year = c.simulation_year
WHERE m.eligible_compensation > 360000
    AND m.simulation_year = 2026
ORDER BY m.eligible_compensation DESC
LIMIT 10;
"
```

## Expected Results

For a $1,675,000 employee in 2026:
- `eligible_compensation`: 1,675,000
- `employer_match_amount`: ≤ 14,400 (4% × $360,000)
- `employer_core_amount`: ≤ 7,200 (2% × $360,000)
- `irs_401a17_limit_applied`: TRUE

## Troubleshooting

### Test Fails with Violations

If `test_401a17_compliance` fails:

```bash
# Check which employees are violating
duckdb dbt/simulation.duckdb "
SELECT employee_id, simulation_year, employer_match_amount, eligible_compensation
FROM int_employee_match_calculations
WHERE employer_match_amount > 14400  -- 4% × $360,000 for 2026
    AND simulation_year = 2026
LIMIT 5;
"
```

### Seed Not Loading

Verify seed file format:

```bash
head -3 dbt/seeds/config_irs_limits.csv
# Expected: limit_year,base_limit,catch_up_limit,catch_up_age_threshold,compensation_limit
```

### Model Compilation Errors

Check dbt compilation:

```bash
cd dbt
dbt compile --select int_employee_match_calculations --threads 1
```

## Files Modified

| File | Change |
|------|--------|
| `dbt/seeds/config_irs_limits.csv` | Add `compensation_limit` column |
| `dbt/models/intermediate/events/int_employee_match_calculations.sql` | Apply 401(a)(17) cap |
| `dbt/models/intermediate/int_employer_core_contributions.sql` | Apply 401(a)(17) cap |
| `dbt/tests/data_quality/test_401a17_compliance.sql` | New validation test |
