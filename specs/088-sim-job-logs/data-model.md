# Data Model: Simulation Job Log Capture

**Branch**: `088-sim-job-logs` | **Date**: 2026-06-03

---

## Entities

### 1. `SimulationLogLine` (New Pydantic model)

Represents a single parsed log entry in API responses.

| Field       | Type                                      | Required | Description                                |
|-------------|-------------------------------------------|----------|--------------------------------------------|
| `sequence`  | `int`                                     | Yes      | 1-based line number within the log file    |
| `timestamp` | `datetime`                                | Yes      | UTC timestamp when the line was produced   |
| `severity`  | `Literal["INFO", "WARNING", "ERROR"]`     | Yes      | Severity level from `classify_line()`      |
| `message`   | `str`                                     | Yes      | Log message text (raw subprocess output)   |

**Validation rules**:
- `sequence >= 1`
- `severity` must be one of the three levels
- `message` is never empty (blank lines are discarded)

---

### 2. `LogPage` (New Pydantic model)

Pagination envelope for the log viewer REST endpoint.

| Field          | Type                    | Required | Description                                     |
|----------------|-------------------------|----------|-------------------------------------------------|
| `run_id`       | `str`                   | Yes      | The run these log lines belong to               |
| `lines`        | `List[SimulationLogLine]`| Yes     | Requested page of log lines                     |
| `total_lines`  | `int`                   | Yes      | Total lines in the log file                     |
| `page`         | `int`                   | Yes      | Current page number (1-based)                   |
| `page_size`    | `int`                   | Yes      | Lines per page requested                        |
| `has_more`     | `bool`                  | Yes      | True if additional pages exist                  |
| `is_running`   | `bool`                  | Yes      | True if the simulation is still in progress     |
| `log_available`| `bool`                  | Yes      | False if no log file exists yet for this run    |

---

### 3. `SimulationTelemetry` (Existing model — extended)

Extends the existing WebSocket telemetry message to include recent log lines.

**Addition**:

| Field              | Type                    | Required | Description                                         |
|--------------------|-------------------------|----------|-----------------------------------------------------|
| `recent_log_lines` | `List[SimulationLogLine]`| No (default `[]`) | Last N log lines produced (window = 50) |

---

### 4. `RunDetails` (Existing model — no change required)

`RunDetails.artifacts` already lists all files in the run directory. Once `simulation.log` is created in `runs/{run_id}/`, it automatically appears as an artifact with `type="text"`.

---

## Filesystem Artifacts

### Log File

**Path**: `workspaces/{workspace_id}/scenarios/{scenario_id}/runs/{run_id}/simulation.log`

**Format** (one entry per line):
```
2025-01-15T10:30:00.123456Z [INFO] Simulation started for years 2025-2027
2025-01-15T10:30:01.456789Z [INFO] Starting simulation year 2025
2025-01-15T10:30:02.100000Z [WARNING] Opt-out rate below configured threshold
2025-01-15T10:30:45.789123Z [ERROR] dbt run failed: model int_baseline_workforce
```

**Encoding**: UTF-8
**Line separator**: `\n` (Unix)

### Run Directory (updated with log)

```
workspaces/{workspace_id}/scenarios/{scenario_id}/runs/{run_id}/
├── config.yaml              # Existing: simulation configuration
├── run_metadata.json        # Existing: run metadata
├── simulation.duckdb        # Existing: database snapshot (success only)
├── {scenario}_results.xlsx  # Existing: Excel export (success only)
└── simulation.log           # NEW: full log output (always present)
```

**Lifecycle**:
- `runs/{run_id}/` created at simulation **start** (before subprocess launch)
- `simulation.log` opened for write at simulation start, closed on completion or failure
- `simulation.duckdb` and `*.xlsx` written only on successful completion (unchanged)

---

## State Transitions

```
[simulation starts]
       │
       ▼
runs/{run_id}/ created
simulation.log opened (write mode)
       │
       ▼ (each subprocess output line)
line appended to simulation.log
line appended to in-memory recent_log_lines window (last 50)
recent_log_lines broadcast via WebSocket telemetry
       │
       ▼
[simulation completes — success OR failure]
simulation.log file handle closed
       │ (success path only)
       ▼
config.yaml, run_metadata.json, simulation.duckdb, *.xlsx archived
```

---

## Constraints and Validation Rules

- **FR-001 / FR-004**: Log file is created and written incrementally; partial logs are preserved on abnormal exit because the file handle is always flushed per line.
- **FR-003**: Every line stored in the log file includes a timestamp and severity prefix.
- **FR-005**: Download is via the existing `GET /{scenario_id}/artifacts/runs/{run_id}/simulation.log` endpoint.
- **FR-006**: Log is scoped to exactly one `run_id`; the run directory encodes the association.
- **FR-008**: Log retention (90 days) is enforced by the existing `prune_old_runs()` mechanism, which deletes the entire run directory including the log file.
- **FR-009**: Batch scenarios create separate run directories per scenario; each has its own `simulation.log`.

---

## Out of Scope (not modeled)

- Log entries as rows in DuckDB — flat file is the storage medium.
- Full-text search index — P3 feature; search can be implemented by reading the flat file.
- Log shipping or external format conversion.
