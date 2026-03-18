# Quickstart: Fix Auto Enrollment Runs Despite Being Disabled

**Branch**: `074-fix-auto-enroll-disabled`

## Problem

Auto-enrollment events are generated even when `auto_enrollment_enabled: false` in DC plan config. The variable is exported to dbt but two models don't check it.

## Files to Modify

1. **`dbt/models/intermediate/int_enrollment_events.sql`** (~line 214-220)
   - Add `auto_enrollment_enabled` check to `is_auto_enrollment_row` CASE expression

2. **`dbt/models/intermediate/int_proactive_voluntary_enrollment.sql`** (~line 34-73)
   - Add `auto_enrollment_enabled` gate to prevent auto-enrollment events when disabled

## Reference Implementation

See `dbt/models/intermediate/int_auto_enrollment_window_determination.sql` lines 263-264 for the correct gating pattern:
```sql
WHERE auto_enrollment_enabled = true
```

## Verify

```bash
# Run enrollment models with auto-enrollment disabled
cd dbt
dbt run --select int_enrollment_events int_proactive_voluntary_enrollment \
  --vars '{simulation_year: 2025, auto_enrollment_enabled: false}' --threads 1

# Check for zero auto-enrollment events
duckdb simulation.duckdb "SELECT COUNT(*) FROM int_enrollment_events WHERE is_auto_enrollment_row = true"
# Expected: 0

# Run tests
dbt test --select int_enrollment_events int_proactive_voluntary_enrollment --threads 1
pytest -m fast
```
