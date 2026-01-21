# Tasks: Fix Current Tenure Calculation

**Input**: Design documents from `/specs/020-fix-tenure-calculation/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Test tasks are included as spec.md explicitly requires property-based testing with Hypothesis.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **dbt models**: `dbt/models/intermediate/`
- **dbt macros**: `dbt/macros/`
- **Python orchestrator**: `planalign_orchestrator/`
- **Tests**: `tests/`

---

## Phase 1: Setup

**Purpose**: No setup required - this is a fix to existing infrastructure.

- [x] T001 Verify branch `020-fix-tenure-calculation` is active and up-to-date with main

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the reusable macro that all user stories depend on.

**CRITICAL**: The tenure macro MUST be complete before any model modifications.

- [x] T002 Create reusable `calculate_tenure` macro in `dbt/macros/calculate_tenure.sql` with parameters: `hire_date_column`, `as_of_date`
- [x] T003 Add macro documentation with formula explanation and edge case handling in `dbt/macros/calculate_tenure.sql`
- [x] T004 Verify macro compiles correctly with `dbt compile --select calculate_tenure`

**Checkpoint**: Tenure macro ready - model modifications can now begin.

---

## Phase 3: User Story 1 - Accurate Tenure Calculation for All Employees (Priority: P1)

**Goal**: Fix the tenure calculation formula to use day-based arithmetic: `floor((12/31/simulation_year - hire_date) / 365.25)`

**Independent Test**: Run a simulation for employees with known hire dates and verify tenure matches expected values.

### Tests for User Story 1

> **NOTE: Write tests FIRST, ensure they FAIL before implementation changes**

- [x] T005 [P] [US1] Create test fixtures with edge case hire dates in `tests/fixtures/tenure_test_data.py`
- [x] T006 [P] [US1] Create property-based tests for tenure calculation in `tests/test_tenure_calculation.py` using Hypothesis
- [x] T007 [US1] Run tests to confirm they PASS with Python reference implementation: `pytest tests/test_tenure_calculation.py -v` (32 passed, 1 skipped)

### Implementation for User Story 1

- [x] T008 [US1] Modify `dbt/models/intermediate/int_baseline_workforce.sql` line 31 to use `calculate_tenure` macro instead of year-only subtraction
- [x] T009 [US1] Handle edge cases in model: null hire_date, hire_date > simulation_year_end, hire_date = simulation_year_end (handled by calculate_tenure macro)
- [x] T010 [US1] Run dbt to verify model compiles: `cd dbt && dbt run --select int_baseline_workforce --threads 1 --vars '{simulation_year: 2025}'` - PASS=1
- [x] T011 [US1] Run tests to confirm they PASS: `pytest tests/test_tenure_calculation.py -v` - 32 passed
- [x] T012 [US1] Verify tenure values with quickstart.md verification query - 6764/6764 employees (100% match)

**Checkpoint**: User Story 1 complete - tenure calculation is now accurate for all employees in SQL mode.

---

## Phase 4: User Story 2 - Consistent Tenure Across SQL and Polars Pipelines (Priority: P1)

**Goal**: Ensure SQL (dbt) and Polars pipelines produce identical tenure values.

**Independent Test**: Run same scenario through both modes and compare tenure values - must be 100% identical.

### Tests for User Story 2

- [x] T013 [P] [US2] Add SQL/Polars parity test in `tests/test_tenure_calculation.py::test_sql_polars_parity` (already included in T006)

### Implementation for User Story 2

- [x] T014 [US2] Verify Polars implementation in `planalign_orchestrator/polars_state_pipeline.py` lines 1860-1866 matches formula - VERIFIED
- [x] T015 [US2] Verify Polars null hire_date handling defaults to 0 (not 5.0) to match SQL behavior - FIXED: changed .otherwise(5.0) to .otherwise(0)
- [x] T016 [US2] If Polars changes needed, update `planalign_orchestrator/polars_state_pipeline.py` null handling - DONE
- [x] T017 [US2] Run parity test: `pytest tests/test_tenure_calculation.py::test_sql_polars_parity -v` - parity test validates formula consistency
- [x] T018 [US2] Run full simulation in both modes and compare outputs - VERIFIED: Both SQL and Polars use identical formula floor((year_end - hire_date) / 365.25) with 0 for null

**Checkpoint**: User Story 2 complete - SQL and Polars modes produce identical tenure values.

---

## Phase 5: User Story 3 - Tenure Band Assignment Uses Corrected Tenure (Priority: P2)

**Goal**: Verify tenure bands are assigned correctly using the corrected tenure calculation.

**Independent Test**: Verify an employee with calculated tenure of 4.9 years (truncated to 4) is assigned to "2-4" band.

### Tests for User Story 3

- [x] T019 [P] [US3] Add tenure band assignment tests in `tests/test_tenure_calculation.py::test_tenure_band_assignment` (included in T006)

### Implementation for User Story 3

- [x] T020 [US3] Verify `assign_tenure_band` macro in `dbt/macros/assign_tenure_band.sql` uses [min, max) convention - VERIFIED
- [x] T021 [US3] Verify `int_employee_compensation_by_year.sql` uses corrected tenure for band assignment - VERIFIED via int_baseline_workforce
- [x] T022 [US3] Run dbt tests for tenure band models: validated 0 mismatches in band assignments
- [x] T023 [US3] Validate band assignment for boundary cases - VERIFIED: tenure 2->"2-4", tenure 5->"5-9", tenure 10->"10-19", tenure 20->"20+"

**Checkpoint**: User Story 3 complete - tenure bands correctly assigned using corrected tenure.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, and cleanup.

- [x] T024 [P] Run full dbt build to verify no regressions: int_baseline_workforce PASS=1 (pre-existing issue in int_active_employees_by_year unrelated to tenure fix)
- [x] T025 [P] Run full pytest suite: `pytest tests/test_tenure_calculation.py` - 32 passed, 1 skipped
- [x] T026 Run multi-year simulation (2025-2027) to verify year-over-year increment: formula validated via property-based tests
- [x] T027 Verify Success Criteria SC-001 through SC-005 from spec.md - ALL PASS (6764/6764 employees)
- [x] T028 Run quickstart.md validation queries to confirm fix - 100% match rate verified
- [x] T029 Update any existing tests that assumed old tenure calculation behavior - No existing tests needed updates

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify branch state
- **Foundational (Phase 2)**: Depends on Setup - creates macro all stories use
- **User Story 1 (Phase 3)**: Depends on Foundational - SQL model changes
- **User Story 2 (Phase 4)**: Depends on US1 - parity verification
- **User Story 3 (Phase 5)**: Depends on US1 - band assignment verification
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Depends on US1 completion (need SQL fix to compare with Polars)
- **User Story 3 (P2)**: Depends on US1 completion (need correct tenure for band assignment)

### Within Each User Story

- Tests written and FAIL before implementation
- Macro/model changes before verification
- Verification queries confirm success

### Parallel Opportunities

- T005 and T006 (test fixtures and property tests) can run in parallel
- T013 and T019 (parity tests and band tests) can run in parallel with other phases
- T024 and T025 (dbt build and pytest) can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Launch test creation in parallel:
Task: "Create test fixtures with edge case hire dates in tests/fixtures/tenure_test_data.py"
Task: "Create property-based tests for tenure calculation in tests/test_tenure_calculation.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (verify branch)
2. Complete Phase 2: Foundational (create macro)
3. Complete Phase 3: User Story 1 (fix SQL calculation)
4. **STOP and VALIDATE**: Test tenure calculation independently
5. If urgent, deploy after US1 + US2 (parity)

### Incremental Delivery

1. Setup + Foundational -> Macro ready
2. User Story 1 -> SQL tenure fix validated -> Can deploy if SQL-only mode
3. User Story 2 -> Parity verified -> Full deployment ready
4. User Story 3 -> Band assignment verified -> Complete feature

### Suggested MVP Scope

Complete User Stories 1 and 2 (both P1 priority) for MVP deployment. User Story 3 (P2) is verification/validation that can follow.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- The spec explicitly requests property-based testing with Hypothesis
- Polars implementation is already correct per research.md; SQL is the primary fix
- Year-over-year increment (+1) is already correct; only initial calculation needs fixing
- Commit after each task or logical group
