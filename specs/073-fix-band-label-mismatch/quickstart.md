# Quickstart: Fix Band Label Mismatches

**Branch**: `073-fix-band-label-mismatch`

## What This Fixes

19 dbt models hardcode age/tenure band labels instead of using centralized `assign_age_band()` / `assign_tenure_band()` macros. 5 models produce actively wrong labels that cause zero-match JOINs with hazard rate tables, silently breaking salary growth and enrollment calculations.

## How to Verify the Bug

```bash
cd dbt
# Build and run a simulation for year 2025
dbt build --threads 1 --fail-fast

# Check for merit raise events - should be non-zero but currently zero due to JOIN mismatches
duckdb simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'RAISE' AND simulation_year = 2025"

# Check band labels in workforce snapshot vs seeds
duckdb simulation.duckdb "
  SELECT DISTINCT age_band FROM fct_workforce_snapshot
  EXCEPT
  SELECT band_label FROM config_age_bands
"
# Should return empty after fix; currently returns 'Under 25'
```

## Fix Pattern

Replace hardcoded CASE statements:
```sql
-- BEFORE (wrong)
CASE WHEN current_age < 25 THEN 'Under 25' ... END AS age_band

-- AFTER (correct - uses macro)
{{ assign_age_band('current_age') }} AS age_band
{{ assign_tenure_band('current_tenure') }} AS tenure_band

-- With expressions (for next-year projections)
{{ assign_age_band('current_age + 1') }} AS age_band
{{ assign_tenure_band('current_tenure + 1') }} AS tenure_band
```

## How to Verify the Fix

```bash
cd dbt
dbt build --threads 1 --fail-fast
dbt test --threads 1

# Verify non-zero events
duckdb simulation.duckdb "SELECT event_type, COUNT(*) FROM fct_yearly_events WHERE simulation_year = 2025 GROUP BY event_type"

# Verify band consistency
duckdb simulation.duckdb "
  SELECT DISTINCT age_band FROM fct_workforce_snapshot
  EXCEPT
  SELECT band_label FROM config_age_bands
"
# Must return zero rows
```

## Key Files

- Macros: `dbt/macros/bands/assign_age_band.sql`, `dbt/macros/bands/assign_tenure_band.sql`
- Seeds: `dbt/seeds/config_age_bands.csv`, `dbt/seeds/config_tenure_bands.csv`
- Schema tests: `dbt/models/intermediate/schema.yml`
