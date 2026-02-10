# Quickstart: Fix Yearly Participation Rate Consistency

**Feature**: 041-fix-yearly-participation-rate
**Date**: 2026-02-10

## What This Fix Does

Changes the per-year participation rate calculation in the analytics service to use only active employees (matching the top-level rate), instead of all employees including terminated ones.

## Files to Change

| File | Change |
| ---- | ------ |
| `planalign_api/services/analytics_service.py` | Fix SQL in `_get_contribution_by_year()` line 185 |

## Files to Create

| File | Purpose |
| ---- | ------- |
| `tests/test_analytics_service.py` | Unit tests for participation rate consistency |

## The Fix (1 line change)

In `planalign_api/services/analytics_service.py`, method `_get_contribution_by_year()`:

**Replace** (line 185):
```sql
COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as participation_rate
```

**With**:
```sql
COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' AND is_enrolled_flag THEN 1 END) * 100.0
  / NULLIF(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' THEN 1 END), 0) as participation_rate
```

## Verification

```bash
# Run the new analytics tests
pytest tests/test_analytics_service.py -v

# Run full test suite to verify no regressions
pytest -m fast
```

## No Frontend Changes

The TypeScript interface already has `participation_rate` on `ContributionYearSummary`. The fix only changes the value computed server-side. No frontend code changes are needed.
