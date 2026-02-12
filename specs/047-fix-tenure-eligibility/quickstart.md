# Quickstart: Fix Tenure Eligibility Enforcement

## What Changed

When `minimum_tenure_years > 0` is configured for employer match or core contributions, `allow_new_hires` now defaults to `false` instead of `true`. New hires no longer bypass the tenure requirement unless explicitly opted in.

A configuration warning is emitted when `allow_new_hires: true` is set alongside `minimum_tenure_years > 0`.

## Verify the Fix

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Run a simulation
planalign simulate 2025

# 3. Check eligibility results
python3 -c "
import duckdb
conn = duckdb.connect('dbt/simulation.duckdb')
result = conn.execute('''
    SELECT
        current_tenure,
        eligible_for_match,
        match_eligibility_reason,
        match_allow_new_hires,
        eligible_for_core,
        core_allow_new_hires,
        COUNT(*) as employee_count
    FROM int_employer_eligibility
    WHERE simulation_year = 2025
    GROUP BY 1, 2, 3, 4, 5, 6
    ORDER BY current_tenure
''').fetchdf()
print(result.to_string())
conn.close()
"
```

## Test the New Default

To test with a non-zero tenure requirement:

1. Edit `config/simulation_config.yaml`:
   ```yaml
   employer_match:
     eligibility:
       minimum_tenure_years: 2
       # allow_new_hires is NOT set — defaults to false
   ```

2. Run simulation and verify tenure-0 and tenure-1 employees are excluded.

## Run Tests

```bash
# Python unit tests
pytest tests/test_match_modes.py -v

# dbt tests
cd dbt && dbt test --select int_employer_eligibility --threads 1
```

## Backward Compatibility

- `minimum_tenure_years: 0` (the default): No change in behavior
- `allow_new_hires: true` explicitly set: No change in behavior (warning emitted if tenure > 0)
- `minimum_tenure_years > 0` without explicit `allow_new_hires`: New hires now correctly excluded
- `apply_eligibility: false`: No change (uses simple active + 1000 hours rule)
