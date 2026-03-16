# API Contract: Apply Workforce Parameters

**Feature Branch**: `072-apply-workforce-params`
**Date**: 2026-03-16

## Endpoint

```
POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/apply-workforce-params
```

### Description

Reads workforce parameters from the source scenario (identified by `scenario_id` in the URL) and applies them to one or more target scenarios. DC plan parameters in target scenarios are preserved.

### Path Parameters

| Parameter | Type | Description |
| --------- | ---- | ----------- |
| workspace_id | string | Workspace containing the scenarios |
| scenario_id | string | Source scenario to read workforce params from |

### Request Body

```json
{
  "target_scenario_ids": ["scenario_b_id", "scenario_c_id"]
}
```

| Field | Type | Required | Constraints |
| ----- | ---- | -------- | ----------- |
| target_scenario_ids | string[] | Yes | Non-empty array; must not include source scenario_id |

### Response (200 OK)

```json
{
  "source_scenario_id": "scenario_a_id",
  "results": [
    {
      "scenario_id": "scenario_b_id",
      "scenario_name": "High Growth",
      "success": true,
      "error": null
    },
    {
      "scenario_id": "scenario_c_id",
      "scenario_name": "Conservative",
      "success": true,
      "error": null
    }
  ],
  "total_applied": 2,
  "total_failed": 0
}
```

### Error Responses

| Status | Condition |
| ------ | --------- |
| 404 | Workspace or source scenario not found |
| 422 | Empty target list, source scenario in target list, or invalid scenario IDs |
| 200 (partial) | Some targets fail — response includes per-scenario errors with `total_failed > 0` |

### Partial Failure Example

```json
{
  "source_scenario_id": "scenario_a_id",
  "results": [
    {
      "scenario_id": "scenario_b_id",
      "scenario_name": "High Growth",
      "success": true,
      "error": null
    },
    {
      "scenario_id": "scenario_deleted_id",
      "scenario_name": null,
      "success": false,
      "error": "Scenario not found"
    }
  ],
  "total_applied": 1,
  "total_failed": 1
}
```

## Workforce Parameters Copied

The following config_overrides keys are extracted from the source and merged into each target:

| Category | Config Path | Merge Strategy |
| -------- | ----------- | -------------- |
| Growth | `simulation.target_growth_rate` | Replace value |
| Workforce | `workforce.*` | Replace entire section |
| Compensation | `compensation.*` | Replace entire section |
| New Hire | `new_hire.*` | Replace entire section |
| Promotion Hazard | `promotion_hazard` | Atomic replace (top-level) |
| Age Bands | `age_bands` | Atomic replace (top-level) |
| Tenure Bands | `tenure_bands` | Atomic replace (top-level) |

## Frontend API Client

```typescript
// New function in services/api.ts
export async function applyWorkforceParams(
  workspaceId: string,
  sourceScenarioId: string,
  targetScenarioIds: string[]
): Promise<WorkforceParamsApplyResult>
```
