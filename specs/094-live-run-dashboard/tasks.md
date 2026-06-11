# Tasks: Live Simulation Run Dashboard

**Input**: Design documents from `/specs/094-live-run-dashboard/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included for backend modules (constitution III mandates test-first; deterministic JSON protocol makes them cheap). Frontend is verified manually via quickstart.md (no React test harness exists in this repo and none is being added).

**Organization**: Phases 3–6 map to spec user stories US1 (live stats, P1), US4 (reliable telemetry, P1), US2 (activity feed, P2), US3 (trend chart, P3) — ordered by priority, then spec order.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 / US4 from spec.md

## Phase 1: Setup

**Purpose**: Confirm the environment supports the plan; no scaffolding needed (all target directories exist).

- [x] T001 Verify `recharts` is present in planalign_studio/package.json (plan relies on it for US3) and that `pytest -m fast` runs green on the current branch before changes; note baseline

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The structured telemetry channel (orchestrator emitter → stdout protocol → API parser → per-run state → WS snapshot) that every user story consumes.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 [P] Add Pydantic v2 models `TelemetryMilestone`, `EventTypeCounts`, `PerformanceSample`, `RunTelemetrySnapshot`, and WS message envelope (discriminated on `type`: snapshot/update/milestone/heartbeat) to planalign_api/models/simulation.py per data-model.md
- [x] T003 [P] Add matching TypeScript interfaces (`TelemetryMilestone`, `EventTypeCounts`, `PerformanceSample`, `RunTelemetrySnapshot`, WS message union) to planalign_studio/services/api.ts
- [x] T004 [P] Write failing fast tests for the telemetry emitter (record shapes for run_started/stage_started/stage_completed/year_completed/run_completed, sentinel prefix, single-line ≤8KB, env-var gating) in tests/test_telemetry_emitter.py
- [x] T005 [P] Write failing fast tests for structured stdout parsing (sentinel JSON fast path, malformed-sentinel resilience, regex fallback for plain lines, structured values taking precedence over regex guesses) in tests/test_output_parser_structured.py
- [x] T006 Implement `TelemetryEmitter` in planalign_orchestrator/pipeline/telemetry_emitter.py: hook callbacks printing `PLANALIGN_TELEMETRY|{json}` lines per contracts/telemetry-stdout-protocol.md, including the `year_completed` per-event-type aggregate query against fct_yearly_events using the orchestrator's own connection; gated by `PLANALIGN_STRUCTURED_TELEMETRY=1`
- [x] T007 Register emitter callbacks with `HookManager` in planalign_orchestrator/pipeline_orchestrator.py (stage/year boundary hooks; no-op when env flag unset)
- [x] T008 [P] Set `PLANALIGN_STRUCTURED_TELEMETRY=1` in `_build_env()` in planalign_api/services/simulation/service.py
- [x] T009 Add structured fast path to planalign_api/services/simulation/output_parser.py: detect sentinel, `json.loads` payload, expose typed records; keep regex heuristics only for non-sentinel lines; once any structured record is seen, suppress regex-derived stage/year/count updates (make T005 pass)
- [x] T010 Write failing fast tests for per-run telemetry state (snapshot accumulation, milestone cap 200 + warning rate-limit 20, perf-sample ring buffer 600, terminal-state retention, snapshot replay on subscribe, sequence monotonicity) in tests/test_telemetry_state.py
- [x] T011 Extend planalign_api/services/telemetry_service.py with `RunTelemetryState` per data-model.md: accumulate updates/counts/milestones/samples, build `RunTelemetrySnapshot`, retain terminal state (stop clearing on completion; discard only when a new run starts for the same scenario), send snapshot to new subscribers (make T010 pass)
- [x] T012 Update planalign_api/websocket/handlers.py to the envelope protocol per contracts/websocket-messages.md: send `snapshot` message on connect before any deltas, then `update`/`milestone` messages; keep 30s heartbeat
- [x] T013 Route structured records in planalign_api/services/simulation/service.py: `_stream_output`/`_process_output_line` feed parsed records into `TelemetryService` state (stage/year/counts/samples), throttle `update` broadcasts to ≥1s, and keep `update_run_status` in sync

**Checkpoint**: `pytest -m fast` green; a manual run shows sentinel lines in simulation.log and the WS delivers a `snapshot` message on connect.

---

## Phase 3: User Story 1 — See Meaningful Live Stats While a Simulation Runs (Priority: P1) 🎯 MVP

**Goal**: Replace the placeholder with live event counts by type and "Year N of M" per-year progress; meaningful idle state.

**Independent Test**: Start a 3-year run; counts panel updates ≤5s after each year's event generation completes; final counts match `duckdb ... "SELECT event_type, COUNT(*) FROM fct_yearly_events GROUP BY 1"` (quickstart US1).

- [x] T014 [P] [US1] Create planalign_studio/components/simulation/LiveStatsPanel.tsx: event-count tiles per type (HIRE/TERMINATION/PROMOTION/RAISE/ENROLLMENT + total), "Year N of M" indicator with per-year stage progress, "exact through year Y" caption from `event_counts.as_of_year`
- [x] T015 [US1] Wire LiveStatsPanel into planalign_studio/components/SimulationControl.tsx in place of the `[Real-time Performance Graph Placeholder]` block, fed from the telemetry hook's snapshot/update data (existing hook is fine for this story; US4 swaps it out underneath)
- [x] T016 [US1] Implement the idle state in planalign_studio/components/SimulationControl.tsx: when no run is active, show last-run summary (from scenario `last_run_at`/`last_run_id`) or a "start a simulation" prompt — no placeholder text remains (FR-007)
- [x] T017 [US1] Manual validation per quickstart US1: run 3-year simulation, verify boundary updates and exact final counts vs DuckDB (SC-002, SC-004)

**Checkpoint**: US1 fully functional — live counts + per-year progress + idle state, accurate vs persisted events.

---

## Phase 4: User Story 4 — Reliable Live Telemetry (Priority: P1)

**Goal**: Correct reconnect/backoff, full resync on (re)connect, staleness indication, REST polling fallback, guaranteed terminal state.

**Independent Test**: Kill/restore network mid-run at various points (quickstart US4): recovery ≤10s after connectivity returns, polling fallback after retry exhaustion, terminal state always reached ≤30s.

- [x] T018 [P] [US4] Write failing fast tests for `GET /api/scenarios/{scenario_id}/run/telemetry` (200 with snapshot during run, telemetry=null after API restart simulation, not_run scenario, 404 unknown scenario, never touches scenario DuckDB) in tests/test_run_telemetry_endpoint.py
- [x] T019 [US4] Implement `GET /api/scenarios/{scenario_id}/run/telemetry` in planalign_api/routers/simulations.py per contracts/rest-telemetry-snapshot.md (make T018 pass)
- [x] T020 [US4] Fix `get_run_status` in planalign_api/routers/simulations.py: report run-registry truth with persisted scenario status as fallback; never fabricate progress=100/completed and never report a terminal scenario as running
- [x] T021 [US4] Guarantee terminal telemetry in planalign_api/services/simulation/service.py: success, failure, and cancel paths all push a terminal-status update into `TelemetryService` state (failure keeps last-known progress instead of resetting to 0; cancel emits cancelled status) (FR-015)
- [x] T022 [US4] Add `fetchRunTelemetrySnapshot(scenarioId)` to planalign_studio/services/api.ts calling the new endpoint
- [x] T023 [US4] Rewrite planalign_studio/services/websocket.ts as `useRunTelemetry(runId, scenarioId)`: retry counter/timers in `useRef` (fixes stale-closure backoff bug), exponential backoff 2s·2^n capped at 5 attempts, state machine idle→connecting→live⇄stale→reconnecting→polling→terminal, snapshot replaces local state / update merges / milestone appends by sequence, 15s staleness timer counting heartbeats as liveness, polling fallback every 5s via `fetchRunTelemetrySnapshot` with WS upgrade retry every 30s, initial REST fetch on mount for instant refresh-restore
- [x] T024 [P] [US4] Create planalign_studio/components/simulation/ConnectionStatusBadge.tsx rendering live / stale ("last update Xs ago") / reconnecting / degraded-polling / terminal states from the hook's connection state
- [x] T025 [US4] Swap SimulationControl.tsx (and its completion-navigation effect) onto `useRunTelemetry` + ConnectionStatusBadge; completion detection driven by terminal status (not `progress === 100` heuristics); manual validation per quickstart US4 scenarios 1–4 (SC-005, SC-007, SC-008)

**Checkpoint**: Both P1 stories done — accurate live stats over a connection that survives drops, refreshes, and proxy-blocked WS.

---

## Phase 5: User Story 2 — Useful Activity Feed Instead of Raw Event Noise (Priority: P2)

**Goal**: Milestone feed (stage transitions, year summaries, warnings/errors) replaces the per-employee Event Stream panel entirely.

**Independent Test**: 3-year run produces dozens of milestone entries (one per stage transition + per year summary), warnings/errors visually distinct, history replays after refresh (quickstart US2).

- [x] T026 [US2] Complete server-side milestone derivation in planalign_api/services/telemetry_service.py + planalign_api/services/simulation/service.py: stage_started/stage_completed/year_completed milestones from structured records; warning/error milestones from the existing severity classifier with dedup + rate limit (≤20 warnings/run); terminal milestone on completed/failed/cancelled; year_completed message format "Year 2025 complete — 142 hires, 98 terminations (48.2s)" (extend tests in tests/test_telemetry_state.py first)
- [x] T027 [P] [US2] Create planalign_studio/components/simulation/ActivityFeed.tsx: newest-first timestamped milestone list, severity styling (info/warning/error), year-summary detail rendering, auto-scroll pinned to newest with manual-scroll override
- [x] T028 [US2] Remove the raw Event Stream panel and all `recentEvents`/`recent_events` rendering from planalign_studio/components/SimulationControl.tsx; mount ActivityFeed in its place fed by the hook's milestone list (FR-003 — no verbose toggle)
- [ ] T029 [US2] Manual validation per quickstart US2: stage/year milestones present, forced failure shows distinct error milestone + failed terminal state, refresh mid-run replays full history (SC-003)

**Checkpoint**: Feed is milestone-grain; raw per-employee noise is gone from the run screen.

---

## Phase 6: User Story 3 — Live Performance Trend Chart (Priority: P3)

**Goal**: Live throughput + memory trend chart in the stats card.

**Independent Test**: Chart accumulates points for the full run, remains readable and responsive on a 10+ minute run, final trend persists until navigation (quickstart US3).

- [x] T030 [P] [US3] Create planalign_studio/components/simulation/PerformanceTrendChart.tsx: Recharts LineChart with dual Y-axes (events/sec, memory MB) over elapsed time, seeded from snapshot `performance_samples`, appending from updates, client cap 600 points with drop-every-other downsampling
- [x] T031 [US3] Mount PerformanceTrendChart in planalign_studio/components/SimulationControl.tsx below the existing metric tiles (the placeholder div location); freeze chart on terminal state; manual validation per quickstart US3 (SC-006)

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T032 SonarQube-compliance pass over all new/modified Python and TS files (cognitive complexity ≤15, ≤13 params — group hook config into dataclasses if needed, no bare except, no dead code), refactoring planalign_api/services/simulation/service.py helpers if `_process_output_line` grew
- [x] T033 [P] Run full `pytest -m fast` and the integration suite touching simulation execution (`pytest -m integration -k simulation`) — all green
- [ ] T034 Execute quickstart.md end-to-end (all spot-checks incl. sentinel-line grep and REST curl); fix any gaps found
- [x] T035 [P] Update CHANGELOG.md (MINOR: feature 094) and remove any now-dead code paths (`recent_events` plumbing left unused after T028, `_simulate_progress` dev helper if orphaned)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none
- **Phase 2 (Foundational)**: blocks all stories. Internal order: T002/T003/T004/T005 in parallel → T006 (needs T004) → T007 → T008; T009 (needs T005); T010 → T011 (needs T002) → T012/T013 (need T011)
- **Phase 3 (US1)**: needs Phase 2. T014 parallel with T016; T015 after T014; T017 last
- **Phase 4 (US4)**: needs Phase 2; independent of US1 code except T025 touches SimulationControl.tsx (serialize T015/T016 → T025 if done by one person). T018 → T019 → T020; T021 independent; T022 → T023; T024 parallel; T025 last
- **Phase 5 (US2)**: needs Phase 2; T026 → (T027 parallel) → T028 → T029. T028 touches SimulationControl.tsx (serialize after T025)
- **Phase 6 (US3)**: needs Phase 2; T030 → T031 (touches SimulationControl.tsx, serialize after T028)
- **Phase 7 (Polish)**: needs all desired stories

### Key file-contention note

`planalign_studio/components/SimulationControl.tsx` is modified by T015, T016, T025, T028, T031 — these MUST be sequential. All other cross-story work is parallel-safe.

### Parallel Opportunities

```text
Phase 2 wave 1: T002 ∥ T003 ∥ T004 ∥ T005
Phase 2 wave 2: T006 ∥ T009 ∥ T010   (then T007→T008, T011→T012/T013)
After Phase 2:  backend US4 (T018–T021) ∥ frontend US1 (T014–T016) ∥ US2 server (T026) ∥ US3 chart (T030)
```

---

## Implementation Strategy

**MVP first**: Phase 1 → Phase 2 → Phase 3 (US1). Stop and validate: live counts + year progress over the existing (still-buggy) hook is already a visible win. Then Phase 4 (US4) hardens the channel — together these complete both P1 stories. Phases 5–6 are independent increments; each ends at a demoable checkpoint.

**Single-developer order**: T001 → T002…T013 → T014…T017 → T018…T025 → T026…T029 → T030…T031 → T032…T035.

---

## Notes

- Backend tests (T004, T005, T010, T018, T026-extension) are written before their implementations per constitution III; verify they fail first.
- Counts are exact at year boundaries only (clarification 2026-06-10) — do not add mid-year count streaming.
- Telemetry state is in-memory only; do not add persistence (clarification 2026-06-10).
- The API must never open the scenario DuckDB during a run; counts come from the orchestrator's own connection (T006).
- Commit after each task or logical group.
