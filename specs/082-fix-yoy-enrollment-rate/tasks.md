# Tasks: Fix Year-over-Year Voluntary Enrollment Rate Override

**Input**: Design documents from `/specs/082-fix-yoy-enrollment-rate/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Test tasks are included — the constitution requires test-first development (Principle III).

**Organization**: Tasks are grouped by user story. US1 and US2 share the same SQL fix (the multiplier works across the full 0–100% range), so they are combined into a single phase. US3 is a verification-only story (no additional code changes).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Understand the current state of the bug location before making changes

- [x] T001 Read and annotate the year-over-year CTE in `dbt/models/intermediate/int_enrollment_events.sql` (lines 508-603) to identify both locations where `event_probability` is calculated without the `voluntary_enrollment_rate` multiplier
- [x] T002 [P] Read `dbt/models/intermediate/int_voluntary_enrollment_decision.sql` (line 159) to confirm the existing multiplier pattern: `COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)`
- [x] T003 [P] Read `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` (line 218) to confirm the same multiplier pattern is used identically

**Checkpoint**: Both reference patterns confirmed; exact insertion points in year-over-year CTE identified

---

## Phase 2: User Story 1 & 2 - Suppress and Scale Voluntary Enrollment (Priority: P1)

**Goal**: Apply `voluntary_enrollment_rate` as a multiplier to the year-over-year conversion probability, so 0% produces zero events and intermediate values scale proportionally

**Independent Test**: Run `dbt run` with `voluntary_enrollment_rate: 0.0` and verify zero year-over-year enrollment events; run with `voluntary_enrollment_rate: 0.5` and verify approximately half the events compared to 1.0

### Test (write first, verify it fails)

- [x] T004 [US1] Create dbt test `dbt/tests/test_yoy_respects_voluntary_rate.sql` that asserts zero year-over-year enrollment events are generated when `voluntary_enrollment_rate` is set to 0.0 — test should query `{{ ref('int_enrollment_events') }}` filtering for `enrollment_source = 'year_over_year_conversion'` and assert `COUNT(*) = 0` when the variable is 0

### Implementation

- [x] T005 [US1] In `dbt/models/intermediate/int_enrollment_events.sql`, add `* COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)` to the `event_probability` calculation in the `year_over_year_enrollment_events` CTE (around line 569, after the tenure multiplier CASE expression)
- [x] T006 [US2] In `dbt/models/intermediate/int_enrollment_events.sql`, verify the same multiplier is applied in the WHERE clause hash-based selection (around lines 584-602) if the probability is recalculated there rather than referencing the column — ensure both locations use the multiplied probability

### Validation

- [x] T007 [US1] Run `cd dbt && dbt run --select int_enrollment_events --vars "{simulation_year: 2025, voluntary_enrollment_rate: 0.0}" --threads 1` and verify zero year-over-year conversion events
- [x] T008 [US2] Run `cd dbt && dbt run --select int_enrollment_events --vars "{simulation_year: 2025, voluntary_enrollment_rate: 1.0}" --threads 1` and verify year-over-year conversion events match current production behavior (regression check)
- [x] T009 [US1] Run `cd dbt && dbt test --select test_yoy_respects_voluntary_rate --vars "{simulation_year: 2025, voluntary_enrollment_rate: 0.0}" --threads 1` and verify the new test passes

**Checkpoint**: Year-over-year CTE respects `voluntary_enrollment_rate` at 0%, 50%, and 100% — US1 and US2 are both satisfied

---

## Phase 3: User Story 3 - Unified Sensitivity Dial (Priority: P2)

**Goal**: Confirm that the single `voluntary_enrollment_rate` slider controls all three pathways uniformly with no additional configuration needed

**Independent Test**: Run the existing enrollment architecture test suite and verify all tests pass with no modifications

### Validation

- [x] T010 [US3] Run `cd dbt && dbt test --select test_enrollment_architecture --vars "simulation_year: 2025" --threads 1` and verify all enrollment architecture tests pass
- [x] T011 [US3] Run `cd dbt && dbt build --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment int_enrollment_events --vars "{simulation_year: 2025, voluntary_enrollment_rate: 0.0}" --threads 1` and verify all three models produce zero voluntary enrollment events

**Checkpoint**: All three pathways respond uniformly to the voluntary enrollment rate — US3 is satisfied

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across the full enrollment pipeline

- [x] T012 Run full enrollment pipeline: `cd dbt && dbt build --select +int_enrollment_events+ --vars "simulation_year: 2025" --threads 1 --fail-fast` and verify no failures
- [x] T013 Run all existing enrollment-related dbt tests: `cd dbt && dbt test --select test_enrollment_architecture test_auto_enrollment_enabled_generates_events assert_enrollment_after_hire_date --vars "simulation_year: 2025" --threads 1` and verify all pass (SC-004: backward compatibility)
- [x] T014 Run quickstart validation per `specs/082-fix-yoy-enrollment-rate/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — read-only exploration
- **US1 & US2 (Phase 2)**: Depends on Phase 1 completion
- **US3 (Phase 3)**: Depends on Phase 2 completion (same SQL fix enables this)
- **Polish (Phase 4)**: Depends on Phase 3 completion

### User Story Dependencies

- **US1 (P1)**: Core fix — add multiplier to year-over-year CTE
- **US2 (P1)**: Same fix as US1 — proportional scaling is automatic when the multiplier is applied
- **US3 (P2)**: No additional code — verified by running all three pathways with the same rate

### Within Phase 2

- T004 (test) MUST be written before T005/T006 (implementation)
- T005 and T006 operate on the same file sequentially
- T007, T008, T009 (validation) depend on T005/T006 completion

### Parallel Opportunities

- T002 and T003 can run in parallel (different files, read-only)
- T007, T008, T009 can run in parallel (independent dbt runs with different vars)
- T010 and T011 can run in parallel (independent dbt test runs)

---

## Parallel Example: Phase 1

```bash
# Read reference patterns in parallel:
Task: "Read int_voluntary_enrollment_decision.sql line 159 for multiplier pattern"
Task: "Read int_proactive_voluntary_enrollment.sql line 218 for multiplier pattern"
```

## Parallel Example: Phase 2 Validation

```bash
# Run validation commands in parallel:
Task: "dbt run with voluntary_enrollment_rate: 0.0 — verify zero events"
Task: "dbt run with voluntary_enrollment_rate: 1.0 — verify regression-free"
Task: "dbt test test_yoy_respects_voluntary_rate — verify new test passes"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Read and understand current code
2. Complete T004: Write failing test
3. Complete T005-T006: Apply the fix
4. Complete T007: Verify 0% produces zero events
5. **STOP and VALIDATE**: The core bug is fixed

### Full Delivery

1. Complete Phase 1 → Phase 2 → Phase 3 → Phase 4
2. Each phase adds confidence without changing additional code
3. Phase 3 and 4 are validation-only — no new code changes

---

## Notes

- This is a **targeted bug fix** — the total code change is ~1 line of SQL
- The test (T004) and fix (T005-T006) are the only tasks that modify files
- T007-T014 are validation/verification tasks that run existing infrastructure
- No Python, config, or UI changes are needed
- The `voluntary_enrollment_rate` variable already flows through the entire config pipeline
