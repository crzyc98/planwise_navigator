# Quickstart: Fix Mid-Year Termination Tenure Calculation

**Feature**: 023-fix-midyear-tenure
**Date**: 2026-01-21

## Verify the Bug

### Step 1: Run a Simulation

```bash
# Activate environment
source .venv/bin/activate

# Run 2-year simulation to trigger the bug
cd dbt
dbt build --threads 1 --vars "simulation_year: 2025" --fail-fast
dbt build --threads 1 --vars "simulation_year: 2026" --fail-fast
```

### Step 2: Query for Mismatched Tenure/Band

```bash
duckdb dbt/simulation.duckdb "
SELECT
    employee_id,
    employee_hire_date,
    termination_date,
    employment_status,
    current_tenure,
    tenure_band,
    -- Expected tenure
    FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25)::INTEGER AS expected_tenure,
    -- Expected band
    CASE
        WHEN FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25) < 2 THEN '< 2'
        WHEN FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25) < 5 THEN '2-4'
        WHEN FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25) < 10 THEN '5-9'
        WHEN FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25) < 20 THEN '10-19'
        ELSE '20+'
    END AS expected_band
FROM fct_workforce_snapshot
WHERE employment_status = 'terminated'
  AND termination_date IS NOT NULL
  AND simulation_year = 2026
LIMIT 20;
"
```

### Step 3: Identify Specific Mismatches

```bash
duckdb dbt/simulation.duckdb "
SELECT
    employee_id,
    current_tenure,
    tenure_band,
    FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25)::INTEGER AS expected_tenure
FROM fct_workforce_snapshot
WHERE employment_status = 'terminated'
  AND termination_date IS NOT NULL
  AND simulation_year = 2026
  AND (
    -- Tenure doesn't match expected
    current_tenure != FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25)::INTEGER
    OR
    -- Band doesn't match tenure
    tenure_band != CASE
        WHEN current_tenure < 2 THEN '< 2'
        WHEN current_tenure < 5 THEN '2-4'
        WHEN current_tenure < 10 THEN '5-9'
        WHEN current_tenure < 20 THEN '10-19'
        ELSE '20+'
    END
  )
LIMIT 20;
"
```

## Test After Fix

### Run Full Test Suite

```bash
# From project root
pytest -m fast -v

# Run tenure-specific tests
pytest tests/test_tenure_calculation.py -v

# Run dbt tests
cd dbt
dbt test --threads 1 --select test_tenure_band_consistency
```

### Verify No Mismatches Remain

```bash
duckdb dbt/simulation.duckdb "
SELECT COUNT(*) AS mismatch_count
FROM fct_workforce_snapshot
WHERE employment_status = 'terminated'
  AND termination_date IS NOT NULL
  AND (
    current_tenure != FLOOR(DATEDIFF('day', employee_hire_date::DATE, termination_date::DATE) / 365.25)::INTEGER
    OR tenure_band != CASE
        WHEN current_tenure < 2 THEN '< 2'
        WHEN current_tenure < 5 THEN '2-4'
        WHEN current_tenure < 10 THEN '5-9'
        WHEN current_tenure < 20 THEN '10-19'
        ELSE '20+'
    END
  );
"
# Expected output: 0
```

### SQL/Polars Parity Test

```bash
# Run simulation in SQL mode (default)
planalign simulate 2025-2026 --clean

# Export SQL results
duckdb dbt/simulation.duckdb "COPY (SELECT * FROM fct_workforce_snapshot WHERE simulation_year = 2026) TO 'sql_snapshot.csv' (HEADER, DELIMITER ',');"

# Run simulation in Polars mode
planalign simulate 2025-2026 --clean --mode polars

# Export Polars results
duckdb dbt/simulation.duckdb "COPY (SELECT * FROM fct_workforce_snapshot WHERE simulation_year = 2026) TO 'polars_snapshot.csv' (HEADER, DELIMITER ',');"

# Compare tenure columns
python -c "
import pandas as pd
sql = pd.read_csv('sql_snapshot.csv')
polars = pd.read_csv('polars_snapshot.csv')
merged = sql.merge(polars, on='employee_id', suffixes=('_sql', '_polars'))
mismatches = merged[merged['current_tenure_sql'] != merged['current_tenure_polars']]
print(f'Tenure mismatches: {len(mismatches)}')
band_mismatches = merged[merged['tenure_band_sql'] != merged['tenure_band_polars']]
print(f'Band mismatches: {len(band_mismatches)}')
"
```

## Files to Modify

1. `dbt/models/marts/fct_workforce_snapshot.sql` - Main fix
2. `planalign_orchestrator/polars_state_pipeline.py` - Verify Polars parity
3. `tests/test_tenure_calculation.py` - Add regression tests
4. `dbt/tests/test_tenure_band_consistency.sql` - Add dbt test
