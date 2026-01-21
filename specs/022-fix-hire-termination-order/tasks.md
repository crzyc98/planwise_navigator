# Tasks: Fix Hire Date Before Termination Date Ordering

**Input**: Design documents from `/specs/022-fix-hire-termination-order/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: This feature includes dbt data quality tests as specified in the plan and constitution (Test-First Development principle).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **dbt models**: `dbt/models/intermediate/events/`, `dbt/models/marts/`
- **dbt macros**: `dbt/macros/`
- **dbt tests**: `dbt/tests/data_quality/`
- **Python orchestrator**: `planalign_orchestrator/`
- **Python tests**: `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Modify the shared macro that generates termination dates

- [x] T001 Modify generate_termination_date macro to add hire_date_column parameter in dbt/macros/generate_termination_date.sql

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None required - macro from Phase 1 is the only shared dependency

**⚠️ CRITICAL**: Phase 1 must complete before user story implementation

**Checkpoint**: Macro ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Termination Dates Follow Hire Dates (Priority: P1) 🎯 MVP

**Goal**: Fix experienced termination events to generate dates >= employee hire date

**Independent Test**: Query database for termination_date < hire_date - should return zero records

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T002 [P] [US1] Create dbt test for termination-after-hire validation in dbt/tests/data_quality/test_termination_after_hire.sql

### Implementation for User Story 1

- [x] T003 [US1] Update int_termination_events.sql line ~100 to pass hire_date to generate_termination_date macro in dbt/models/intermediate/events/int_termination_events.sql
- [x] T004 [US1] Update tenure calculation reference line ~106 to use the constrained termination date in dbt/models/intermediate/events/int_termination_events.sql

### Validation for User Story 1

- [x] T005 [US1] Run dbt build for int_termination_events and verify test passes with `dbt test --select test_termination_after_hire --vars "simulation_year: 2026" --threads 1`

**Checkpoint**: Experienced termination dates should now be >= hire_date (SC-001, SC-002, SC-003)

---

## Phase 4: User Story 2 - New Hire Termination Date Consistency (Priority: P1)

**Goal**: Verify new hire terminations already constrain dates correctly

**Independent Test**: Query fct_workforce_snapshot for new_hire_termination records - all should have termination_date > hire_date

### Verification for User Story 2

- [x] T006 [US2] Verify int_new_hire_termination_events.sql already constrains dates in dbt/models/intermediate/events/int_new_hire_termination_events.sql (no changes needed, already implemented at lines 71-73)

**Checkpoint**: New hire terminations already enforced (verification only - no code changes needed)

---

## Phase 5: User Story 3 - Polars Pipeline Parity (Priority: P2)

**Goal**: Update Polars pipeline to enforce same hire-before-termination constraint

**Independent Test**: Run simulation in Polars mode and verify zero employees with termination_date < hire_date

### Implementation for User Story 3

- [x] T007 [US3] Update _generate_termination_date_expr method to accept hire_date column in planalign_orchestrator/polars_event_factory.py:394-423
- [x] T008 [US3] Update generate_termination_events method call at line ~837 to pass hire_date in planalign_orchestrator/polars_event_factory.py
- [x] T009 [US3] Update generate_new_hire_termination_events method call at line ~1414 to pass hire_date in planalign_orchestrator/polars_event_factory.py

### Validation for User Story 3

- [x] T010 [US3] Run Polars mode simulation and verify SC-004 (parity) with `planalign simulate 2026 --mode polars --verbose`

**Checkpoint**: Both SQL and Polars pipelines should produce identical results (SC-004)

---

## Phase 6: User Story 4 - Tenure At Termination Accuracy (Priority: P1)

**Goal**: Fix fct_workforce_snapshot to calculate tenure to termination_date for terminated employees

**Independent Test**: Query terminated employees and verify current_tenure = floor((termination_date - hire_date) / 365.25)

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T011 [P] [US4] Create dbt test for tenure-at-termination validation in dbt/tests/data_quality/test_tenure_at_termination.sql

### Implementation for User Story 4

- [x] T012 [US4] Update fct_workforce_snapshot.sql to use calculate_tenure macro with termination_date parameter for terminated employees in dbt/models/marts/fct_workforce_snapshot.sql
- [x] T013 [US4] Ensure terminated employee tenure is recalculated in final select, not carried from base_workforce in dbt/models/marts/fct_workforce_snapshot.sql

### Validation for User Story 4

- [x] T014 [US4] Run dbt build for fct_workforce_snapshot and verify test passes with `dbt test --select test_tenure_at_termination --vars "simulation_year: 2026" --threads 1`
- [x] T015 [US4] Run specific regression test: employee hired 2024-08-01, terminated 2026-01-10 should have tenure=1 (SC-007)

**Checkpoint**: All terminated employees should have tenure calculated to termination_date (SC-005, SC-006, SC-007, SC-008)

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation and documentation

- [ ] T016 [P] Run full simulation for year 2026 and validate all success criteria with `planalign simulate 2026 --verbose`
- [ ] T017 [P] Run quickstart.md validation queries to confirm all fixes working
- [ ] T018 Update CLAUDE.md Active Technologies section if needed (no updates expected)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: N/A for this feature
- **User Stories (Phase 3-6)**: All depend on Phase 1 macro being complete
  - US1 and US4 are P1 priority and share files - execute US1 first
  - US2 is verification only - no code changes
  - US3 (P2) is Python changes - can run in parallel with US4
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on T001 (macro) - Modifies int_termination_events.sql
- **User Story 2 (P1)**: No dependencies - verification only
- **User Story 3 (P2)**: Depends on T001 (macro) - Modifies polars_event_factory.py
- **User Story 4 (P1)**: Depends on US1 completion - Modifies fct_workforce_snapshot.sql

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Model changes before validation
- Story complete before moving to next priority

### Parallel Opportunities

- T002 and T011 (tests) can run in parallel after Phase 1
- T007, T008, T009 (Polars) can run in parallel with T012, T013 (SQL)
- T016, T017 (Polish) can run in parallel

---

## Parallel Example: Test Creation

```bash
# Launch all test creation tasks together after Phase 1:
Task: "Create dbt test for termination-after-hire validation in dbt/tests/data_quality/test_termination_after_hire.sql"
Task: "Create dbt test for tenure-at-termination validation in dbt/tests/data_quality/test_tenure_at_termination.sql"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (modify macro)
2. Complete Phase 3: User Story 1 (termination date fix)
3. **STOP and VALIDATE**: Test termination date constraint independently
4. Deploy/demo if ready - most critical bug is fixed

### Incremental Delivery

1. Complete Setup → Macro ready
2. Add User Story 1 → Test independently → Core fix live
3. Add User Story 2 → Verify (no changes needed) → Confirmed working
4. Add User Story 4 → Test independently → Tenure fix live
5. Add User Story 3 → Test independently → Polars parity achieved
6. Each story adds value without breaking previous stories

### Recommended Execution Order

Given file dependencies, the recommended order is:

1. T001 (macro) - MUST be first
2. T002 (test) + T011 (test) - parallel, both fail initially
3. T003, T004, T005 (US1) - termination date fix
4. T006 (US2) - verification only
5. T012, T013, T014, T015 (US4) - tenure fix (same SQL file as US1)
6. T007, T008, T009, T010 (US3) - Polars parity
7. T016, T017, T018 (Polish) - final validation

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (constitution: Test-First Development)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Run dbt with `--threads 1` for work laptop stability (constitution)
