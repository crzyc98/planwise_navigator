# Tasks: Fix Termination Event Data Quality

**Input**: Design documents from `/specs/021-fix-termination-events/`
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

**Purpose**: Create reusable macro for termination date generation

- [X] T001 Create generate_termination_date macro in dbt/macros/generate_termination_date.sql with year-aware hash logic

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None required - macro from Phase 1 is the only shared dependency

**⚠️ CRITICAL**: Phase 1 must complete before user story implementation

**Checkpoint**: Macro ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Realistic Termination Date Distribution (Priority: P1) 🎯 MVP

**Goal**: Fix termination dates to be distributed across all months instead of clustering on a single date

**Independent Test**: Run `dbt run --select int_termination_events --vars "simulation_year: 2026"` and verify dates span all 12 months

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T002 [P] [US1] Create dbt test for monthly distribution validation in dbt/tests/data_quality/test_termination_date_distribution.sql

### Implementation for User Story 1

- [X] T003 [US1] Update int_termination_events.sql line ~100 to use generate_termination_date macro in dbt/models/intermediate/events/int_termination_events.sql
- [X] T004 [US1] Update tenure calculation reference line ~107 to use the same macro-generated date in dbt/models/intermediate/events/int_termination_events.sql
- [X] T005 [P] [US1] Update Polars pipeline to use year-aware hash for date generation parity in planalign_orchestrator/polars_event_factory.py

### Validation for User Story 1

- [X] T006 [US1] Run dbt build for int_termination_events and verify test passes with `dbt test --select test_termination_date_distribution --vars "simulation_year: 2026"`

**Checkpoint**: Termination dates should now be distributed across all months (SC-001, SC-005, SC-006)

---

## Phase 4: User Story 2 - Accurate New Hire Status Classification (Priority: P1)

**Goal**: Fix detailed_status_code to only classify employees as new_hire_* if they have a current-year hire event

**Independent Test**: Query `fct_workforce_snapshot` for `detailed_status_code = 'new_hire_active'` and verify all have current-year hire dates

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [P] [US2] Create dbt test for new hire status accuracy in dbt/tests/data_quality/test_new_hire_status_accuracy.sql

### Implementation for User Story 2

- [X] T008 [US2] Update detailed_status_code CASE logic for new_hire_active (line ~751) to add hire date year validation in dbt/models/marts/fct_workforce_snapshot.sql
- [X] T009 [US2] Update detailed_status_code CASE logic for new_hire_termination (line ~756) to add hire date year validation in dbt/models/marts/fct_workforce_snapshot.sql

### Validation for User Story 2

- [X] T010 [US2] Run dbt build for fct_workforce_snapshot and verify test passes with `dbt test --select test_new_hire_status_accuracy --vars "simulation_year: 2026"`

**Checkpoint**: Only employees with current-year hire events should have new_hire_* status codes (SC-002)

---

## Phase 5: User Story 3 - New Hire Termination Data Completeness (Priority: P1)

**Goal**: Fix new hire terminations to have populated termination_date and employment_status='terminated'

**Independent Test**: Query `fct_workforce_snapshot` for `detailed_status_code = 'new_hire_termination'` and verify all have termination_date and terminated status

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T011 [P] [US3] Create dbt test for new hire termination data completeness in dbt/tests/data_quality/test_new_hire_termination_completeness.sql

### Implementation for User Story 3

- [X] T012 [US3] Rename termination_type to event_category in output columns (line ~122) in dbt/models/intermediate/events/int_new_hire_termination_events.sql
- [X] T013 [US3] Fix fct_yearly_events.sql to use nht.event_category instead of hardcoded 'termination' (line ~246) in dbt/models/marts/fct_yearly_events.sql

### Validation for User Story 3

- [X] T014 [US3] Run dbt build for full pipeline and verify test passes with `dbt test --select test_new_hire_termination_completeness --vars "simulation_year: 2026"`

**Checkpoint**: All new hire terminations should have complete data (SC-003, SC-004)

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation and documentation

- [ ] T015 [P] Run full simulation for year 2026 and validate all success criteria with `planalign simulate 2026`
- [ ] T016 [P] Run multi-year simulation (2025-2027) to verify year-independence (SC-006) with `planalign simulate 2025-2027`
- [ ] T017 [P] Create property-based pytest tests for distribution validation in tests/test_termination_events.py
- [X] T018 Run quickstart.md validation queries to confirm all fixes working
- [X] T019 Update CLAUDE.md Active Technologies section if needed (no updates required)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Phase 1 macro being complete
  - User stories can then proceed in parallel (all are P1)
  - Or sequentially in priority order (US1 → US2 → US3)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on T001 (macro) - Modifies int_termination_events.sql
- **User Story 2 (P1)**: Depends on T001 (macro) - Modifies fct_workforce_snapshot.sql
- **User Story 3 (P1)**: No dependency on macro - Modifies int_new_hire_termination_events.sql and fct_workforce_snapshot.sql

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Model changes before validation
- Story complete before moving to next priority

### Parallel Opportunities

- T002, T007, T011 (all tests) can run in parallel after Phase 1
- T005 (Polars) can run in parallel with T003, T004 (SQL)
- User Stories 2 and 3 can run in parallel (different focus areas)
- T015, T016, T017 (Polish) can run in parallel

---

## Parallel Example: All Test Creation

```bash
# Launch all test creation tasks together after Phase 1:
Task: "Create dbt test for monthly distribution validation in dbt/tests/data_quality/test_termination_date_distribution.sql"
Task: "Create dbt test for new hire status accuracy in dbt/tests/data_quality/test_new_hire_status_accuracy.sql"
Task: "Create dbt test for new hire termination data completeness in dbt/tests/data_quality/test_new_hire_termination_completeness.sql"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (create macro)
2. Complete Phase 3: User Story 1 (date distribution)
3. **STOP and VALIDATE**: Test termination date distribution independently
4. Deploy/demo if ready - most visible bug is fixed

### Incremental Delivery

1. Complete Setup → Macro ready
2. Add User Story 1 → Test independently → Most impactful fix live
3. Add User Story 2 → Test independently → Status codes accurate
4. Add User Story 3 → Test independently → Data completeness fixed
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Developer completes Phase 1 (macro)
2. Once macro is done:
   - Developer A: User Story 1 (int_termination_events.sql + Polars)
   - Developer B: User Story 2 (fct_workforce_snapshot.sql status logic)
   - Developer C: User Story 3 (int_new_hire_termination_events.sql + snapshot propagation)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (constitution: Test-First Development)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Run dbt with `--threads 1` for work laptop stability (constitution)
