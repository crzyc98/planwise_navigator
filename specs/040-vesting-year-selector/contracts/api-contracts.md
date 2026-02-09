# API Contracts: Vesting Year Selector

**Feature**: 040-vesting-year-selector
**Date**: 2026-02-09

## New Endpoint

### GET `/api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting/years`

Retrieve the list of available simulation years for vesting analysis in a given scenario.

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | `string` | Workspace identifier |
| `scenario_id` | `string` | Scenario identifier |

**Response** `200 OK`:

```json
{
  "years": [2025, 2026, 2027],
  "default_year": 2027
}
```

| Field | Type | Description |
|-------|------|-------------|
| `years` | `int[]` | Available simulation years, sorted ascending |
| `default_year` | `int` | The most recent year (recommended default selection) |

**Response** `404 Not Found`:

```json
{
  "detail": "Workspace not found"
}
```

```json
{
  "detail": "Scenario not found"
}
```

```json
{
  "detail": "Simulation data not found. Ensure the scenario has completed simulation."
}
```

**Notes**:
- Returns years from actual simulation data (not config), ensuring only valid years are listed.
- Uses read-only database connection via `DatabasePathResolver`.
- Reuses existing workspace/scenario validation pattern from `analyze_vesting` endpoint.

## Modified Endpoint (no changes needed)

### POST `/api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting`

The existing analysis endpoint already accepts `simulation_year` in the request body. No backend changes required. The frontend will now include this field when the user selects a year.

**Request body** (unchanged):

```json
{
  "current_schedule": { "schedule_type": "graded_5_year", "name": "5-Year Graded" },
  "proposed_schedule": { "schedule_type": "cliff_3_year", "name": "3-Year Cliff" },
  "simulation_year": 2025
}
```

The `simulation_year` field is optional. When omitted, the backend defaults to the final simulation year (existing behavior preserved).

## Frontend API Client

### New Function: `getScenarioYears`

```typescript
interface ScenarioYearsResponse {
  years: number[];
  default_year: number;
}

export async function getScenarioYears(
  workspaceId: string,
  scenarioId: string
): Promise<ScenarioYearsResponse>
```

### Modified Function: `analyzeVesting` (no changes)

The existing function already passes the full `VestingAnalysisRequest` object (which includes `simulation_year?: number`) via `JSON.stringify(request)`. No client changes needed — the frontend component just needs to include the field in the request object.
