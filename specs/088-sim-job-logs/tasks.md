# Tasks: Simulation Job Log Capture

**Input**: Design documents from `/specs/088-sim-job-logs/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story this task belongs to
- Tests are included per constitution Principle III (Test-First Development)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project initialization needed (existing codebase). Confirm log directory structure and create the log writer module file.

- [x] T001 Create empty `planalign_api/services/simulation/log_writer.py` module file (establishes import path before Phase 2 work begins)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and the `SimulationLogWriter` service that all three user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Add `SimulationLogLine` Pydantic v2 model (fields: `sequence: int`, `timestamp: datetime`, `severity: Literal["INFO","WARNING","ERROR"]`, `message: str`) to `planalign_api/models/simulation.py`
- [x] T003 [P] Add `LogPage` Pydantic v2 model (fields: `run_id`, `lines: List[SimulationLogLine]`, `total_lines`, `page`, `page_size`, `has_more`, `is_running`, `log_available`) to `planalign_api/models/simulation.py`
- [x] T004 [P] Implement `SimulationLogWriter` class in `planalign_api/services/simulation/log_writer.py` — constructor takes `run_dir: Path`; `write_line(timestamp, severity, message)` appends `{ISO_UTC} [{SEVERITY}] {message}\n` and flushes; `close()` closes file handle
- [x] T005 Modify `SimulationService.execute_simulation()` in `planalign_api/services/simulation/service.py` to create `runs/{run_id}/` directory before subprocess launch (move run dir creation out of `archive_run()`)
- [x] T006 Wire `SimulationLogWriter` into `_stream_output()` in `planalign_api/services/simulation/service.py` — open log writer before async loop, pass classified severity and line text to `write_line()` on each iteration, close in `finally` block
- [x] T007 Handle log writer close on failure path in `_handle_simulation_failure()` in `planalign_api/services/simulation/service.py` — ensure partial logs are flushed and closed when simulation fails or is cancelled
- [x] T008 Update `archive_run()` in `planalign_api/services/simulation/run_archiver.py` — remove run dir creation (now happens in T005); accept pre-existing `run_dir` path parameter instead of computing it

**Checkpoint**: Run a simulation and confirm `runs/{run_id}/simulation.log` is created with timestamped lines. Verify failed run also produces a partial log.

---

## Phase 3: User Story 1 — View Logs for a Completed Simulation Run (Priority: P1) 🎯 MVP

**Goal**: Analysts can open any completed (or failed) run in PlanAlign Studio and read the full log output, and download it as a plain text file.

**Independent Test**: Navigate to any completed simulation run in PlanAlign Studio, open its detail view, and confirm the full log output is displayed. Click "Download Logs" and verify the file downloads correctly.

### Tests for User Story 1

> **Write these FIRST — they must FAIL before implementation begins**

- [x] T009 [P] [US1] Write unit tests for `SimulationLogWriter` in `tests/unit/test_simulation_log_writer.py` — cover: file creation, line format, severity mapping, flush-per-line, close idempotency, missing directory handling
- [x] T010 [P] [US1] Write integration tests for `GET /{scenario_id}/runs/{run_id}/logs` in `tests/integration/test_simulation_logs.py` — cover: 200 with log lines, 200 with `log_available=false` when no log, pagination (`page`/`page_size` params), severity filter param, 404 for unknown run

### Implementation for User Story 1

- [x] T011 [US1] Add `GET /{scenario_id}/runs/{run_id}/logs` endpoint to `planalign_api/routers/simulations.py` — reads `simulation.log` from run dir, parses each line into `SimulationLogLine`, returns `LogPage` with pagination; returns `log_available=false` if file does not exist; accepts `?page=1&page_size=200&severity=` query params
- [x] T012 [P] [US1] Add `fetchRunLogs(scenarioId, runId, page, pageSize, severity?)` async function to `planalign_studio/services/simulationService.ts` — calls `GET /api/simulations/{scenarioId}/runs/{runId}/logs`, returns `LogPage`
- [x] T013 [P] [US1] Create `LogViewer.tsx` React component in `planalign_studio/components/simulation/LogViewer.tsx` — displays `SimulationLogLine[]` in a scrollable list with severity badge (colored), timestamp, and message; shows empty state when `log_available=false`; includes "Download Logs" button that links to `GET /api/simulations/{scenarioId}/artifacts/runs/{runId}/simulation.log`
- [x] T014 [US1] Integrate `LogViewer` into run detail view in `planalign_studio/` (whichever component renders run details — check `App.tsx` routes) — add a "Logs" tab or collapsible section; load first page of logs on mount via `fetchRunLogs()`; implement "Load More" button for pagination

**Checkpoint**: US1 fully functional — analysts can view and download logs for any completed or failed run.

---

## Phase 4: User Story 2 — Monitor a Running Simulation in Real Time (Priority: P2)

**Goal**: Analysts can see log lines streaming live in the web interface while a simulation is actively running, without page refresh.

**Independent Test**: Start a simulation through PlanAlign Studio. Confirm log lines appear in the Logs tab incrementally as the simulation runs. Navigate away and return — confirm all prior lines are visible plus new ones.

### Tests for User Story 2

> **Write these FIRST — they must FAIL before implementation begins**

- [x] T015 [P] [US2] Write integration tests for WebSocket telemetry `recent_log_lines` field in `tests/integration/test_simulation_logs.py` — extend existing file with: WebSocket message includes `recent_log_lines` array; lines are in sequence order; window does not exceed 50; field is empty list when no lines produced yet

### Implementation for User Story 2

- [x] T016 [US2] Extend `SimulationTelemetry` Pydantic model in `planalign_api/models/simulation.py` — add `recent_log_lines: List[SimulationLogLine] = []` field
- [x] T017 [US2] Update `TelemetryService.update_telemetry()` in `planalign_api/services/telemetry_service.py` — accept `recent_log_lines: List[SimulationLogLine]` parameter; include in broadcast payload
- [x] T018 [US2] Pass rolling `recent_log_lines` window (last 50 entries) from `_process_output_line()` in `planalign_api/services/simulation/service.py` to `update_telemetry()` — maintain a `deque(maxlen=50)` of `SimulationLogLine` in `_stream_output()` loop and pass snapshot on each telemetry update
- [x] T019 [US2] Update WebSocket telemetry TypeScript type in `planalign_studio/services/simulationService.ts` — add `recent_log_lines: SimulationLogLine[]` to `SimulationTelemetry` interface
- [x] T020 [US2] Update `LogViewer.tsx` in `planalign_studio/components/simulation/LogViewer.tsx` — accept optional `liveLines?: SimulationLogLine[]` prop from WebSocket; merge live lines with paginated lines (dedup by sequence), auto-scroll to bottom when new lines arrive and user is near bottom

**Checkpoint**: US2 functional — real-time log streaming works during active simulations. US1 behaviour unchanged.

---

## Phase 5: User Story 3 — Search and Filter Logs Within a Run (Priority: P3)

**Goal**: Analysts can type a keyword to highlight matching lines or filter by severity level within a run's log output.

**Independent Test**: Open a completed run with a log containing known text. Use keyword search to find that text — matching lines are highlighted. Use severity filter to show only ERROR lines — non-error lines disappear.

### Implementation for User Story 3

- [x] T021 [US3] Add severity filter controls to `LogViewer.tsx` in `planalign_studio/components/simulation/LogViewer.tsx` — add radio/button group for `ALL | INFO | WARNING | ERROR`; pass selected severity to `fetchRunLogs()` so server-side filtering is applied; reset to page 1 on change
- [x] T022 [US3] Add keyword search input to `LogViewer.tsx` in `planalign_studio/components/simulation/LogViewer.tsx` — client-side filter over the current page's lines; highlight matching substring in message text using a `<mark>` element; show match count ("N matches on this page"); clear button

**Checkpoint**: US3 functional — analysts can find specific lines without scrolling. US1 and US2 behaviour unchanged.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Completeness, edge cases, and validation.

- [x] T023 [P] Verify `simulation.log` appears automatically in `RunDetails.artifacts` list (it should via existing artifact scan logic) — if not, confirm `ARTIFACT_TYPE_MAP` has `".log"` entry in `planalign_api/constants.py` (it already does per research)
- [x] T024 [P] Verify cancelled simulation also produces a partial log — cancel a running simulation and confirm `simulation.log` exists in the run directory
- [x] T025 Run `pytest tests/unit/test_simulation_log_writer.py tests/integration/test_simulation_logs.py -v` — all tests must pass
- [x] T026 Run quickstart.md manual validation steps end-to-end (run simulation, view live logs, complete, download, check failed run)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **blocks all user stories**
  - T002 and T003 are parallel (both modify `models/simulation.py` — do sequentially or merge)
  - T004 is parallel with T002/T003 (different file: `log_writer.py`)
  - T005, T006, T007, T008 must be sequential (all modify `service.py` / `run_archiver.py`)
- **Phase 3 (US1)**: Depends on Phase 2 completion
- **Phase 4 (US2)**: Depends on Phase 2 completion; integrates with Phase 3 `LogViewer`
- **Phase 5 (US3)**: Depends on Phase 3 `LogViewer` existing
- **Phase 6 (Polish)**: Depends on desired stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on US2 or US3
- **US2 (P2)**: Can start after Phase 2 — T020 extends `LogViewer` from US1 (plan US1 first or stub the component)
- **US3 (P3)**: Depends on `LogViewer` from US1 existing (T013)

### Parallel Opportunities Within Phase 2

```bash
# These can run simultaneously:
T002 + T003: Models in simulation.py (edit same file sequentially)
T004: log_writer.py (independent file — fully parallel with T002/T003)
```

### Parallel Opportunities Within Phase 3 (US1)

```bash
# After T009/T010 are written (tests fail):
Backend:  T011 → add endpoint to simulations.py
Frontend: T012 → add fetchRunLogs to simulationService.ts
Frontend: T013 → create LogViewer.tsx component
# Then:
T014: Wire LogViewer into run detail view (depends on T012 + T013)
```

---

## Parallel Example: User Story 1 (after tests written)

```bash
# Run in parallel once test skeletons exist:
Backend task:   "T011 — Add GET .../logs endpoint to routers/simulations.py"
Frontend task:  "T012 — Add fetchRunLogs() to simulationService.ts"
Frontend task:  "T013 — Create LogViewer.tsx component"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T008) — log file now written to disk
3. Complete Phase 3: US1 (T009–T014) — analysts can view and download logs
4. **STOP and VALIDATE**: Check that `simulation.log` is created, the endpoint returns lines, the viewer displays them, and the download works
5. Ship US1 — this resolves the stated analyst blocker

### Incremental Delivery

1. Phase 1 + 2 → Log file on disk for every run
2. Phase 3 (US1) → Log viewing + download in Studio ← **resolves analyst blocker**
3. Phase 4 (US2) → Real-time streaming during active runs
4. Phase 5 (US3) → Search and filter for large logs
5. Phase 6 (Polish) → Tests passing, edge cases verified

---

## Notes

- [P] tasks = different files or independent operations, no shared state
- [Story] label maps task to specific user story for traceability
- T002 and T003 both edit `models/simulation.py` — merge into one edit or do sequentially
- `simulation.log` download uses the *existing* `GET /{scenario_id}/artifacts/runs/{run_id}/simulation.log` endpoint — no new download endpoint needed
- Constitution III (Test-First): Tests T009/T010/T015 must be written and confirmed failing before their implementation tasks run
- Do not store log lines in DuckDB — flat file only (constitution I: log lines are not workforce events)
