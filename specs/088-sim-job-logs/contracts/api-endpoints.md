# API Contracts: Simulation Job Log Capture

**Branch**: `088-sim-job-logs` | **Date**: 2026-06-03

Router prefix: `/api/simulations` (existing router in `planalign_api/routers/simulations.py`)

---

## New Endpoint

### `GET /{scenario_id}/runs/{run_id}/logs`

Returns a paginated list of log entries for a specific simulation run.

**Path parameters**:
| Parameter     | Type   | Description                        |
|---------------|--------|------------------------------------|
| `scenario_id` | string | Scenario identifier                |
| `run_id`      | string | Run identifier (UUID)              |

**Query parameters**:
| Parameter   | Type | Default | Description                              |
|-------------|------|---------|------------------------------------------|
| `page`      | int  | `1`     | 1-based page number                      |
| `page_size` | int  | `200`   | Lines per page (max: 500)               |
| `severity`  | str  | `null`  | Filter: `INFO`, `WARNING`, `ERROR`, or omit for all |

**Response `200 OK`**:
```json
{
  "run_id": "3f9a2b1c-...",
  "lines": [
    {
      "sequence": 1,
      "timestamp": "2025-01-15T10:30:00.123456Z",
      "severity": "INFO",
      "message": "Simulation started for years 2025-2027"
    },
    {
      "sequence": 2,
      "timestamp": "2025-01-15T10:30:01.456789Z",
      "severity": "INFO",
      "message": "Starting simulation year 2025"
    }
  ],
  "total_lines": 1243,
  "page": 1,
  "page_size": 200,
  "has_more": true,
  "is_running": false,
  "log_available": true
}
```

**Response `200 OK` — log not yet available** (run is pending/just started):
```json
{
  "run_id": "3f9a2b1c-...",
  "lines": [],
  "total_lines": 0,
  "page": 1,
  "page_size": 200,
  "has_more": false,
  "is_running": true,
  "log_available": false
}
```

**Response `404 Not Found`**: Scenario or run not found.

**Behaviour notes**:
- Returns `log_available: false` if `simulation.log` does not exist yet (run is queued or log hasn't been created).
- Returns partial results if the simulation is still running (`is_running: true`) — the client can re-poll or switch to WebSocket for new lines.
- Severity filter is applied client-side over the page slice (server reads all lines then filters); this keeps the implementation simple and avoids needing a line-number index per severity.

---

## Modified Existing Endpoint

### `GET /{scenario_id}/artifacts/{artifact_path:path}` (existing — no change required)

Log download reuses this endpoint:
```
GET /api/simulations/{scenario_id}/artifacts/runs/{run_id}/simulation.log
```

Response headers set automatically by existing code:
```
Content-Type: text/plain
Content-Disposition: attachment; filename="simulation.log"
```

---

## Modified WebSocket Message Schema

### `ws://host/api/ws/{run_id}` (existing — schema extended)

The existing `SimulationTelemetry` message is extended to include a rolling window of the most recent log lines.

**Before** (existing schema excerpt):
```json
{
  "run_id": "...",
  "progress": 42,
  "current_stage": "EVENT_GENERATION",
  "current_year": 2025,
  "total_years": 3,
  "performance_metrics": { ... },
  "recent_events": [ ... ],
  "timestamp": "..."
}
```

**After** (new field added):
```json
{
  "run_id": "...",
  "progress": 42,
  "current_stage": "EVENT_GENERATION",
  "current_year": 2025,
  "total_years": 3,
  "performance_metrics": { ... },
  "recent_events": [ ... ],
  "recent_log_lines": [
    {
      "sequence": 341,
      "timestamp": "2025-01-15T10:31:45.123Z",
      "severity": "INFO",
      "message": "Generated 2847 hire events for year 2025"
    },
    {
      "sequence": 342,
      "timestamp": "2025-01-15T10:31:45.234Z",
      "severity": "INFO",
      "message": "Model int_termination_events completed in 1.2s"
    }
  ],
  "timestamp": "..."
}
```

**`recent_log_lines`**: Sliding window of the last 50 log lines produced by the simulation. Clients use this for live display. On page load or reconnect, clients call `GET .../logs?page=1` to read historical lines, then subscribe to the WebSocket for new ones.

---

## Frontend TypeScript Types

```typescript
// New types
export interface SimulationLogLine {
  sequence: number;
  timestamp: string;          // ISO 8601
  severity: "INFO" | "WARNING" | "ERROR";
  message: string;
}

export interface LogPage {
  run_id: string;
  lines: SimulationLogLine[];
  total_lines: number;
  page: number;
  page_size: number;
  has_more: boolean;
  is_running: boolean;
  log_available: boolean;
}

// Extension to existing type
export interface SimulationTelemetry {
  // ... existing fields unchanged ...
  recent_log_lines: SimulationLogLine[];  // NEW
}
```
