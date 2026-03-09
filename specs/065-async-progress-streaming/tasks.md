# Tasks: Async Streaming for Simulation Progress Display

**Input**: Design documents from `/specs/065-async-progress-streaming/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included per Constitution Principle III (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create new files and establish the output capture foundation

- [x] T001 Create `planalign_cli/ui/output_capture.py` with module docstring and imports (Rich Console, threading, sys, os) — empty class stubs for `OutputCapture` and `PlainTextProgressFallback`
- [x] T002 [P] Create `tests/test_progress_display.py` with imports and empty test class stubs for progress callback wiring tests
- [x] T003 [P] Create `tests/test_output_capture.py` with imports and empty test class stubs for output capture mechanism tests

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that ALL user stories depend on — the output capture mechanism and TTY detection

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement `OutputCapture` class in `planalign_cli/ui/output_capture.py`: accepts a Rich `Console` instance, provides a `capture_line(line: str)` method that calls `console.print()` to safely render text above the Rich Live display area, and a `is_tty() -> bool` static method using `sys.stdout.isatty()`
- [x] T005 Implement `PlainTextProgressFallback` class in `planalign_cli/ui/output_capture.py`: implements the same `ProgressCallback` protocol as `LiveProgressTracker` (methods: `update_year`, `update_stage`, `stage_completed`, `update_events`, `year_validation`) but uses plain `print()` statements instead of Rich Live rendering — used when `is_tty()` returns False
- [x] T006 Write tests in `tests/test_output_capture.py`: test that `OutputCapture.capture_line()` calls `console.print()`, test that `PlainTextProgressFallback` emits plain text for each progress method, test `is_tty()` returns False when stdout is redirected (use `io.StringIO`)
- [x] T007 Add `on_dbt_line` method to `LiveProgressTracker` class in `planalign_cli/commands/simulate.py` (around line 463): accepts a string line parameter and calls `self._live.console.print(line)` if `self._live` is active and `self.verbose` is True — this is the safe way to show dbt output during Rich Live rendering

**Checkpoint**: Foundation ready — output capture mechanism and TTY detection are in place

---

## Phase 3: User Story 1 — Real-Time Progress Visibility (Priority: P1) MVP

**Goal**: Enable live-updating progress bars during multi-year simulation by wiring the disabled `progress_callback` to `LiveProgressTracker`

**Independent Test**: Run `planalign simulate 2025-2027` and observe live progress bars advancing through years and stages without display corruption

### Tests for User Story 1

- [x] T008 [P] [US1] Write test in `tests/test_progress_display.py`: test that `create_orchestrator()` returns a `ProgressAwareOrchestrator` when `progress_callback` is provided (not None) — mock the orchestrator and verify the wrapper is applied
- [x] T009 [P] [US1] Write test in `tests/test_progress_display.py`: test that `LiveProgressTracker.update_year()`, `update_stage()`, `stage_completed()` correctly update internal state (`current_year`, `current_stage`, `years_completed`, `stage_durations`) — unit test the tracker in isolation without Rich Live

### Implementation for User Story 1

- [x] T010 [US1] In `planalign_cli/commands/simulate.py` (line 138): change `progress_callback=None` to `progress_callback=progress_tracker` — this is the single-line change that enables the entire progress display system
- [x] T011 [US1] In `planalign_cli/commands/simulate.py` (around line 131-145): add TTY detection — if `not sys.stdout.isatty()`, create a `PlainTextProgressFallback` instead of `LiveProgressTracker` and pass it as the callback. Import `PlainTextProgressFallback` from `planalign_cli.ui.output_capture`
- [x] T012 [US1] In `planalign_cli/commands/simulate.py` `LiveProgressTracker.live_display()` method (around line 534): wrap the `Live.start()`/`Live.stop()` in a try/finally block to ensure terminal state is restored on KeyboardInterrupt or any exception — already implemented with try/finally
- [x] T013 [US1] In `planalign_cli/integration/orchestrator_wrapper.py` `EnhancedProgressMonitor._process_line()` (around line 376): fix the stage regex pattern from `📋 Executing stage: (\w+)` to `📋 Starting (\w+)` to match the actual print statement in `year_executor.py` line 159. Also add missing `📊 Generated` event count pattern if not already matching
- [x] T014 [US1] In `planalign_cli/integration/orchestrator_wrapper.py` `EnhancedProgressMonitor.write()` method (around line 362): replace `self.original_stdout.write(text)` with `self.original_stdout.flush()` only (suppress raw stdout write) — when Rich Live is active, raw stdout writes cause corruption. Instead, pass the line to the progress callback's `on_dbt_line()` method for safe rendering via `Console.print()`
- [x] T015 [US1] Add ETA calculation method `_estimated_remaining()` to `LiveProgressTracker` in `planalign_cli/commands/simulate.py` — already implemented via `_add_estimated_remaining()` method

**Checkpoint**: User Story 1 complete — live progress bars work during simulation with clean terminal restoration

---

## Phase 4: User Story 2 — Verbose Mode with dbt Output (Priority: P2)

**Goal**: Enable `--verbose` flag to show dbt subprocess output alongside the progress display without corruption

**Independent Test**: Run `planalign simulate 2025 --verbose` and verify dbt model compilation/execution messages appear cleanly alongside progress bars

### Tests for User Story 2

- [x] T016 [P] [US2] Write test in `tests/test_output_capture.py`: test that `OutputCapture.capture_line()` renders text without ANSI corruption when called during an active Rich `Live` context — use Rich's `Console(file=io.StringIO())` for capture
- [x] T017 [P] [US2] Write test in `tests/test_progress_display.py`: test that `LiveProgressTracker.on_dbt_line()` calls `self._live.console.print()` when verbose=True and is a no-op when verbose=False

### Implementation for User Story 2

- [x] T018 [US2] dbt output routing handled via EnhancedProgressMonitor.write() routing through on_dbt_line callback — no changes needed to DbtRunner itself since stdout redirection captures print() from orchestrator
- [x] T019 [US2] In `planalign_orchestrator/pipeline/year_executor.py`: added `progress_callback` parameter to `YearExecutor.__init__()` for direct stage signaling
- [x] T020 [US2] In `planalign_cli/integration/orchestrator_wrapper.py` `ProgressAwareOrchestrator.__init__()`: wires progress_callback to orchestrator's YearExecutor via `orchestrator.year_executor.progress_callback = progress_callback`
- [x] T021 [US2] In `planalign_cli/commands/simulate.py` `LiveProgressTracker.on_dbt_line()`: guard implemented — falls back to print() when `self._live` is None

**Checkpoint**: Verbose mode works — dbt output appears cleanly alongside progress display

---

## Phase 5: User Story 3 — Stage-by-Stage Progress Awareness (Priority: P2)

**Goal**: Show which specific pipeline stage is executing and provide stage-level progress (e.g., "Stage 3/6")

**Independent Test**: Run a single-year simulation and verify all 6 stage names appear as they execute

### Implementation for User Story 3

- [x] T022 [US3] In `planalign_orchestrator/pipeline/year_executor.py` `execute_workflow_stage()`: added direct callback invocations — `progress_callback.update_stage()` before stage execution and `progress_callback.stage_completed()` after
- [x] T023 [US3] Year-level progress handled via EnhancedProgressMonitor regex matching on `🔄 Starting simulation year` print statement + direct stage callbacks through YearExecutor
- [x] T024 [US3] In `planalign_cli/commands/simulate.py` `_build_status_table()`: added stage counter display (e.g., "Event Generation (3/6)") using stage order mapping

**Checkpoint**: Stage-by-stage progress visible — operators can see exactly which stage is running

---

## Phase 6: User Story 4 — Cross-Platform Terminal Compatibility (Priority: P3)

**Goal**: Ensure progress display works correctly on Linux, macOS, and Windows without rendering artifacts

**Independent Test**: Run simulation on each target platform and verify no ANSI artifacts or freezing

### Implementation for User Story 4

- [x] T025 [US4] In `planalign_cli/ui/output_capture.py` `is_tty()`: Windows-specific detection implemented — checks `os.name`, `TERM`, `WT_SESSION`, and falls back to Rich Console.is_terminal
- [x] T026 [US4] Rich Live handles terminal resize natively — no additional SIGWINCH handler needed
- [x] T027 [US4] Tests written in `tests/test_output_capture.py`: tests for posix TTY, Windows with WT_SESSION, and Windows fallback to Rich detection

**Checkpoint**: Cross-platform compatibility verified

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup across all user stories

- [x] T028 Run full test suite `pytest -m fast` — 522 passed, 1 pre-existing failure (unrelated datetime bug in test_run_cleanup.py), no regressions
- [ ] T029 Run manual validation per quickstart.md: `planalign simulate 2025`, `planalign simulate 2025-2027`, `planalign simulate 2025 --verbose`, and `planalign simulate 2025 > /tmp/log.txt` (piped)
- [x] T030 Review all modified files for SonarQube compliance: cognitive complexity <15, no bare except, no mutable defaults, functions <40 lines per CLAUDE.md standards

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001-T003) — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (T004-T007)
- **User Story 2 (Phase 4)**: Depends on User Story 1 (T010 must be complete — callback must be wired)
- **User Story 3 (Phase 5)**: Depends on User Story 1 (T010 must be complete)
- **User Story 4 (Phase 6)**: Depends on Foundational (T004-T005) — can run parallel with US1-US3
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Requires Foundational phase only — no story dependencies
- **User Story 2 (P2)**: Requires US1 T010 (callback wired) — builds on the enabled progress system
- **User Story 3 (P2)**: Requires US1 T010 (callback wired) — can run parallel with US2
- **User Story 4 (P3)**: Requires Foundational only — can run parallel with US1-US3

### Within Each User Story

- Tests written FIRST, verified to FAIL before implementation
- Foundation modules before wiring tasks
- Wiring before display enhancements
- Core implementation before edge case handling

### Parallel Opportunities

- T002, T003 can run in parallel (different test files)
- T008, T009 can run in parallel (different test methods, same file but independent)
- T016, T017 can run in parallel (different test files)
- US2 and US3 can run in parallel after US1 T010 is complete
- US4 can run in parallel with all other user stories

---

## Parallel Example: User Story 1

```bash
# Launch tests in parallel (both in tests/test_progress_display.py but independent):
Task: "T008 - Test create_orchestrator returns ProgressAwareOrchestrator when callback provided"
Task: "T009 - Test LiveProgressTracker state updates"

# After tests pass, implementation tasks T010-T015 are sequential (same files)
```

## Parallel Example: After US1 Complete

```bash
# US2 and US3 can run in parallel:
Task: "T018-T021 - User Story 2 (verbose mode)"
Task: "T022-T024 - User Story 3 (stage-by-stage progress)"
# US4 can also run in parallel:
Task: "T025-T027 - User Story 4 (cross-platform)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T007)
3. Complete Phase 3: User Story 1 (T008-T015)
4. **STOP and VALIDATE**: Run `planalign simulate 2025-2027` — verify live progress bars work
5. This alone delivers the core value: real-time progress visibility

### Incremental Delivery

1. Setup + Foundational → Output capture mechanism ready
2. Add User Story 1 → Live progress bars work → **MVP complete**
3. Add User Story 2 → Verbose mode works alongside progress → Deploy
4. Add User Story 3 → Stage-by-stage visibility → Deploy
5. Add User Story 4 → Cross-platform hardening → Deploy
6. Polish → Full validation and cleanup

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- The core fix is T010 (one line change) + T014 (suppress raw stdout) — everything else is supporting infrastructure
- Constitution Principle III requires tests; they are included in each user story phase
- All modified files must stay under 600 lines per Constitution Principle II
- Commit after each task or logical group
