# Tasks: Fix Mid-Year Termination Tenure Calculation

**Input**: Design documents from `/specs/023-fix-midyear-tenure/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included per Constitution Principle III (Test-First Development) and plan.md requirements.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **dbt models**: `dbt/models/` (from project root)
- **dbt tests**: `dbt/tests/` (from project root)
- **Python orchestrator**: `planalign_orchestrator/` (from project root)
- **Python tests**: `tests/` (from project root)

---

## Phase 1: Setup (Verification & Baseline)

**Purpose**: Verify the bug exists and establish a baseline before fixing

- [ ] T001 Verify the bug by running quickstart.md "Verify the Bug" steps and documenting current mismatch count
- [ ] T002 Review existing `calculate_tenure` macro in dbt/macros/calculate_tenure.sql to confirm it handles edge cases correctly
- [ ] T003 Review existing `assign_tenure_band` macro in dbt/macros/bands/assign_tenure_band.sql to confirm band boundaries

---

## Phase 2: Foundational (Test Infrastructure)

**Purpose**: Create test infrastructure that MUST be complete before implementation

**⚠️ CRITICAL**: Tests must FAIL before implementation (Red phase of Red-Green-Refactor)

- [ ] T004 [P] Create dbt test for tenure/band consistency in dbt/tests/generic/test_tenure_band_consistency.sql
- [ ] T005 [P] Create pytest fixture for terminated employee test data in tests/fixtures/workforce_data.py
- [ ] T006 Create pytest test cases for mid-year termination tenure in tests/test_tenure_calculation.py
- [ ] T007 Run T004-T006 tests and confirm they FAIL (Red phase) - document failures

**Checkpoint**: Test infrastructure ready - tests fail as expected, proving the bug exists

---

## Phase 3: User Story 1 - Accurate Tenure for Mid-Year Terminated Employees (Priority: P1) 🎯 MVP

**Goal**: Fix `current_tenure` calculation for terminated employees so it uses `floor((termination_date - hire_date) / 365.25)` and ensure `tenure_band` is derived from the corrected value.

**Independent Test**: Query `fct_workforce_snapshot` for terminated employees and verify `current_tenure` matches expected formula and `tenure_band` matches `current_tenure`.

### Implementation for User Story 1

- [ ] T008 [US1] Refactor `final_workforce` CTE in dbt/models/marts/fct_workforce_snapshot.sql to use subquery pattern for tenure calculation (lines 668-760)
- [ ] T009 [US1] Update tenure_band calculation in dbt/models/marts/fct_workforce_snapshot.sql to derive from recalculated tenure (move to outer SELECT)
- [ ] T010 [US1] Update `new_hires` CTE in dbt/models/marts/fct_workforce_snapshot.sql (line 208) to calculate tenure using `calculate_tenure` macro instead of hardcoded 0
- [ ] T011 [US1] Run dbt build for Year 2026 to verify SQL pipeline fix: `cd dbt && dbt build --threads 1 --vars "simulation_year: 2026" --fail-fast`
- [ ] T012 [US1] Run dbt test T004 (tenure_band_consistency) and confirm it PASSES (Green phase)
- [ ] T013 [US1] Run quickstart.md "Verify No Mismatches Remain" query and confirm 0 mismatches

**Checkpoint**: User Story 1 complete - SQL pipeline produces correct tenure for terminated employees

---

## Phase 4: User Story 2 - Tenure Consistency Between SQL and Polars Modes (Priority: P2)

**Goal**: Ensure Polars state pipeline produces identical `current_tenure` and `tenure_band` values as the SQL pipeline for all terminated employees.

**Independent Test**: Run same simulation in both SQL and Polars modes, compare tenure values for terminated employees.

### Implementation for User Story 2

- [ ] T014 [US2] Verify tenure calculation order in planalign_orchestrator/polars_state_pipeline.py SnapshotBuilder.build() method (lines 1862-1949)
- [ ] T015 [US2] Verify TENURE_BANDS constant in polars_state_pipeline.py matches SQL macro definitions in dbt/macros/bands/assign_tenure_band.sql
- [ ] T016 [US2] Add explicit test for edge cases in planalign_orchestrator/polars_state_pipeline.py: same-day hire/termination, NULL dates, hire > termination
- [ ] T017 [US2] Create SQL/Polars parity test in tests/test_tenure_calculation.py comparing tenure output between modes
- [ ] T018 [US2] Run parity test from quickstart.md and confirm 0 tenure mismatches and 0 band mismatches between modes
- [ ] T019 [US2] Run full test suite `pytest -m fast -v` and confirm all tests pass

**Checkpoint**: User Story 2 complete - SQL and Polars pipelines produce identical tenure values

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, and cleanup

- [ ] T020 Run full 2-year simulation `planalign simulate 2025-2026 --clean` and verify no errors
- [ ] T021 Run all dbt tests `cd dbt && dbt test --threads 1` and confirm all pass
- [ ] T022 Run all pytest tests `pytest -v` and confirm all pass
- [ ] T023 Update specs/023-fix-midyear-tenure/spec.md status from "Draft" to "Complete"
- [ ] T024 Review and clean up any debug logging or temporary code added during implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS implementation phases
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion
- **User Story 2 (Phase 4)**: Can start after Foundational phase; independent of US1 but recommended to do US1 first
- **Polish (Phase 5)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - SQL pipeline fix
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Polars pipeline verification
  - Note: US2 may benefit from US1 being complete to have a "correct" SQL baseline for comparison

### Within Each User Story

- Tests must be written and FAIL before implementation (Red-Green-Refactor)
- Implementation tasks are sequential within the story
- Story complete when all tests pass

### Parallel Opportunities

- T002 and T003 can run in parallel (both are review tasks)
- T004 and T005 can run in parallel (different files)
- US1 and US2 can run in parallel after Phase 2 (different pipelines)

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch these in parallel (different files):
Task T004: "Create dbt test for tenure/band consistency in dbt/tests/generic/test_tenure_band_consistency.sql"
Task T005: "Create pytest fixture for terminated employee test data in tests/fixtures/workforce_data.py"

# Then sequential:
Task T006: "Create pytest test cases" (depends on T005 fixture)
Task T007: "Run and verify tests FAIL" (depends on T004, T006)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (verify bug exists)
2. Complete Phase 2: Foundational (create failing tests)
3. Complete Phase 3: User Story 1 (fix SQL pipeline)
4. **STOP and VALIDATE**: Run quickstart.md verification queries
5. Deploy/demo if tenure is correct for terminated employees

### Incremental Delivery

1. Setup + Foundational → Test infrastructure ready
2. Add User Story 1 → SQL pipeline fixed → Validate with dbt tests
3. Add User Story 2 → Polars parity confirmed → Validate with parity tests
4. Polish → Full test suite passes → Ready for merge

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (Constitution Principle III)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- This is a bug fix - no new schema changes, minimal code changes
