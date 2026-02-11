# Data Model: Disable Run Button During Active Simulation

**Branch**: `045-disable-run-during-sim` | **Date**: 2026-02-11

## Entities

### SimulationRunningState (Frontend - React State)

Represents the global simulation running state shared across all components via Layout context.

| Field | Type | Description |
|-------|------|-------------|
| `isSimulationRunning` | `boolean` | Whether any simulation is currently active |
| `activeRunId` | `string \| null` | UUID of the currently active simulation run |
| `runningScenarioId` | `string \| null` | ID of the scenario being simulated |
| `runStartedAt` | `number \| null` | Timestamp (ms) when the run started, for timeout calculation |

**State Transitions**:

```
IDLE                    → RUNNING         (user clicks Run, API returns successfully)
RUNNING                 → IDLE            (telemetry reports COMPLETED or failed)
RUNNING                 → IDLE            (safety timeout expires with no heartbeat)
PAGE_LOAD               → RUNNING         (GET /api/simulations/active returns active run)
PAGE_LOAD               → IDLE            (GET /api/simulations/active returns empty)
```

### ActiveSimulationResponse (Backend - API Response)

Returned by the new `GET /api/simulations/active` endpoint.

| Field | Type | Description |
|-------|------|-------------|
| `active_runs` | `ActiveRun[]` | List of currently active simulation runs (0 or 1 in practice) |

### ActiveRun (Backend - Nested Object)

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `string` | UUID of the active run |
| `scenario_id` | `string` | ID of the scenario being run |
| `status` | `string` | Current status: "pending", "queued", "running" |
| `progress` | `int` | 0-100 progress percentage |
| `current_stage` | `string \| null` | Current pipeline stage name |
| `started_at` | `string` | ISO 8601 timestamp |

## Relationships

- `SimulationRunningState.activeRunId` → corresponds to `ActiveRun.run_id` from the backend
- `SimulationRunningState.runningScenarioId` → corresponds to `ActiveRun.scenario_id`
- WebSocket connection uses `activeRunId` to subscribe to telemetry updates at `/ws/simulation/{run_id}`

## Validation Rules

- At most one simulation can be active at a time (enforced by DuckDB single-writer + backend 409 check)
- `activeRunId` and `runningScenarioId` must both be set or both be null (atomic state transition)
- `runStartedAt` must be set when transitioning to RUNNING and cleared when transitioning to IDLE
- Safety timeout (30 minutes): if `Date.now() - runStartedAt > 1_800_000` and no heartbeat received, transition to IDLE
