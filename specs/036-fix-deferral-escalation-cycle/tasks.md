# Tasks: Fix Deferral Rate Escalation Circular Dependency

**Input**: Design documents from `/specs/036-fix-deferral-escalation-cycle/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included -- the spec explicitly requires automated tests (US3, FR-001 through FR-008, SC-005).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the existing codebase is in a compilable state and configuration is correct before making changes.

- [ ] T001 Verify escalation configuration is complete and correct in config/simulation_config.yaml (lines 639-651): confirm `deferral_auto_escalation.enabled: true`, all 7 parameters present
- [ ] T002 Verify dbt project compiles without errors by running `dbt compile --threads 1` from dbt/ directory
- [ ] T003 Verify orchestrator config export maps all escalation vars correctly by inspecting planalign_orchestrator/config/export.py (lines 162-184, 210-227)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Clean up the disabled model and verify the corrected model is the only active version. MUST complete before any user story work.

**CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Delete the obsolete disabled model at dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql.disabled
- [ ] T005 Verify the active model at dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql uses ephemeral materialization with tags `['EVENT_GENERATION', 'E068A_EPHEMERAL']` and has no `{{ ref('fct_workforce_snapshot') }}` reference
- [ ] T006 Verify the cycle-breaking mechanism: confirm the Year 2+ branch (line ~160) uses `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` (direct table reference, NOT `{{ ref() }}`) in dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql
- [ ] T007 Verify orchestrator pipeline stage ordering: confirm `int_deferral_rate_escalation_events` is last in EVENT_GENERATION stage and `int_deferral_rate_state_accumulator_v2` is in STATE_ACCUMULATION stage in planalign_orchestrator/pipeline/workflow.py
- [ ] T008 Run `dbt compile --threads 1` from dbt/ directory and confirm zero circular dependency errors with the escalation model active

**Checkpoint**: Foundation ready -- the corrected model compiles without cycles. User story implementation can now begin.

---

## Phase 3: User Story 1 - Deferral Escalation Events Generated for Eligible Employees (Priority: P1) MVP

**Goal**: Activate the corrected escalation model so it produces real `deferral_escalation` events for eligible enrolled employees in a single-year simulation.

**Independent Test**: Run a single-year simulation (2025) and verify non-zero escalation events exist in `fct_yearly_events` with correct rate increments.

### Implementation for User Story 1

- [ ] T009 [US1] Run a single-year simulation (`planalign simulate 2025`) with escalation enabled and capture the output to verify the pipeline completes successfully
- [ ] T010 [US1] Query `fct_yearly_events` for `event_type = 'deferral_escalation'` and `simulation_year = 2025` to confirm non-zero event count (SC-002)
- [ ] T011 [US1] Verify escalation events have correct rate arithmetic: confirm `new_deferral_rate = previous_deferral_rate + escalation_rate` and `new_deferral_rate <= max_escalation_rate` for all events in fct_yearly_events
- [ ] T012 [US1] Verify no employee with `previous_deferral_rate >= escalation_cap` (0.10) received an escalation event (FR-005, SC-004) by querying fct_yearly_events
- [ ] T013 [US1] Verify the config toggle works: temporarily set `deferral_escalation_enabled: false` in config/simulation_config.yaml, re-run simulation, confirm zero escalation events (FR-004), then restore to `true`
- [ ] T014 [US1] Verify escalation events include audit trail fields (previous_rate, new_rate, escalation_rate, event_details) are non-null for all escalation events in fct_yearly_events (FR-007)
- [ ] T015 [US1] Verify determinism: run the same single-year simulation twice with the same seed and confirm identical escalation event counts and employee IDs (FR-006, SC-006)

**Checkpoint**: User Story 1 complete -- single-year escalation events are generated correctly. The core fix is validated.

---

## Phase 4: User Story 2 - Multi-Year Escalation State Carries Forward Correctly (Priority: P2)

**Goal**: Validate that escalation state accumulates correctly across simulation years (rates increment each year, cap enforced, new hires eligible after delay).

**Independent Test**: Run a 3-year simulation (2025-2027) and verify an employee's deferral rate increments each year (e.g., 6% -> 7% -> 8%).

**Depends on**: User Story 1 (single-year must work before multi-year)

### Implementation for User Story 2

- [ ] T016 [US2] Run a 3-year simulation (`planalign simulate 2025-2027`) and confirm the pipeline completes successfully for all 3 years
- [ ] T017 [US2] Query `int_deferral_rate_state_accumulator_v2` to verify rate accumulation: find at least one employee whose `current_deferral_rate` increases by the configured increment (0.01) each year across 2025, 2026, 2027 (SC-003)
- [ ] T018 [US2] Verify cap enforcement across years: confirm no employee in `int_deferral_rate_state_accumulator_v2` has `current_deferral_rate > escalation_cap` (0.10) in any simulation year
- [ ] T019 [US2] Verify `escalations_received` increments correctly: for employees with escalations in multiple years, confirm the count matches the number of years they received escalation events
- [ ] T020 [US2] Verify that employees who reach the cap in one year receive zero escalation events in subsequent years by querying `fct_yearly_events` for those employee IDs
- [ ] T021 [US2] Verify new hires enrolled mid-simulation are eligible for escalation after the configured delay period (`first_escalation_delay_years: 1`) by checking `fct_yearly_events` for new hire employee IDs in Year 2+

**Checkpoint**: User Story 2 complete -- multi-year accumulation works correctly. Rates carry forward, cap is enforced, timing is respected.

---

## Phase 5: User Story 3 - Escalation Events Validated by Automated Tests (Priority: P3)

**Goal**: Replace all placeholder tests with real assertions and add a pytest integration test so the feature is protected from regression.

**Independent Test**: Run `dbt test --select tag:escalation --threads 1` and `pytest tests/test_escalation_events.py` -- all tests pass.

**Depends on**: User Story 1 and 2 (need real data in the database to write meaningful tests against)

### Implementation for User Story 3

- [ ] T022 [US3] Re-enable the commented-out schema tests for `int_deferral_rate_escalation_events` in dbt/models/intermediate/schema.yml (around line 2137-2145): uncomment the model definition with description, config tags, and add column-level tests for `employee_id` (not_null), `event_type` (accepted_values: ['deferral_escalation']), `simulation_year` (not_null), `new_deferral_rate` (not_null)
- [ ] T023 [P] [US3] Replace the placeholder `dq_deferral_escalation_validation.sql` at dbt/models/marts/data_quality/dq_deferral_escalation_validation.sql with real validation queries that check: (1) no escalations for employees above rate cap, (2) no duplicate escalation events per employee per year, (3) escalation effective dates are on the configured date (default Jan 1), (4) new_deferral_rate > previous_deferral_rate for all events
- [ ] T024 [P] [US3] Replace the placeholder `test_deferral_escalation.sql` at dbt/tests/data_quality/test_deferral_escalation.sql with real assertions that query `fct_yearly_events` for `event_type = 'deferral_escalation'` and validate: no rates above cap, no duplicate employee+year combinations, all events have non-null audit fields
- [ ] T025 [US3] Verify existing bug-fix tests still pass by running `dbt test --select test_escalation_bug_fix test_deferral_orphaned_states test_deferral_state_continuity --threads 1` from dbt/ directory
- [ ] T026 [US3] Create pytest integration test at tests/test_escalation_events.py that: (1) runs a single-year simulation, (2) queries fct_yearly_events for deferral_escalation events, (3) asserts non-zero count, (4) asserts all new_deferral_rate <= configured cap, (5) asserts deterministic output across two runs
- [ ] T027 [US3] Run full escalation test suite: `dbt test --select tag:escalation --threads 1` and `pytest tests/test_escalation_events.py -v` -- confirm all tests pass (SC-005)

**Checkpoint**: User Story 3 complete -- at least 3 automated tests cover escalation scenarios (basic eligibility, multi-year accumulation, cap enforcement).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Clean up orphaned models and update documentation.

- [ ] T028 [P] Update the schema documentation for `int_deferral_rate_escalation_events` in dbt/models/intermediate/schema.yml: add full model description referencing Epic E035, add column descriptions for key fields (new_deferral_rate, previous_deferral_rate, escalation_rate), add appropriate tags (escalation, deferral, events, epic_e035)
- [ ] T029 [P] Evaluate orphaned legacy model `int_deferral_escalation_state_accumulator` at dbt/models/intermediate/int_deferral_escalation_state_accumulator.sql: confirm no downstream `ref()` exists, and if confirmed orphaned, remove it from the dbt project and from planalign_orchestrator/pipeline/workflow.py STATE_ACCUMULATION stage list
- [ ] T030 [P] Evaluate orphaned legacy model `int_deferral_rate_state_accumulator` (v1) at dbt/models/intermediate/int_deferral_rate_state_accumulator.sql: confirm no downstream `ref()` exists, and if confirmed orphaned, remove it from the dbt project
- [ ] T031 Run full simulation (`planalign simulate 2025-2027`) after all cleanup changes to confirm no regressions
- [ ] T032 Run `dbt compile --threads 1` one final time to confirm the project compiles cleanly with all changes applied

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies -- can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion -- BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 (Phase 3) completion (needs single-year working first)
- **User Story 3 (Phase 5)**: Depends on User Story 1 and 2 completion (needs real data in DB for tests)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) -- No dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 -- multi-year requires single-year to work first
- **User Story 3 (P3)**: Depends on US1 and US2 -- tests need real data from successful simulations

### Within Each Phase

- T001-T003 (Setup): Sequential -- verify config, then compile, then check export
- T004-T008 (Foundational): T004 first (delete disabled file), T005-T007 parallel, T008 last (compile check)
- T009-T015 (US1): T009 first (run simulation), T010-T015 can run in sequence after simulation completes
- T016-T021 (US2): T016 first (run 3-year simulation), T017-T021 can run after simulation completes
- T022-T027 (US3): T022 first (enable schema), T023-T024 parallel, T025 after schema changes, T026 after T025, T027 last
- T028-T032 (Polish): T028-T030 parallel, T031-T032 sequential after cleanup

### Parallel Opportunities

- T005, T006, T007 can run in parallel (different files, read-only verification)
- T023, T024 can run in parallel (different dbt test files)
- T028, T029, T030 can run in parallel (different files, independent changes)

---

## Parallel Example: User Story 3

```bash
# After T022 (re-enable schema), launch parallel test replacements:
Task: "Replace dq_deferral_escalation_validation.sql placeholder at dbt/models/marts/data_quality/"
Task: "Replace test_deferral_escalation.sql placeholder at dbt/tests/data_quality/"

# After parallel tasks complete, run verification:
Task: "Verify existing bug-fix tests still pass"
Task: "Create pytest integration test at tests/test_escalation_events.py"
Task: "Run full escalation test suite"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (verify config)
2. Complete Phase 2: Foundational (delete disabled file, verify compile)
3. Complete Phase 3: User Story 1 (run simulation, validate events)
4. **STOP and VALIDATE**: Query `fct_yearly_events` for non-zero escalation events
5. MVP delivered -- escalation events are being generated

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Validate single-year escalation -> MVP delivered
3. Add User Story 2 -> Validate multi-year accumulation -> Full feature working
4. Add User Story 3 -> All tests pass -> Regression protection in place
5. Polish -> Cleanup orphans, update docs -> Production-ready

### Estimated Scope

- **Total tasks**: 32
- **Phase 1 (Setup)**: 3 tasks (verification only)
- **Phase 2 (Foundational)**: 5 tasks (1 deletion + 4 verifications)
- **Phase 3 (US1 - MVP)**: 7 tasks (simulation runs + query validations)
- **Phase 4 (US2)**: 6 tasks (multi-year simulation + query validations)
- **Phase 5 (US3)**: 6 tasks (test creation + verification)
- **Phase 6 (Polish)**: 5 tasks (cleanup + final validation)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Most tasks in US1 and US2 are validation queries, not code changes -- the corrected model already exists
- The primary code changes are: delete `.disabled` file (T004), re-enable schema tests (T022), replace test placeholders (T023-T024), create pytest test (T026), and optional legacy model cleanup (T029-T030)
- Commit after each phase completion
- Stop at any checkpoint to validate story independently
