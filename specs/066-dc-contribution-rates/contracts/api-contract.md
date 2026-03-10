# API Contract: Contribution Rate Fields

**Feature**: 066-dc-contribution-rates
**Date**: 2026-03-09

## Changed Endpoints

No new endpoints. Two existing endpoints return extended response models:

### GET `/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan`

### GET `/{workspace_id}/analytics/dc-plan/compare`

## Response Schema Changes

### ContributionYearSummary (in `contribution_by_year` array)

**Added fields** (backward-compatible — additive only):

```json
{
  "year": 2025,
  "total_employee_contributions": 5000000.00,
  "total_employer_match": 2500000.00,
  "total_employer_core": 1000000.00,
  "total_all_contributions": 8500000.00,
  "participant_count": 500,
  "average_deferral_rate": 0.06,
  "participation_rate": 85.0,
  "total_employer_cost": 3500000.00,
  "total_compensation": 50000000.00,
  "employer_cost_rate": 7.0,
  "employee_contribution_rate": 10.0,
  "match_contribution_rate": 5.0,
  "core_contribution_rate": 2.0,
  "total_contribution_rate": 17.0
}
```

### DCPlanAnalytics (top-level aggregate)

**Added fields**:

```json
{
  "employer_cost_rate": 7.0,
  "employee_contribution_rate": 10.0,
  "match_contribution_rate": 5.0,
  "core_contribution_rate": 2.0,
  "total_contribution_rate": 17.0
}
```

## Field Specifications

| Field | Type | Unit | Range | Default | Description |
|-------|------|------|-------|---------|-------------|
| `employee_contribution_rate` | float | % | 0-100 | 0.0 | Employee deferrals as % of total compensation |
| `match_contribution_rate` | float | % | 0-100 | 0.0 | Employer match as % of total compensation |
| `core_contribution_rate` | float | % | 0-100 | 0.0 | Employer core as % of total compensation |
| `total_contribution_rate` | float | % | 0-100 | 0.0 | Sum of employee + match + core rates |

## Backward Compatibility

- All new fields have default values (0.0)
- Existing fields unchanged
- No breaking changes to request parameters
- Existing frontend consumers that don't use the new fields will continue working
