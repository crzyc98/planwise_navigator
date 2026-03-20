# Quickstart: Fix Year-over-Year Voluntary Enrollment Rate Override

**Branch**: `082-fix-yoy-enrollment-rate`

## What's the Bug?

Setting `voluntary_enrollment_rate` to 0% suppresses voluntary enrollment in two of three pathways but **not** the year-over-year conversion pathway in `int_enrollment_events.sql`. Employees still convert via year-over-year at hardcoded 3–8% demographic rates.

## The Fix (1 file, ~1 line)

In `dbt/models/intermediate/int_enrollment_events.sql`, find the year-over-year CTE's `event_probability` calculation (around line 569) and multiply by the voluntary enrollment rate:

```sql
-- BEFORE (missing voluntary_enrollment_rate):
(age_rate * income_multiplier * tenure_multiplier) as event_probability

-- AFTER (consistent with other pathways):
(age_rate * income_multiplier * tenure_multiplier *
 COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)) as event_probability
```

The same multiplier must also be applied in the WHERE clause hash comparison (around line 584-602) if the probability is recalculated there.

## Validation

```bash
cd dbt

# Run the fixed model
dbt run --select int_enrollment_events --vars "simulation_year: 2025" --threads 1

# Run enrollment tests
dbt test --select test_enrollment_architecture --threads 1

# Verify fix: check year-over-year events with rate=0
dbt run --select int_enrollment_events --vars "{simulation_year: 2026, voluntary_enrollment_rate: 0.0}" --threads 1
duckdb simulation.duckdb "SELECT COUNT(*) FROM int_enrollment_events WHERE simulation_year = 2026 AND enrollment_source = 'year_over_year_conversion'"
# Expected: 0
```

## Files

| File | Action |
|------|--------|
| `dbt/models/intermediate/int_enrollment_events.sql` | Modify: add `voluntary_enrollment_rate` multiplier to year-over-year CTE |
| `dbt/tests/test_yoy_respects_voluntary_rate.sql` | Create: validate year-over-year respects voluntary enrollment rate |
