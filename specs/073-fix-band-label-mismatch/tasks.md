# Tasks: Fix Hardcoded Age/Tenure Band Label Mismatches

**Input**: Design documents from `/specs/073-fix-band-label-mismatch/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: No separate test tasks — this bug fix includes test fixes (schema.yml) and a new consistency test as implementation tasks.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- All paths relative to repository root
- dbt models: `dbt/models/intermediate/`, `dbt/models/dimensions/`, `dbt/models/marts/`
- dbt macros: `dbt/macros/events/`
- dbt tests: `dbt/tests/data_quality/`
- dbt schema: `dbt/models/intermediate/schema.yml`

---

## Phase 1: Setup (Verification)

**Purpose**: Confirm macros work as expected before modifying models

- [x] T001 Verify `assign_age_band` macro compiles with expression argument by running `dbt compile --select int_employee_compensation_by_year` from `dbt/` directory — inspect compiled SQL to confirm `{{ assign_age_band('current_age + 1') }}` generates valid CASE expression
- [x] T002 Verify `assign_tenure_band` macro compiles with expression argument by running `dbt compile --select int_employee_compensation_by_year` from `dbt/` directory — inspect compiled SQL to confirm `{{ assign_tenure_band('current_tenure + 1') }}` generates valid CASE expression

---

## Phase 2: User Story 1 - Salary Growth Produces Correct Results (Priority: P1) 🎯 MVP

**Goal**: Fix 5 critically mismatched models so band labels match seed-defined values, restoring merit raise and enrollment event generation.

**Independent Test**: Run `dbt build --threads 1 --fail-fast` then query `fct_yearly_events` to verify non-zero RAISE events exist for year 2025.

### Implementation for User Story 1

- [x] T003 [P] [US1] Replace hardcoded age/tenure band CASE statements with `{{ assign_age_band('current_age') }}` and `{{ assign_tenure_band('current_tenure') }}` macro calls in `dbt/models/intermediate/int_active_employees_by_year.sql` (lines ~39-55). Remove the entire CASE block for both age_band and tenure_band and replace each with the single macro call.
- [x] T004 [P] [US1] Replace hardcoded age/tenure band CASE statements with `{{ assign_age_band('current_age + 1') }}` and `{{ assign_tenure_band('current_tenure + 1') }}` macro calls in `dbt/models/intermediate/int_active_employees_prev_year_snapshot.sql` (lines ~72-89). This model increments age/tenure by 1 for next-year projection.
- [x] T005 [P] [US1] Fix tenure band labels in `dbt/models/dimensions/dim_enrollment_hazards.sql` (lines ~58-101) — replace wrong string literals (`'0-1'`, `'1-3'`, `'3-5'`) with seed-aligned labels (`'< 2'`, `'2-4'`, `'5-9'`, `'10-19'`, `'20+'`). This is a lookup table so macro calls may not apply; correct the string constants directly and ensure boundary logic aligns with seed `[min, max)` convention.
- [x] T006 [P] [US1] Fix voluntary enrollment band assignments in `dbt/models/intermediate/events/int_enrollment_events_v2.sql` (lines ~377-388) — replace wrong age bands (`'< 30'`, `'30-39'`, `'40-49'`, `'50+'`) and month-based tenure bands (`'< 2 years'`, `'2-5 years'`, etc.) with `{{ assign_age_band('ved.current_age') }}` and `{{ assign_tenure_band('ved.current_tenure') }}` macro calls. If `current_tenure` is in months in this CTE, convert to years first: `{{ assign_tenure_band('ved.current_tenure / 12.0') }}`.
- [x] T007 [P] [US1] Fix tenure band split in `dbt/macros/events/events_enrollment_sql.sql` (lines ~93-100) — replace hardcoded CASE that splits `10-19` into `'10-14'` and `'15-19'` with `{{ assign_tenure_band('se.current_tenure') }}` macro call. Also replace the age band CASE (lines ~84-91) with `{{ assign_age_band('se.current_age') }}`.
- [x] T008 [US1] Validate Phase 1 critical fixes by running `dbt build --threads 1 --fail-fast` from `dbt/` directory. Verify compilation succeeds and no model errors occur.

**Checkpoint**: The 5 critically mismatched models now produce seed-aligned band labels. Merit raise and enrollment events should be generated correctly.

---

## Phase 3: User Story 2 - Band Labels Stay Consistent When Users Customize Bands (Priority: P2)

**Goal**: Replace 14 hardcoded-but-currently-correct CASE blocks with centralized macro calls so band customization works end-to-end.

**Independent Test**: After changes, modify `config_age_bands.csv` to use different boundaries, run `dbt build`, and verify all models produce the new labels consistently.

### Implementation for User Story 2

**Batch A — Intermediate models (no events/ subdirectory)**:

- [x] T009 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/int_employee_compensation_by_year.sql` (lines ~110-124) with `{{ assign_age_band('current_age + 1') }}` and `{{ assign_tenure_band('current_tenure + 1') }}`.
- [x] T010 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/int_workforce_previous_year.sql` (lines ~50-65) with `{{ assign_age_band('current_age + 1') }}` and `{{ assign_tenure_band('current_tenure + 1') }}`.
- [x] T011 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/int_workforce_previous_year_v2.sql` (lines ~104-118) with appropriate macro calls — check column names and whether `+1` is used.
- [x] T012 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/int_workforce_snapshot_optimized.sql` (lines ~394-407) with appropriate macro calls — check column names.
- [x] T013 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/int_new_hire_compensation_staging.sql` (lines ~155-160) with appropriate macro calls — check column names (may use `he.employee_age` or similar).

**Batch B — Event models (events/ subdirectory)**:

- [x] T014 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_enrollment_events.sql` (lines ~41-53, ~485-500, ~593-598) with appropriate macro calls. Note: this file has 3 separate CASE blocks — replace all of them.
- [x] T015 [P] [US2] Replace remaining hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_enrollment_events_v2.sql` (lines ~71-76, ~108-113) with appropriate macro calls. Note: the critical fix (lines 377-388) was done in T006; these are the fragile-but-correct sections.
- [x] T016 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_hiring_events.sql` (lines ~154-161) with appropriate macro calls.
- [x] T017 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_new_hire_termination_events.sql` (lines ~147-152) with appropriate macro calls.
- [x] T018 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_promotion_events_optimized.sql` (lines ~71-84) with appropriate macro calls.
- [x] T019 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_proactive_voluntary_enrollment.sql` (lines ~331-346) with appropriate macro calls.
- [x] T020 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql` (lines ~256-269) with appropriate macro calls.
- [x] T021 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/intermediate/events/int_deferral_match_response_events.sql` (lines ~308-321) with appropriate macro calls.

**Batch C — Marts**:

- [x] T022 [P] [US2] Replace hardcoded age/tenure CASE in `dbt/models/marts/fct_workforce_snapshot.sql` (lines ~751-764) with appropriate macro calls.

- [x] T023 [US2] Validate all 14 fragile model fixes by running `dbt build --threads 1 --fail-fast` from `dbt/` directory. Verify compilation succeeds and no model errors occur.

**Checkpoint**: All 19 models now use centralized band assignment. Band customization via seed CSV changes will propagate to all models.

---

## Phase 4: User Story 3 - Schema Validation Tests Match Seed-Defined Labels (Priority: P3)

**Goal**: Fix `schema.yml` accepted_values tests so they validate against seed-defined labels.

**Independent Test**: Run `dbt test --select int_active_employees_by_year int_active_employees_prev_year_snapshot --threads 1` and verify tests pass.

### Implementation for User Story 3

- [x] T024 [US3] Update accepted_values for `age_band` and `tenure_band` on `int_active_employees_prev_year_snapshot` in `dbt/models/intermediate/schema.yml` (lines ~1564-1575) — change age values from `['Under 25', '25-34', ...]` to `['< 25', '25-34', '35-44', '45-54', '55-64', '65+']` and tenure values from `['Less than 1 year', '1-2 years', ...]` to `['< 2', '2-4', '5-9', '10-19', '20+']`.
- [x] T025 [US3] Update accepted_values for `age_band` and `tenure_band` on `int_active_employees_by_year` in `dbt/models/intermediate/schema.yml` (lines ~1661-1672) — same corrections as T024.
- [x] T026 [US3] Validate schema test fixes by running `dbt test --threads 1` from `dbt/` directory. Verify all accepted_values tests pass.

**Checkpoint**: Schema validation tests now catch real band label mismatches rather than codifying wrong labels.

---

## Phase 5: User Story 4 - Cross-Model Band Consistency Validation (Priority: P3)

**Goal**: Add a new dbt test that validates all band labels in final output tables exist in seed configuration tables.

**Independent Test**: Run `dbt test --select test_band_label_consistency --threads 1` and verify it passes.

### Implementation for User Story 4

- [x] T027 [US4] Create cross-model band consistency test at `dbt/tests/data_quality/test_band_label_consistency.sql`. The test should: (1) SELECT DISTINCT age_band values from `fct_workforce_snapshot`, (2) EXCEPT against `config_age_bands.band_label`, (3) do the same for tenure_band vs `config_tenure_bands.band_label`, (4) UNION both mismatches, (5) return rows only if mismatches exist (test passes when zero rows returned). Use `{{ ref() }}` for all table references.
- [x] T028 [US4] Validate the new consistency test by running `dbt test --select test_band_label_consistency --threads 1` from `dbt/` directory. Verify it passes with all models fixed.

**Checkpoint**: A regression guardrail now exists — any future model introducing a non-seed band label will be caught by `dbt test`.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Full validation and verification

- [x] T029 Run full `dbt build --threads 1 --fail-fast` from `dbt/` directory to validate all models compile and pass tests end-to-end.
- [x] T030 Run quickstart.md verification queries to confirm non-zero RAISE and enrollment events in `fct_yearly_events` for simulation year 2025.
- [x] T031 Grep all dbt model files for remaining hardcoded band labels (search for `'Under 25'`, `'Less than 1 year'`, `'1-2 years'`, `'3-4 years'`, `'10-14'`, `'15-19'`, `'< 30'`, `'30-39'`, `'40-49'`, `'50+'`, `'0-1'`, `'1-3'`, `'3-5'`) in `dbt/models/` and `dbt/macros/` to verify zero hardcoded band labels remain.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — verify macro capabilities first
- **US1 (Phase 2)**: Depends on Setup — fixes the 5 critical models
- **US2 (Phase 3)**: Depends on Setup — can run in parallel with US1 (different files)
- **US3 (Phase 4)**: Depends on US1 + US2 completion (schema tests validate model output)
- **US4 (Phase 5)**: Depends on US1 + US2 completion (consistency test validates all models)
- **Polish (Phase 6)**: Depends on all phases complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Setup (Phase 1) — No dependencies on other stories
- **User Story 2 (P2)**: Can start after Setup (Phase 1) — No dependencies on US1 (different files)
- **User Story 3 (P3)**: Depends on US1 + US2 (schema tests need correct model output to pass)
- **User Story 4 (P3)**: Depends on US1 + US2 (consistency test needs all models fixed)

### Within Each User Story

- All model fix tasks within a story are [P] parallelizable (different files)
- Validation task (T008, T023, T026, T028) must run after all model fixes in that phase

### Parallel Opportunities

- **T001 + T002**: Setup verification tasks can run in parallel
- **T003-T007**: All 5 critical model fixes can run in parallel (different files)
- **T009-T022**: All 14 fragile model fixes can run in parallel (different files)
- **US1 + US2**: Phases 2 and 3 can execute in parallel (no overlapping files except `int_enrollment_events_v2.sql` which has distinct line ranges per story)
- **T024 + T025**: Both schema.yml changes can be done sequentially in same file
- **T027**: Independent of other Phase 5 work

---

## Parallel Example: User Story 1

```bash
# Launch all 5 critical model fixes in parallel:
Task: "T003 - Fix int_active_employees_by_year.sql"
Task: "T004 - Fix int_active_employees_prev_year_snapshot.sql"
Task: "T005 - Fix dim_enrollment_hazards.sql"
Task: "T006 - Fix int_enrollment_events_v2.sql (lines 377-388)"
Task: "T007 - Fix events_enrollment_sql.sql"

# Then validate:
Task: "T008 - Run dbt build to validate"
```

## Parallel Example: User Story 2

```bash
# Launch all 14 fragile model fixes in parallel:
Task: "T009-T022 - All can run concurrently (different files)"

# Then validate:
Task: "T023 - Run dbt build to validate"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup verification (T001-T002)
2. Complete Phase 2: Fix 5 critical models (T003-T008)
3. **STOP and VALIDATE**: Run simulation, verify non-zero events
4. This alone fixes the actively broken salary growth and enrollment

### Incremental Delivery

1. Complete Setup → Macros verified
2. Fix 5 critical models (US1) → Salary growth and enrollment restored (MVP!)
3. Fix 14 fragile models (US2) → Band customization now works end-to-end
4. Fix schema tests (US3) → Test suite validates correctly
5. Add consistency test (US4) → Regression guardrail in place
6. Polish → Full validation complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each task includes exact file paths and line number ranges for precision
- For each model fix: read the file first to identify the exact column names/expressions used, then replace the CASE block with the appropriate macro call
- The `assign_age_band` / `assign_tenure_band` macros accept expressions (e.g., `'current_age + 1'`) per CLAUDE.md Section 9.1
- `dim_enrollment_hazards.sql` is a special case: it's a lookup table defining rates per band, so fix string literals directly rather than using macros
- `int_enrollment_events_v2.sql` appears in both US1 (critical fix, lines 377-388) and US2 (fragile fix, lines 71-76, 108-113) — different line ranges, no conflict
