# API Contract Extensions: Employer Cost Ratio Metrics

**Date**: 2026-01-07
**Feature**: 013-cost-comparison-metrics

## Overview

This feature extends the existing DC Plan Analytics API. No new endpoints are required.

## Extended Response Schema

### Endpoint: `GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan`

**Response Model**: `DCPlanAnalytics` (extended)

```json
{
  "scenario_id": "string",
  "scenario_name": "string",
  "total_eligible": 0,
  "total_enrolled": 0,
  "participation_rate": 0.0,
  "participation_by_method": {
    "auto_enrolled": 0,
    "voluntary_enrolled": 0,
    "census_enrolled": 0
  },
  "contribution_by_year": [
    {
      "year": 2025,
      "total_employee_contributions": 0.0,
      "total_employer_match": 0.0,
      "total_employer_core": 0.0,
      "total_all_contributions": 0.0,
      "participant_count": 0,
      "average_deferral_rate": 0.0,
      "participation_rate": 0.0,
      "total_employer_cost": 0.0,
      "total_compensation": 0.0,       // NEW
      "employer_cost_rate": 0.0        // NEW
    }
  ],
  "total_employee_contributions": 0.0,
  "total_employer_match": 0.0,
  "total_employer_core": 0.0,
  "total_all_contributions": 0.0,
  "deferral_rate_distribution": [],
  "escalation_metrics": {},
  "irs_limit_metrics": {},
  "average_deferral_rate": 0.0,
  "total_employer_cost": 0.0,
  "total_compensation": 0.0,           // NEW
  "employer_cost_rate": 0.0            // NEW
}
```

### Endpoint: `GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare`

**Response Model**: `DCPlanComparisonResponse` (unchanged structure, extended nested models)

```json
{
  "scenarios": ["baseline_id", "comparison_id"],
  "scenario_names": {
    "baseline_id": "Baseline",
    "comparison_id": "High Match"
  },
  "analytics": [
    // DCPlanAnalytics objects with new fields as above
  ]
}
```

## Field Specifications

### New Fields

| Field | Type | Unit | Precision | Description |
|-------|------|------|-----------|-------------|
| `total_compensation` | float | USD | 2 decimals | Sum of `prorated_annual_compensation` for all active employees |
| `employer_cost_rate` | float | Percent | 2 decimals | `(total_employer_cost / total_compensation) * 100` |

### Edge Case Handling

| Condition | `total_compensation` | `employer_cost_rate` |
|-----------|---------------------|---------------------|
| Normal | Sum of compensation | Calculated % |
| Zero compensation | 0.0 | 0.0 |
| Zero employer cost | Sum of compensation | 0.0 |
| No active employees | 0.0 | 0.0 |

## TypeScript Interface Extensions

```typescript
// planalign_studio/services/api.ts

export interface ContributionYearSummary {
  year: number;
  total_employee_contributions: number;
  total_employer_match: number;
  total_employer_core: number;
  total_all_contributions: number;
  participant_count: number;
  average_deferral_rate: number;
  participation_rate: number;
  total_employer_cost: number;
  total_compensation: number;       // NEW
  employer_cost_rate: number;       // NEW
}

export interface DCPlanAnalytics {
  // ... existing fields ...
  total_compensation: number;       // NEW
  employer_cost_rate: number;       // NEW
}
```

## Backward Compatibility

- All new fields have default values (0.0)
- Existing API consumers will receive additional fields (non-breaking)
- Frontend must handle new fields being present
