# API Contract: Active Simulations Endpoint

**Branch**: `045-disable-run-during-sim` | **Date**: 2026-02-11

## New Endpoint

### GET /api/simulations/active

Returns all currently active simulation runs. Used by the frontend on page load/refresh to detect running simulations and restore the disabled button state.

**Request**: No parameters required.

**Response** (200 OK):
```json
{
  "active_runs": [
    {
      "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "scenario_id": "baseline_2025",
      "status": "running",
      "progress": 45,
      "current_stage": "EVENT_GENERATION",
      "started_at": "2026-02-11T14:30:00Z"
    }
  ]
}
```

**Response** (200 OK - No active runs):
```json
{
  "active_runs": []
}
```

**Implementation Notes**:
- Queries the existing `_active_runs` in-memory dictionary in `planalign_api/routers/simulations.py`
- Filters for runs with status in ("pending", "queued", "running")
- No authentication required (single-user desktop application)
- Response should be fast (<50ms) since it reads from memory only

## Existing Endpoints (No Changes)

### POST /api/scenarios/{scenario_id}/run
- Already returns `SimulationRun` with `id` (run_id) — no changes needed
- Already returns 409 if scenario is already running — no changes needed

### GET /api/scenarios/{scenario_id}/run/status
- Already returns current run status — no changes needed
- Used as fallback if the new active endpoint is unavailable

### WS /ws/simulation/{run_id}
- Already streams real-time telemetry — no changes needed
- Frontend reconnects to this after page refresh using run_id from `/api/simulations/active`

## Frontend API Client Addition

Add to `planalign_studio/services/api.ts`:

```typescript
export interface ActiveRun {
  run_id: string;
  scenario_id: string;
  status: string;
  progress: number;
  current_stage: string | null;
  started_at: string;
}

export interface ActiveSimulationsResponse {
  active_runs: ActiveRun[];
}

export async function getActiveSimulations(): Promise<ActiveSimulationsResponse> {
  const response = await fetch(`${API_BASE}/api/simulations/active`);
  return handleResponse<ActiveSimulationsResponse>(response);
}
```
