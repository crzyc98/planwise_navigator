# Developer Quickstart: Simulation Job Log Capture

**Branch**: `088-sim-job-logs`

---

## What This Feature Does

Every simulation run now writes a `simulation.log` file to its run directory. Analysts can view and download logs through PlanAlign Studio without SSH access to the server.

**Log file location**:
```
workspaces/{workspace_id}/scenarios/{scenario_id}/runs/{run_id}/simulation.log
```

---

## Files Touched

### Backend (Python)

| File | Change |
|------|--------|
| `planalign_api/models/simulation.py` | Add `SimulationLogLine`, `LogPage` models; extend `SimulationTelemetry` with `recent_log_lines` |
| `planalign_api/services/simulation/log_writer.py` | **New** — `SimulationLogWriter` class: opens log file, writes formatted lines, closes on completion/failure |
| `planalign_api/services/simulation/service.py` | Modify `_stream_output()` to write to `SimulationLogWriter`; modify `execute_simulation()` to create run dir before subprocess launch |
| `planalign_api/services/simulation/run_archiver.py` | Pass `run_dir` as parameter so `execute_simulation()` can create it early |
| `planalign_api/routers/simulations.py` | Add `GET /{scenario_id}/runs/{run_id}/logs` endpoint |

### Frontend (TypeScript/React)

| File | Change |
|------|--------|
| `planalign_studio/services/simulationService.ts` | Add `fetchRunLogs(scenarioId, runId, page, pageSize)` and update WebSocket telemetry type |
| `planalign_studio/components/simulation/LogViewer.tsx` | **New** — paginated log viewer with severity badges and download button |
| `planalign_studio/components/simulation/RunDetails.tsx` (or wherever run details are shown) | Add "Logs" tab/section with `LogViewer` |

### Tests

| File | Change |
|------|--------|
| `tests/unit/test_simulation_log_writer.py` | **New** — unit tests for `SimulationLogWriter` |
| `tests/integration/test_simulation_logs.py` | **New** — integration tests for the logs endpoint |

---

## Running the Tests

```bash
# Unit tests only (fast)
pytest tests/unit/test_simulation_log_writer.py -v

# Integration tests
pytest tests/integration/test_simulation_logs.py -v

# Full suite
pytest -m "fast" -v
```

---

## Manual Testing

1. Start PlanAlign Studio:
   ```bash
   planalign studio
   ```

2. Open a workspace and run a simulation.

3. During the simulation, open the run detail view — you should see live log lines streaming in the Logs tab.

4. After completion, the full log is available in the Logs tab.

5. Click "Download Logs" to download `simulation.log` as a plain text file. Or download it as an artifact:
   ```bash
   curl http://localhost:8000/api/simulations/{scenario_id}/artifacts/runs/{run_id}/simulation.log \
     -o simulation.log
   ```

6. For a failed run, confirm the partial log is accessible.

---

## Key Architecture Decisions

1. **Log written incrementally**: Each subprocess line is written to disk as it arrives. If the server crashes, the partial log is already on disk.

2. **Run directory created at start**: `runs/{run_id}/` is now created before the subprocess launches (not after completion). This is required to open the log file handle.

3. **Download reuses existing artifact endpoint**: No new download endpoint — the existing `GET /{scenario_id}/artifacts/runs/{run_id}/simulation.log` endpoint serves the file automatically since `.log` is already in `ARTIFACT_TYPE_MAP`.

4. **Real-time via existing WebSocket**: `SimulationTelemetry` gets a new `recent_log_lines` field (rolling window of 50). No new WebSocket connection needed.

5. **No DuckDB storage**: Log lines live only in `simulation.log`. They are not workforce events and must not enter the event store.

---

## Log Format

Each line in `simulation.log`:
```
2025-01-15T10:30:00.123456Z [INFO] Simulation started for years 2025-2027
2025-01-15T10:30:01.456789Z [WARNING] Opt-out rate below configured threshold
2025-01-15T10:30:45.789123Z [ERROR] dbt model int_baseline_workforce failed
```

Format: `{UTC timestamp} [{SEVERITY}] {message}`
