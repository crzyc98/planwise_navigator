# Implementation Plan: Simulation Job Log Capture

**Branch**: `088-sim-job-logs` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/088-sim-job-logs/spec.md`

---

## Summary

Every simulation run must persist its full log output to a `simulation.log` file in the run directory so analysts can view, tail, and download logs through PlanAlign Studio without server filesystem access. The approach:

1. Create `runs/{run_id}/` at simulation *start* (not completion) so partial logs survive failures.
2. Write each subprocess output line incrementally to `simulation.log` via a new `SimulationLogWriter` service.
3. Expose a paginated REST endpoint for log viewing and extend the existing WebSocket telemetry with a `recent_log_lines` rolling window for live streaming.
4. Log download reuses the existing `download_artifact` endpoint — zero new backend plumbing.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript with React 18 (frontend)
**Primary Dependencies**: FastAPI (backend API), Pydantic v2 (models), asyncio (subprocess streaming), React 18 + Tailwind CSS v4 (frontend)
**Storage**: Filesystem — `simulation.log` in run directory; no DuckDB changes
**Testing**: pytest (backend unit + integration), React component tests
**Target Platform**: Unix server (Linux), macOS dev
**Project Type**: Web service (FastAPI backend + React frontend)
**Performance Goals**: Log lines appear in WebSocket within 5 seconds; log file download completes in under 10 seconds for any size
**Constraints**: Log file written incrementally (each line flushed to disk); no in-memory-only buffering that would lose data on crash
**Scale/Scope**: Single run produces up to ~100K log lines for a multi-year simulation; log viewer pages at 200 lines/request

---

## Constitution Check

### I. Event Sourcing & Immutability ✅

Log lines are **not** workforce events and must **not** enter `fct_yearly_events`. They are operational metadata stored in flat files. The event store remains unchanged. Log files are append-only by design (written incrementally, never modified after write).

### II. Modular Architecture ✅

One new focused module: `log_writer.py` (~60 lines, single responsibility). Modifications to existing modules are minimal surgical additions. No module will exceed the 600-line limit. No circular dependencies introduced.

### III. Test-First Development ✅

Tests written before implementation:
- `tests/unit/test_simulation_log_writer.py` — unit tests for `SimulationLogWriter`
- `tests/integration/test_simulation_logs.py` — endpoint tests for `GET .../logs`

### IV. Enterprise Transparency ✅

This feature directly supports transparency: all simulation decisions are now durably logged with timestamps and severity, accessible to analysts without server access.

### V. Type-Safe Configuration ✅

New Pydantic v2 models: `SimulationLogLine`, `LogPage`. Extension to `SimulationTelemetry` is additive with a typed field. No raw string manipulation of config.

### VI. Performance & Scalability ✅

Log file is written line-by-line (no full-file rewrites). Paginated endpoint reads only the requested slice. WebSocket window is capped at 50 lines. Virtual scrolling in the frontend prevents DOM overload for large logs.

---

## Project Structure

### Documentation (this feature)

```text
specs/088-sim-job-logs/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api-endpoints.md # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code Changes

```text
planalign_api/
├── models/
│   └── simulation.py                           # +SimulationLogLine, +LogPage, extend SimulationTelemetry
├── services/simulation/
│   ├── log_writer.py                           # NEW: SimulationLogWriter
│   └── service.py                             # Modify _stream_output(), execute_simulation()
├── routers/
│   └── simulations.py                         # +GET /{scenario_id}/runs/{run_id}/logs

planalign_studio/
├── services/
│   └── simulationService.ts                   # +fetchRunLogs(), update WS telemetry types
├── components/simulation/
│   ├── LogViewer.tsx                          # NEW: paginated log viewer component
│   └── RunDetails.tsx (or equivalent)         # Add Logs tab

tests/
├── unit/
│   └── test_simulation_log_writer.py          # NEW: SimulationLogWriter unit tests
└── integration/
    └── test_simulation_logs.py                # NEW: logs endpoint integration tests
```

**Structure Decision**: Single project structure (existing layout). No new packages. Backend changes are surgical additions to the existing simulation service and router. Frontend adds one new component and extends an existing one.

---

## Complexity Tracking

No constitution violations. No complexity justification required.
