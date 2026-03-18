# Tasks: Fix Auto Enrollment Runs Despite Being Disabled

**Input**: Design documents from `/specs/074-fix-auto-enroll-disabled/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Tests**: Included — constitution mandates test-first development (Principle III).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the existing config export pipeline is correct before modifying dbt models

- [x] T001 Verify `auto_enrollment_enabled` is exported correctly by running existing tests in tests/unit/orchestrator/test_config_export.py
- [x] T002 Read and document current behavior of `is_auto_enrollment_row` CASE in dbt/models/intermediate/int_enrollment_events.sql (lines 214-220)
- [x] T003 Read and document current behavior of auto-enrollment gating in dbt/models/intermediate/int_proactive_voluntary_enrollment.sql (lines 34-73)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational changes needed — existing infrastructure (config export, dbt variables) is already correct. The fix is localized to dbt model SQL.

**⚠️ CRITICAL**: Phase 1 verification must confirm the variable is exported before proceeding.

**Checkpoint**: Config export verified — dbt model fixes can now begin.

---

## Phase 3: User Story 1 - Disable Auto Enrollment (Priority: P1) 🎯 MVP

**Goal**: When auto enrollment is disabled in DC plan config, zero auto-enrollment events are generated during simulation.

**Independent Test**: Disable auto enrollment, run a simulation, verify zero auto-enrollment events in results.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T004 [P] [US1] Add dbt test that asserts zero auto-enrollment rows when `auto_enrollment_enabled` is false in dbt/tests/test_auto_enrollment_disabled_no_events.sql — test should SELECT from int_enrollment_events WHERE is_auto_enrollment_row = true and assert count = 0 when var is false
- [x] T005 [P] [US1] Add Python test that verifies disabled auto-enrollment produces no auto-enrollment events in tests/integration/test_auto_enrollment_disabled.py — configure SimulationConfig with auto_enrollment.enabled=False, export vars, assert `auto_enrollment_enabled` is False in exported dbt vars

### Implementation for User Story 1

- [x] T006 [P] [US1] Add `auto_enrollment_enabled` gate to `is_auto_enrollment_row` CASE expression in dbt/models/intermediate/int_enrollment_events.sql (line 214-220) — add `WHEN NOT {{ var('auto_enrollment_enabled', true) }} THEN false` as the first WHEN clause, before the scope checks
- [x] T007 [P] [US1] Add `auto_enrollment_enabled` gate to dbt/models/intermediate/int_proactive_voluntary_enrollment.sql — add `AND {{ var('auto_enrollment_enabled', true) }}` to the WHERE clause of the new_hire_population CTE that filters on `is_eligible_for_auto_enrollment`, so proactive auto-enrollment events are suppressed when disabled
- [x] T008 [US1] Run dbt test from T004 with `--vars '{auto_enrollment_enabled: false}'` and verify it passes after the fix

**Checkpoint**: Auto-enrollment disabled setting is now respected. Run `dbt run --select int_enrollment_events int_proactive_voluntary_enrollment --vars '{simulation_year: 2025, auto_enrollment_enabled: false}' --threads 1` and verify zero auto-enrollment events.

---

## Phase 4: User Story 2 - Scope Respected When Enabled (Priority: P2)

**Goal**: Verify that existing scope behavior ("all eligible employees" vs "new hires only") is not broken by the fix.

**Independent Test**: Enable auto enrollment with "new hires only" scope, run simulation, verify only new hires get auto-enrollment events.

### Tests for User Story 2

- [x] T009 [P] [US2] Add dbt test that asserts auto-enrollment events ARE generated when `auto_enrollment_enabled` is true (default) with scope "all_eligible_employees" in dbt/tests/test_auto_enrollment_enabled_generates_events.sql
- [x] T010 [P] [US2] Add dbt test that asserts only new hires receive auto-enrollment events when scope is "new_hires_only" in dbt/tests/test_auto_enrollment_new_hires_only_scope.sql

### Implementation for User Story 2

- [x] T011 [US2] Verify backward compatibility: run existing enrollment dbt models WITHOUT explicitly setting `auto_enrollment_enabled` var and confirm default behavior (enabled) is preserved — run `dbt run --select int_enrollment_events --vars '{simulation_year: 2025}' --threads 1` from dbt/ directory
- [x] T012 [US2] Run all existing enrollment-related dbt tests to confirm no regressions: `dbt test --select int_enrollment_events int_proactive_voluntary_enrollment --threads 1` from dbt/ directory

**Checkpoint**: Scope behavior verified — enabled auto-enrollment with both scope settings works correctly.

---

## Phase 5: User Story 3 - Multi-Year Simulation Consistency (Priority: P3)

**Goal**: The auto-enrollment disabled setting is respected across all years of a multi-year simulation.

**Independent Test**: Disable auto enrollment, run a 3-year simulation, verify zero auto-enrollment events in every year.

### Tests for User Story 3

- [x] T013 [US3] Add Python integration test in tests/integration/test_auto_enrollment_disabled.py that runs a multi-year simulation (2025-2027) with auto_enrollment.enabled=False and asserts zero auto-enrollment events in each simulation year

### Implementation for User Story 3

- [x] T014 [US3] Verify the `auto_enrollment_enabled` var is passed to dbt for every simulation year by reviewing planalign_orchestrator/pipeline/year_executor.py — confirm the var is included in the dbt vars dict for each year's execution, not just the first year
- [x] T015 [US3] Run a manual multi-year simulation with auto-enrollment disabled and verify results: `planalign simulate 2025-2027` with auto_enrollment disabled in config/simulation_config.yaml

**Checkpoint**: Multi-year consistency confirmed — disabled auto-enrollment produces zero events across all simulated years.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [x] T016 Run full existing test suite to confirm no regressions: `pytest -m fast` and `cd dbt && dbt test --threads 1`
- [x] T017 Run quickstart.md validation steps from specs/074-fix-auto-enroll-disabled/quickstart.md
- [x] T018 Verify voluntary enrollment still functions when auto-enrollment is disabled by checking int_proactive_voluntary_enrollment produces voluntary events with demographic rates

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — verification only
- **Foundational (Phase 2)**: Depends on Setup confirmation
- **US1 (Phase 3)**: Depends on Phase 2 — this is the core fix
- **US2 (Phase 4)**: Depends on US1 completion (regression testing)
- **US3 (Phase 5)**: Depends on US1 completion (multi-year validation)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Core fix — must complete first; no dependencies on other stories
- **User Story 2 (P2)**: Regression validation — depends on US1 fix being in place
- **User Story 3 (P3)**: Multi-year validation — depends on US1 fix being in place

### Within Each User Story

- Tests MUST be written and FAIL before implementation (T004/T005 before T006/T007)
- dbt model fixes before verification runs
- Checkpoint validation before moving to next story

### Parallel Opportunities

- T004 and T005 can run in parallel (different files)
- T006 and T007 can run in parallel (different dbt models)
- T009 and T010 can run in parallel (different test files)
- US2 and US3 can run in parallel after US1 completes

---

## Parallel Example: User Story 1

```bash
# Launch tests in parallel (write first, expect failure):
Task T004: "dbt test for disabled auto-enrollment in dbt/tests/test_auto_enrollment_disabled_no_events.sql"
Task T005: "Python test for config export in tests/integration/test_auto_enrollment_disabled.py"

# Launch fixes in parallel (different files):
Task T006: "Fix int_enrollment_events.sql CASE expression"
Task T007: "Fix int_proactive_voluntary_enrollment.sql WHERE clause"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Verify config export is correct
2. Complete Phase 3: Write tests → Apply fix to 2 dbt models → Verify
3. **STOP and VALIDATE**: Run checkpoint — zero auto-enrollment events when disabled
4. This alone resolves the bug reported in Issue #246

### Incremental Delivery

1. US1 → Core bug fix (MVP)
2. US2 → Regression confidence (scope behavior preserved)
3. US3 → Multi-year confidence (all years respected)
4. Each story adds validation confidence without breaking previous stories

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- The fix follows the pattern in `int_auto_enrollment_window_determination.sql` (lines 263-264)
- Default value `true` preserves backward compatibility when var is not set
- Commit after each phase checkpoint
