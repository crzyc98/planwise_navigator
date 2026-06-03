# Research: Simulation Job Log Capture

**Branch**: `088-sim-job-logs` | **Date**: 2026-06-03

---

## Finding 1: How Simulation Output Is Currently Handled

**Decision**: Log lines are captured in a rolling in-memory buffer only; nothing is persisted.

**Evidence from codebase**:

`planalign_api/services/simulation/service.py` — `_stream_output()` (lines 562–600):
- Reads subprocess stdout line-by-line via an async iterator
- Maintains a `output_buffer: List[str]` capped at 50 lines (for error context only)
- Calls `logger.debug/warning/error()` on each line (Python `logging` module — not persisted per run)
- Sends the last ~20 lines as `recent_events` via WebSocket telemetry (`SimulationTelemetry`)
- **No file write occurs at any point**

**Implication**: Adding `simulation.log` persistence requires modifying `_stream_output()` to open a file handle and write each line as it arrives.

---

## Finding 2: Run Archive Directory Structure

**Decision**: Write `simulation.log` to `runs/{run_id}/simulation.log`.

**Evidence**:

`run_archiver.py` — `archive_run()` creates `scenario_path/runs/{run_id}/` and saves:
- `config.yaml`
- `run_metadata.json`
- `simulation.duckdb` (copy)
- `{name}_results.xlsx`

**Critical gap**: `archive_run()` is called only on *successful* completion. For failed runs, the run directory is never created and no artifacts are saved. To support FR-004 (preserve logs for failed runs), the run directory must be created at simulation *start*, not at archive time.

**Rationale**: Creating `runs/{run_id}/` before subprocess launch lets us open `simulation.log` for incremental writing. On failure, the partial log is already on disk. On success, `archive_run()` then writes the remaining artifacts.

---

## Finding 3: Artifact System Already Supports `.log` Files

**Decision**: Reuse the existing artifact serving infrastructure for log download — no new download endpoint needed.

**Evidence** from `planalign_api/constants.py`:
```python
ARTIFACT_TYPE_MAP = {".log": "text", ...}
MEDIA_TYPE_MAP = {".log": "text/plain", ...}
```

The existing `GET /{scenario_id}/artifacts/{artifact_path:path}` endpoint (`routers/simulations.py`, line 761) serves any file from `scenario_path/`. Passing `runs/{run_id}/simulation.log` as the artifact path will serve the log file with `Content-Type: text/plain` and trigger a browser download.

The `get_run()` endpoint already lists all files in the run directory as artifacts, so `simulation.log` will automatically appear in `RunDetails.artifacts` once it exists.

---

## Finding 4: Real-Time Log Delivery via Existing WebSocket

**Decision**: Extend `SimulationTelemetry` with a `recent_log_lines` field (last 50 lines). The UI subscribes to the existing WebSocket and receives incremental log lines alongside telemetry.

**Evidence**:

`planalign_api/websocket/manager.py` — `ConnectionManager` is already wired to the simulation run via `run_id`. The telemetry service broadcasts `SimulationTelemetry` objects on every output line.

`planalign_api/models/simulation.py` — `SimulationTelemetry` already has `recent_events: List[RecentEvent]` as a rolling window pattern. Adding `recent_log_lines: List[LogLine]` follows the same pattern.

**Alternatives considered**:

| Approach | Rationale for rejection |
|----------|------------------------|
| Separate WebSocket for logs | Requires a second WS connection per run; increases client complexity |
| Server-Sent Events (SSE) | Not as bidirectional; no reconnect replay; more frontend plumbing |
| Polling a `/logs/tail` endpoint | Adds latency; not true streaming; wastes connections on completed runs |

**Reconnect behavior**: When a client reconnects mid-run, it reads the persisted log file via REST (paginated endpoint) to catch up on missed lines, then subscribes to the WebSocket for new lines. This is the same pattern used by CI systems (GitHub Actions, CircleCI log replay).

---

## Finding 5: Paginated Log Viewer Endpoint

**Decision**: Add `GET /{scenario_id}/runs/{run_id}/logs` returning parsed log lines with pagination. Reads directly from `simulation.log` — no database storage needed.

**Rationale**: Log lines are already ordered, immutable, and stored in a flat file. Reading them with `offset`/`limit` is trivially efficient. Storing them in DuckDB would be unnecessary overhead and conflicts with the event-sourcing principle (log lines are not workforce events).

**Format of each line in `simulation.log`**:
```
2025-01-15T10:30:00.123456Z [INFO] Starting simulation year 2025
```

**Parsing**: Split at first `]` — timestamp and severity are before it, message after. Lines that don't match this format (raw subprocess output without classification) are stored as `severity=info`.

---

## Finding 6: Severity Classification

**Decision**: Reuse `SimulationOutputParser.classify_line()` for severity, which already exists in `output_parser.py`.

**Evidence**:
`service.py` line 614: `level = SimulationOutputParser.classify_line(line_text)` → returns `"error"`, `"warning"`, or `"info"`.

**Log severity mapping**:
- `"error"` → `ERROR`
- `"warning"` → `WARNING`
- `"info"` → `INFO`

---

## Summary of Unknowns Resolved

| Unknown | Resolution |
|---------|-----------|
| Where to store log files | `runs/{run_id}/simulation.log` — run directory (created at sim start) |
| How to serve log downloads | Existing `download_artifact` endpoint; no new code needed |
| Real-time delivery mechanism | Extend existing WebSocket `SimulationTelemetry` with `recent_log_lines` |
| Log format | `{ISO_timestamp} [{SEVERITY}] {message}` — one line per entry |
| Failed run log persistence | Create run dir before subprocess launch; write incrementally |
| Database storage for logs | Not needed — flat file is sufficient; DuckDB is for event sourcing |
| Log retention 90 days | Handled by existing `prune_old_runs()` run retention system |
