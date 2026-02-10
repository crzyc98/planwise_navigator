# API Contract: Fix Yearly Participation Rate Consistency

**Feature**: 041-fix-yearly-participation-rate
**Date**: 2026-02-10

## Summary

No API contract changes. The fix modifies only the server-side computation logic that populates existing fields. All endpoint paths, request/response schemas, and field names remain identical.

## Affected Endpoints (behavior change only)

### GET `/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan`

**Response model**: `DCPlanAnalytics` (unchanged schema)

**Behavioral change**: Each entry in `contribution_by_year[]` will have its `participation_rate` field computed using only active employees as the population, rather than all employees.

**Before**:
```json
{
  "contribution_by_year": [
    {
      "year": 2025,
      "participation_rate": 72.5,
      "...": "..."
    }
  ],
  "participation_rate": 85.0
}
```
Note: Per-year rate (72.5) differs from top-level (85.0) because per-year includes terminated employees in denominator.

**After**:
```json
{
  "contribution_by_year": [
    {
      "year": 2025,
      "participation_rate": 85.0,
      "...": "..."
    }
  ],
  "participation_rate": 85.0
}
```
Note: Per-year final-year rate now matches top-level rate because both use active-only population.

### GET `/{workspace_id}/analytics/dc-plan/compare`

**Response model**: `DCPlanComparisonResponse` (unchanged schema)

**Behavioral change**: Same as above — each scenario's `contribution_by_year[].participation_rate` will use active-only population.

## Unchanged Fields

All other fields in `ContributionYearSummary` remain computed over the full population (active + terminated):
- `total_employee_contributions`
- `total_employer_match`
- `total_employer_core`
- `total_all_contributions`
- `participant_count`
- `average_deferral_rate`
- `total_employer_cost`
- `total_compensation`
- `employer_cost_rate`
