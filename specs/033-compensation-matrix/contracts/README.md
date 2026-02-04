# API Contracts: Multi-Year Compensation Matrix

**Feature**: 033-compensation-matrix
**Date**: 2026-02-03

## No New Contracts Required

This feature is a **frontend-only enhancement** that uses existing API contracts.

### Existing Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/workspaces/{workspace_id}/analytics/dc-plan/compare` | GET | Fetch comparison data including compensation |

### Data Already Available

The `total_compensation` field is already included in the API response:

```json
{
  "scenarios": ["scenario_1", "scenario_2"],
  "scenario_names": {
    "scenario_1": "Baseline",
    "scenario_2": "High Growth"
  },
  "analytics": [
    {
      "scenario_id": "scenario_1",
      "scenario_name": "Baseline",
      "contribution_by_year": [
        {
          "year": 2025,
          "total_employer_cost": 1200000,
          "total_compensation": 15000000,  // ← Already present
          "employer_cost_rate": 0.08
        }
      ],
      "total_compensation": 45000000  // ← Aggregate also present
    }
  ]
}
```

### Why No Backend Changes

1. The `total_compensation` field was added in E013 (Employer Cost Ratio Metrics)
2. Backend analytics service already calculates and returns this data
3. TypeScript types in `api.ts` already define the field (line 807)
