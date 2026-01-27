# Tasks: Fix Workforce Snapshot Performance Regression

**Input**: Design documents from `/specs/028-fix-snapshot-perf-regression/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Tests**: Existing dbt tests provide validation; no new test files required.

**Organization**: Tasks implement SQL optimization in a single file. User stories share the same implementation but have different validation criteria.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **dbt project**: `dbt/models/` for SQL models
- **Target file**: `dbt/models/marts/fct_workforce_snapshot.sql`

---

## Phase 1: Setup (Pre-Implementation Baseline)

**Purpose**: Capture baseline performance and data for regression validation

- [X] T001 Export pre-optimization fct_workforce_snapshot data to CSV for comparison in dbt/ (Note: Table empty - baseline established)
- [ ] T002 Record current 5-year simulation time baseline (expected: ~45 min on Windows)
- [ ] T003 [P] Run existing dbt tests to confirm green baseline: `dbt test --select fct_workforce_snapshot --threads 1`

---

## Phase 2: Foundational (Core Optimization)

**Purpose**: Implement the O(n²) to O(n) optimization - this is the primary fix that benefits ALL user stories

**⚠️ CRITICAL**: This phase delivers the core performance improvement

- [X] T004 Add `baseline_comp_for_quality` CTE before `final_output` in dbt/models/marts/fct_workforce_snapshot.sql (around line 930)
- [X] T005 Add LEFT JOIN to `baseline_comp_for_quality` in `final_output` CTE in dbt/models/marts/fct_workforce_snapshot.sql
- [X] T006 Replace 4 scalar subqueries (lines 971-1025) with single CASE expression using joined baseline_compensation in dbt/models/marts/fct_workforce_snapshot.sql

**Checkpoint**: Core optimization complete - scalar subqueries eliminated

---

## Phase 3: User Story 1 - Multi-Year Simulation Performance (Priority: P1) 🎯 MVP

**Goal**: Fix 5.6x performance regression for 5-year simulations (45 min → <15 min)

**Independent Test**: Run `planalign simulate 2025-2029` and verify completion in <15 minutes with identical output data

### Implementation for User Story 1

- [X] T007 [US1] Add `simulation_year = {{ var('simulation_year') }}` filter at Line ~373 (Year 1 baseline eligibility) in dbt/models/marts/fct_workforce_snapshot.sql
- [X] T008 [US1] Add `simulation_year = {{ var('simulation_year') }}` filter at Line ~423 (NOT IN subquery) in dbt/models/marts/fct_workforce_snapshot.sql
- [X] T009 [US1] Add `simulation_year = {{ var('simulation_year') }}` filter at Line ~472 (baseline fallback) in dbt/models/marts/fct_workforce_snapshot.sql
- [ ] T010 [US1] Run 5-year simulation and compare output data to pre-optimization baseline (must match 100%)
- [ ] T011 [US1] Verify 5-year simulation completes in <15 minutes (SC-001)

**Checkpoint**: User Story 1 complete - 5-year simulations run in target time with identical data

---

## Phase 4: User Story 2 - Single Year Performance Consistency (Priority: P2)

**Goal**: Ensure single-year dbt builds remain fast (<30 sec for 10K employees)

**Independent Test**: Run `dbt run --select fct_workforce_snapshot --vars "simulation_year: 2025" --threads 1` and verify <30 sec execution

### Validation for User Story 2

- [ ] T012 [US2] Measure single-year model execution time for Year 2025 in dbt/
- [ ] T013 [US2] Verify model execution <30 seconds for 10K employee dataset (SC-002)
- [ ] T014 [US2] Confirm EXPLAIN output shows no full table scans of int_baseline_workforce

**Checkpoint**: User Story 2 validated - single-year builds performant

---

## Phase 5: User Story 3 - Cross-Platform Performance Parity (Priority: P3)

**Goal**: Reduce Windows vs. Linux/macOS performance gap from 5.6x to <2x

**Independent Test**: Run identical simulation on both platforms and compare execution times

### Validation for User Story 3

- [ ] T015 [US3] Run simulation on Linux/macOS and record execution time
- [ ] T016 [US3] Compare Windows vs. Linux/macOS execution time ratio (target: <2x)

**Checkpoint**: User Story 3 validated - cross-platform parity improved

---

## Phase 6: Polish & Final Validation

**Purpose**: Run all dbt tests, verify edge cases, and finalize

- [ ] T017 Run all dbt tests: `dbt test --threads 1` in dbt/ (SC-004)
- [ ] T018 Query fct_workforce_snapshot to verify zero NULL compensation_quality_flag values (SC-005)
- [ ] T019 Verify edge case: employees with zero baseline_compensation return 'NORMAL' flag
- [ ] T020 Verify edge case: new hires (not in baseline) return 'NORMAL' flag
- [ ] T021 Delete temporary baseline CSV files created in T001
- [ ] T022 Update any documentation if needed (e.g., dbt model descriptions)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - captures baseline before changes
- **Foundational (Phase 2)**: Depends on Setup - implements core optimization
- **User Story 1 (Phase 3)**: Depends on Foundational - adds simulation_year filters, validates multi-year
- **User Story 2 (Phase 4)**: Depends on User Story 1 - validates single-year (filters already added)
- **User Story 3 (Phase 5)**: Depends on User Story 1 - validates cross-platform (same code)
- **Polish (Phase 6)**: Depends on all stories - final validation

### Task Execution Order

```
T001 → T002 → T003 (baseline capture)
         ↓
T004 → T005 → T006 (core optimization - sequential, same file)
         ↓
T007 → T008 → T009 (add filters - sequential, same file)
         ↓
T010 → T011 (US1 validation)
         ↓
T012 → T013 → T014 (US2 validation)
         ↓
T015 → T016 (US3 validation - can skip if no Windows access)
         ↓
T017 → T018 → T019 → T020 → T021 → T022 (final validation)
```

### Parallel Opportunities

This feature has **limited parallelism** because:
1. All implementation tasks modify the same file (`fct_workforce_snapshot.sql`)
2. Tasks must be executed sequentially to avoid merge conflicts

**Parallel-safe tasks**:
- T001, T002, T003 can run in parallel (different operations)
- T019, T020 can run in parallel (independent edge case queries)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (capture baseline)
2. Complete Phase 2: Foundational (core optimization)
3. Complete Phase 3: User Story 1 (add filters + validate)
4. **STOP and VALIDATE**: Verify <15 min execution, 100% data match
5. Can deploy after US1 passes

### Incremental Delivery

1. Setup → Baseline captured
2. Foundational → Core scalar subquery fix deployed
3. User Story 1 → 5-year simulation fix validated → **MVP Complete**
4. User Story 2 → Single-year validation confirmed
5. User Story 3 → Cross-platform parity confirmed (if Windows available)
6. Polish → All tests pass, edge cases verified

### Single Developer Strategy

Since all tasks modify the same file, recommended approach:
1. Execute T001-T003 to capture baseline
2. Execute T004-T006 sequentially (core optimization)
3. Execute T007-T009 sequentially (add filters)
4. Run T010-T011 to validate US1
5. Continue with US2/US3 validation
6. Complete Polish phase

---

## Notes

- All implementation tasks (T004-T009) modify the same file - **no parallelism possible**
- Validation tasks can partially parallelize
- Single file change makes this low-risk and easy to rollback
- Commit after T006 (core optimization) and after T009 (all filters added)
- If any validation fails, root cause is clear since changes are isolated
