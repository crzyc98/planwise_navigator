# Tasks: Remove Duplicate/Versioned dbt Models (v2 Cleanup)

**Input**: Design documents from `/specs/081-remove-duplicate-dbt-models/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: No explicit test tasks — validation is via `dbt build --threads 1 --fail-fast` after each phase.

**Organization**: Tasks are grouped by user story. US1 (remove unused) must complete before US2 (rename v2) can begin, since base models must be deleted before v2 models can take their names.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Pre-Flight Validation)

**Purpose**: Verify the build is green before making any changes

- [x] T001 Verify `dbt build --threads 1 --fail-fast` passes with zero errors in `dbt/`
- [x] T002 Record baseline model count by running `find dbt/models -name "*.sql" | wc -l`

**Checkpoint**: Build is green — safe to begin cleanup

---

## Phase 2: User Story 1 — Remove Unused Model Variants (Priority: P1) MVP

**Goal**: Delete 5 unused/superseded dbt model files and update collateral references so the build remains green.

**Independent Test**: `cd dbt && dbt build --threads 1 --fail-fast` passes with zero errors after all deletions.

### Remove zero-reference models

- [x] T003 [P] [US1] Delete `dbt/models/intermediate/int_enrollment_events_v2.sql` (zero downstream refs)
- [x] T004 [P] [US1] Delete `dbt/models/intermediate/events/int_promotion_events_optimized.sql` (zero downstream refs, explicitly excluded in pipeline)

### Remove model with debug-only reference + update debug model

- [x] T005 [US1] Update `dbt/models/analysis/debug_enrollment_event_counts.sql` — remove the `optimized_event_counts` CTE (lines 43-51) and all references to it in the `validation_summary` CTE (lines 93-94 `optimized_total_events`, `optimized_events_generated`)
- [x] T006 [US1] Delete `dbt/models/intermediate/int_enrollment_events_optimized.sql` after T005

### Remove superseded base models

- [x] T007 [P] [US1] Delete `dbt/models/intermediate/int_deferral_rate_state_accumulator.sql` (base version, zero downstream refs — superseded by v2)
- [x] T008 [P] [US1] Delete `dbt/models/intermediate/int_workforce_previous_year.sql` (base version, superseded by v2 — standalone test at `tests/test_backward_compatibility_legacy_mode.sql` will resolve to renamed v2 after US2)

### Update Python references for removed models

- [x] T009 [US1] Remove `int_promotion_events_optimized` exclusion entry from `planalign_orchestrator/pipeline/event_generation_executor.py` (line 263 area)

### Update schema.yml for removed models

- [x] T010 [US1] Remove model definition entries for deleted models from `dbt/models/intermediate/schema.yml`: remove base `int_deferral_rate_state_accumulator` entry (line 311 area) and base `int_workforce_previous_year` entry (line 1262 area)

### Validate Phase 2

- [ ] T011 [US1] Run `cd dbt && dbt build --threads 1 --fail-fast` — must pass with zero errors (PENDING: requires dbt environment)

**Checkpoint**: 5 unused models removed. Build is green. US2 can now begin.

---

## Phase 3: User Story 2 — Rename Active v2 Models to Drop Suffix (Priority: P2)

**Goal**: Rename 2 active `_v2` models to their canonical names and update all downstream `ref()` calls in SQL and string references in Python.

**Independent Test**: `cd dbt && dbt build --threads 1 --fail-fast` passes with zero errors after all renames and reference updates.

**Depends on**: Phase 2 (US1) complete — base models must be deleted before v2 can take their names.

### Rename `int_deferral_rate_state_accumulator_v2` → `int_deferral_rate_state_accumulator`

- [x] T012 [US2] Rename file `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql` → `dbt/models/intermediate/int_deferral_rate_state_accumulator.sql`
- [x] T013 [P] [US2] Update `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` in `dbt/models/marts/fct_workforce_snapshot.sql`
- [x] T014 [P] [US2] Update `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` in `dbt/models/intermediate/int_deferral_escalation_state_accumulator.sql`
- [x] T015 [P] [US2] Update `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` in `dbt/models/marts/reporting/rpt_deferral_rate_regulatory_audit_summary.sql` (2 occurrences)
- [x] T016 [P] [US2] Update `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` in `dbt/models/marts/data_quality/dq_deferral_rate_state_audit_validation_v2.sql`
- [x] T017 [P] [US2] Update `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` in `dbt/models/marts/data_quality/dq_deferral_rate_state_audit_validation.sql`
- [x] T018 [P] [US2] Update `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` in `dbt/models/intermediate/events/int_employee_contributions.sql`
- [x] T019 [P] [US2] Update `ref('int_deferral_rate_state_accumulator_v2')` → `ref('int_deferral_rate_state_accumulator')` in `dbt/models/analysis/debug_participation_pipeline.sql`

### Rename `int_workforce_previous_year_v2` → `int_workforce_previous_year`

- [x] T020 [US2] Rename file `dbt/models/intermediate/int_workforce_previous_year_v2.sql` → `dbt/models/intermediate/int_workforce_previous_year.sql`
- [x] T021 [US2] Update `ref('int_workforce_previous_year_v2')` → `ref('int_workforce_previous_year')` in `dbt/models/intermediate/int_year_snapshot_preparation.sql`

### Update Python string references

- [x] T022 [P] [US2] Update `"int_deferral_rate_state_accumulator_v2"` → `"int_deferral_rate_state_accumulator"` in `planalign_orchestrator/state_accumulator/__init__.py`
- [x] T023 [P] [US2] Update `"int_deferral_rate_state_accumulator_v2"` and `"int_workforce_previous_year_v2"` → drop `_v2` suffix in `planalign_orchestrator/model_execution_types.py`
- [x] T024 [P] [US2] Update `"int_deferral_rate_state_accumulator_v2"` → `"int_deferral_rate_state_accumulator"` in `planalign_orchestrator/pipeline/workflow.py`
- [x] T025 [P] [US2] Update `"int_deferral_rate_state_accumulator_v2"` → `"int_deferral_rate_state_accumulator"` in `planalign_orchestrator/init_database.py`
- [x] T026 [P] [US2] Update `"int_deferral_rate_state_accumulator_v2"` → `"int_deferral_rate_state_accumulator"` in `planalign_api/services/simulation/db_cleanup.py`

### Update schema.yml for renamed models

- [x] T027 [US2] Update model entries in `dbt/models/intermediate/schema.yml` — rename `int_deferral_rate_state_accumulator_v2` entry to `int_deferral_rate_state_accumulator`; rename `int_workforce_previous_year_v2` entry to `int_workforce_previous_year` (if present)

### Validate Phase 3

- [ ] T028 [US2] Run `cd dbt && dbt build --threads 1 --fail-fast` — must pass with zero errors (PENDING: requires dbt environment)

**Checkpoint**: All `_v2` suffixes removed from active models. Build is green.

---

## Phase 4: User Story 3 — Verify Simulation Output Consistency (Priority: P3)

**Goal**: Confirm the cleanup produces identical simulation results.

**Independent Test**: Run a single-year simulation and compare `fct_yearly_events` and `fct_workforce_snapshot` row counts and checksums against baseline.

**Depends on**: Phase 3 (US2) complete.

- [ ] T029 [US3] Run `planalign simulate 2025` and record row counts + checksums for `fct_yearly_events` and `fct_workforce_snapshot` via DuckDB queries
- [ ] T030 [US3] Verify row counts and data match expected baseline (same seed, same config = identical output)

**Checkpoint**: Simulation output verified identical — cleanup is complete.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final sweep

- [x] T031 [P] Update `dbt/CLAUDE.md` stage 4 reference from `int_deferral_rate_state_accumulator_v2` to `int_deferral_rate_state_accumulator`
- [x] T032 [P] Run `grep -r "_v2\|_optimized" dbt/models/ --include="*.sql" -l` and verify only `int_workforce_snapshot_optimized` and `dq_deferral_rate_state_audit_validation_v2` remain (both out of scope)
- [x] T033 Run `grep -r "int_deferral_rate_state_accumulator_v2\|int_workforce_previous_year_v2\|int_enrollment_events_v2\|int_enrollment_events_optimized\|int_promotion_events_optimized" planalign_orchestrator/ planalign_api/ planalign_cli/ --include="*.py"` and verify zero matches
- [x] T034 Verify model count reduced by at least 5 vs baseline recorded in T002

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 2)**: Depends on Phase 1 — remove unused models first
- **US2 (Phase 3)**: Depends on Phase 2 — base models must be gone before v2 takes their name
- **US3 (Phase 4)**: Depends on Phase 3 — run simulation after all changes
- **Polish (Phase 5)**: Depends on Phase 3 — can run in parallel with Phase 4

### Within Each Phase

- Tasks marked [P] within a phase can run in parallel
- Non-[P] tasks must run sequentially in order

### Parallel Opportunities

**Phase 2 (US1)**:
- T003, T004 can run in parallel (independent file deletions)
- T007, T008 can run in parallel (independent file deletions)
- T005 must precede T006 (update debug model before deleting referenced model)

**Phase 3 (US2)**:
- T013-T019 can all run in parallel (different SQL files, same find-replace pattern)
- T022-T026 can all run in parallel (different Python files, same string replacement)
- T012 and T020 (file renames) should precede their respective ref() updates

---

## Parallel Example: Phase 3 (US2) ref() Updates

```bash
# After T012 (file rename), launch all SQL ref() updates together:
Task: "Update ref() in dbt/models/marts/fct_workforce_snapshot.sql"
Task: "Update ref() in dbt/models/intermediate/int_deferral_escalation_state_accumulator.sql"
Task: "Update ref() in dbt/models/marts/reporting/rpt_deferral_rate_regulatory_audit_summary.sql"
Task: "Update ref() in dbt/models/marts/data_quality/dq_deferral_rate_state_audit_validation_v2.sql"
Task: "Update ref() in dbt/models/marts/data_quality/dq_deferral_rate_state_audit_validation.sql"
Task: "Update ref() in dbt/models/intermediate/events/int_employee_contributions.sql"
Task: "Update ref() in dbt/models/analysis/debug_participation_pipeline.sql"

# Launch all Python string updates together:
Task: "Update string refs in planalign_orchestrator/state_accumulator/__init__.py"
Task: "Update string refs in planalign_orchestrator/model_execution_types.py"
Task: "Update string refs in planalign_orchestrator/pipeline/workflow.py"
Task: "Update string refs in planalign_orchestrator/init_database.py"
Task: "Update string refs in planalign_api/services/simulation/db_cleanup.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (pre-flight validation)
2. Complete Phase 2: US1 — Remove 5 unused models
3. **STOP and VALIDATE**: `dbt build --threads 1 --fail-fast`
4. This alone delivers SC-001 (5 fewer models) and eliminates developer confusion

### Incremental Delivery

1. Phase 1 → Pre-flight green
2. Phase 2 (US1) → 5 models removed → Build green (MVP!)
3. Phase 3 (US2) → v2 suffixes dropped → Naming consistency achieved
4. Phase 4 (US3) → Output equivalence confirmed → Full confidence
5. Phase 5 → Docs updated, final sweep

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- US1 MUST complete before US2 (name collision avoidance)
- US3 is a validation-only phase — no code changes
- `int_workforce_snapshot_optimized` and `dq_deferral_rate_state_audit_validation_v2` are explicitly OUT OF SCOPE
- The standalone test `tests/test_backward_compatibility_legacy_mode.sql` references `int_workforce_previous_year` — after US2 renames the v2 to that name, this test resolves naturally with no changes needed
