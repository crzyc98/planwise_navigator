# Quickstart: Tenure-Based and Points-Based Employer Match

**Feature Branch**: `046-tenure-points-match`

## What This Feature Does

Adds two new employer match calculation modes:
- **`tenure_based`**: Match rate varies by employee years of service (configurable tiers)
- **`points_based`**: Match rate varies by employee "points" where points = FLOOR(age) + FLOOR(tenure)

These join the existing `deferral_based` and `graded_by_service` modes.

## Key Files to Modify

### dbt Layer (Core Calculation)
| File | Action | Purpose |
|------|--------|---------|
| `dbt/macros/get_points_based_match_rate.sql` | **CREATE** | New macro pair for points-tier CASE expressions |
| `dbt/models/intermediate/events/int_employee_match_calculations.sql` | **MODIFY** | Add `tenure_based` and `points_based` branches |
| `dbt/dbt_project.yml` | **VERIFY** | Ensure new variables have defaults |

### Python Configuration
| File | Action | Purpose |
|------|--------|---------|
| `planalign_orchestrator/config/workforce.py` | **MODIFY** | Add `TenureMatchTier`, `PointsMatchTier` Pydantic models |
| `planalign_orchestrator/config/export.py` | **MODIFY** | Export new tier variables to dbt |
| `config/simulation_config.yaml` | **MODIFY** | Add default tier configurations |

### API / Studio (P3)
| File | Action | Purpose |
|------|--------|---------|
| `planalign_api/storage/workspace_storage.py` | **MODIFY** | Default config for new modes |
| `planalign_studio/src/components/` | **MODIFY** | Tier editor for points/tenure modes |

## How to Test

### Quick Smoke Test (tenure_based)
```bash
# 1. Edit config/simulation_config.yaml — set employer_match_status to tenure_based
# 2. Add tenure_match_tiers under employer_match section
# 3. Run simulation
source .venv/bin/activate
planalign simulate 2025

# 4. Verify match amounts
python3 -c "
import duckdb
conn = duckdb.connect('dbt/simulation.duckdb')
print(conn.execute('''
  SELECT formula_type, applied_years_of_service,
         employer_match_amount, match_status
  FROM int_employee_match_calculations
  WHERE simulation_year = 2025
  LIMIT 10
''').fetchdf())
conn.close()
"
```

### Quick Smoke Test (points_based)
```bash
# 1. Edit config — set employer_match_status to points_based
# 2. Add points_match_tiers
# 3. Run simulation
planalign simulate 2025

# 4. Verify points and match amounts
python3 -c "
import duckdb
conn = duckdb.connect('dbt/simulation.duckdb')
print(conn.execute('''
  SELECT formula_type, applied_points, applied_years_of_service,
         employer_match_amount, match_status
  FROM int_employee_match_calculations
  WHERE simulation_year = 2025
  LIMIT 10
''').fetchdf())
conn.close()
"
```

### dbt Model Test
```bash
cd dbt
dbt run --select int_employee_match_calculations --vars "simulation_year: 2025, employer_match_status: 'points_based', points_match_tiers: [{min_points: 0, max_points: 40, rate: 25, max_deferral_pct: 6}, {min_points: 40, max_points: null, rate: 100, max_deferral_pct: 6}]" --threads 1
```

### Python Validation Test
```bash
source .venv/bin/activate
pytest tests/ -k "match" -v
```

## Configuration Examples

### Tenure-Based Match
```yaml
# In config/simulation_config.yaml or scenario overrides
# Field names here are Pydantic model fields (match_rate).
# The export function maps match_rate -> rate for dbt variables.
employer_match_status: 'tenure_based'
tenure_match_tiers:
  - min_years: 0
    max_years: 2
    match_rate: 25
    max_deferral_pct: 6
  - min_years: 2
    max_years: 5
    match_rate: 50
    max_deferral_pct: 6
  - min_years: 5
    max_years: 10
    match_rate: 75
    max_deferral_pct: 6
  - min_years: 10
    max_years: null
    match_rate: 100
    max_deferral_pct: 6
```

### Points-Based Match
```yaml
employer_match_status: 'points_based'
points_match_tiers:
  - min_points: 0
    max_points: 40
    match_rate: 25
    max_deferral_pct: 6
  - min_points: 40
    max_points: 60
    match_rate: 50
    max_deferral_pct: 6
  - min_points: 60
    max_points: 80
    match_rate: 75
    max_deferral_pct: 6
  - min_points: 80
    max_points: null
    match_rate: 100
    max_deferral_pct: 6
```

## Architecture Notes

- Match mode is **mutually exclusive** — only one mode active per scenario
- IRS 401(a)(17) compensation cap applies to ALL modes
- Eligibility filtering applies to ALL modes (same `int_employer_eligibility` model)
- `applied_points` column is NULL for non-points modes (same as `applied_years_of_service` is NULL for deferral mode)
- Tier rates in dbt are percentages (50 = 50%); macros divide by 100
- `[min, max)` interval convention: lower inclusive, upper exclusive
