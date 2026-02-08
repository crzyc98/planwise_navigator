# Tasks: Fix Census Compensation Annualization Logic

**Input**: Design documents from `/specs/037-fix-annualization-logic/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md

**Tests**: Included — the spec (FR-006, US4) explicitly requires automated dbt tests for annualization validation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Note: US1 and US2 share the same code change in `stg_census_data.sql` since the fix applies to both full-year and partial-year employees simultaneously. US3 depends on US1/US2 being complete.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **dbt models**: `dbt/models/staging/`, `dbt/models/intermediate/`
- **dbt schema**: `dbt/models/staging/schema.yml`
- All dbt commands run from `/workspace/dbt` directory

---

## Phase 1: Setup (Pre-Fix Baseline)

**Purpose**: Capture pre-fix baseline state to verify zero regression after changes

- [ ] T001 Build current staging and baseline models to establish pre-fix state: `cd dbt && dbt run --select stg_census_data int_baseline_workforce --threads 1`
- [ ] T002 Capture pre-fix compensation snapshot for regression comparison: query `stg_census_data` to record `employee_id`, `employee_gross_compensation`, `employee_annualized_compensation` row counts and sums

**Checkpoint**: Pre-fix baseline captured — implementation can begin

---

## Phase 2: User Story 1 & 2 - Fix Annualization Formula (Priority: P1) 🎯 MVP

**Goal**: Correct the `employee_annualized_compensation` formula in `stg_census_data.sql` so it equals `employee_gross_compensation` directly (since gross is already an annual rate), fixing both full-year (US1) and partial-year (US2) employee handling in one change.

**Independent Test**: After rebuilding `stg_census_data`, verify `employee_annualized_compensation = employee_gross_compensation` for every row.

### Implementation for User Stories 1 & 2

- [ ] T003 [US1] [US2] Simplify the `employee_annualized_compensation` formula in `dbt/models/staging/stg_census_data.sql`: replace the CASE expression at lines 117-120 with `ad.employee_gross_compensation AS employee_annualized_compensation` and add clarifying comment that gross is already an annual rate per the data contract
- [ ] T004 [US1] [US2] Remove stale comment at lines 80-82 of `dbt/models/staging/stg_census_data.sql` referencing the never-implemented `annualize_partial_year_compensation` variable toggle
- [ ] T005 [US1] [US2] Rebuild the staging model and verify output: `cd dbt && dbt run --select stg_census_data --threads 1`
- [ ] T006 [US1] [US2] Verify annualized equals gross for all rows: query `stg_census_data` to confirm `employee_annualized_compensation = employee_gross_compensation` with zero exceptions
- [ ] T007 [US2] Verify plan year compensation pro-rating is unchanged: query `stg_census_data` for partial-year employees and confirm `employee_plan_year_compensation = employee_gross_compensation * days_active_in_year / 365.0` within rounding tolerance

**Checkpoint**: Staging model formula is correct — `employee_annualized_compensation` is now trustworthy

---

## Phase 3: User Story 3 - Remove HOTFIX from Baseline (Priority: P1)

**Goal**: Replace the HOTFIX bypass in `int_baseline_workforce.sql` with the corrected `employee_annualized_compensation` field from staging, and remove all HOTFIX/TODO comments.

**Independent Test**: Rebuild `int_baseline_workforce` and verify `current_compensation` values are identical to pre-fix baseline.

**Depends on**: Phase 2 (staging model must be fixed first)

### Implementation for User Story 3

- [ ] T008 [US3] Replace HOTFIX in `dbt/models/intermediate/int_baseline_workforce.sql`: change lines 25-27 from `stg.employee_gross_compensation AS current_compensation` (with HOTFIX/TODO comments) to `stg.employee_annualized_compensation AS current_compensation` (no comments)
- [ ] T009 [US3] Rebuild the baseline model: `cd dbt && dbt run --select stg_census_data int_baseline_workforce --threads 1`
- [ ] T010 [US3] Verify zero regression: query `int_baseline_workforce` and confirm all `current_compensation` values are identical to pre-fix baseline captured in T002
- [ ] T011 [US3] Verify no HOTFIX or annualization TODO markers remain: search `int_baseline_workforce.sql` for "HOTFIX" and "TODO.*annualization" patterns — expect zero matches

**Checkpoint**: HOTFIX removed, baseline model uses canonical annualized field, zero value regression

---

## Phase 4: User Story 4 - Add Automated dbt Tests (Priority: P2)

**Goal**: Add dbt data tests in `schema.yml` that validate annualization correctness and prevent future regression.

**Independent Test**: Run `dbt test --select stg_census_data` and verify all new tests pass.

**Depends on**: Phase 2 (staging model must be fixed for tests to pass)

### Implementation for User Story 4

- [ ] T012 [US4] Update `employee_annualized_compensation` column definition in `dbt/models/staging/schema.yml` (around line 56-60): update description to "Annualized compensation equals gross compensation (gross is already an annual rate per data contract)." and add `data_tests` with `dbt_utils.expression_is_true` asserting `= employee_gross_compensation` (named `annualized_comp_equals_gross`)
- [ ] T013 [P] [US4] Update `employee_plan_year_compensation` column definition in `dbt/models/staging/schema.yml` (around line 51-55): add `data_tests` with `dbt_utils.accepted_range` for `min_value: 0` (named `plan_year_comp_non_negative`) and `dbt_utils.expression_is_true` asserting `<= employee_gross_compensation` (named `plan_year_comp_not_exceeds_gross`)
- [ ] T014 [US4] Run all new and existing tests on the staging model: `cd dbt && dbt test --select stg_census_data --threads 1` — all tests must pass

**Checkpoint**: Automated regression tests in place — future changes to annualization logic will be caught

---

## Phase 5: Polish & Cross-Cutting Validation

**Purpose**: Full regression validation across the entire dbt project

- [ ] T015 Run full dbt build to verify no regressions across all models: `cd dbt && dbt build --threads 1 --fail-fast`
- [ ] T016 Run existing pytest suite to verify no Python-level regressions: `cd /workspace && source .venv/bin/activate && pytest -m fast`
- [ ] T017 Verify downstream compensation models produce consistent results: query `fct_workforce_snapshot` and `fct_compensation_growth` compensation fields and confirm values match pre-fix expectations

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (US1 & US2)**: Depends on Phase 1 baseline capture
- **Phase 3 (US3)**: Depends on Phase 2 — staging must be fixed before baseline can switch to annualized field
- **Phase 4 (US4)**: Depends on Phase 2 — tests validate the corrected formula
- **Phase 5 (Polish)**: Depends on Phases 2, 3, and 4

### User Story Dependencies

- **US1 & US2 (P1)**: Combined in Phase 2 — single code change fixes both stories
- **US3 (P1)**: Depends on US1/US2 — can only remove HOTFIX after staging formula is correct
- **US4 (P2)**: Depends on US1/US2 — tests validate the corrected formula. Can run in parallel with US3.

### Within Each Phase

- T003 and T004 can run in parallel (different line ranges in same file, but logically independent edits)
- T012 and T013 can run in parallel (different column sections in schema.yml)

### Parallel Opportunities

```
Phase 2 (T003-T007) ──────────┐
                               ├──► Phase 5 (T015-T017)
Phase 3 (T008-T011) ───┐      │
                        ├──────┘
Phase 4 (T012-T014) ───┘
```

Phase 3 and Phase 4 can execute in parallel once Phase 2 is complete.

---

## Implementation Strategy

### MVP First (Phases 1-3)

1. Complete Phase 1: Capture pre-fix baseline
2. Complete Phase 2: Fix annualization formula in staging
3. Complete Phase 3: Remove HOTFIX in baseline
4. **STOP and VALIDATE**: Verify zero regression with T010
5. This delivers the core fix — tech debt removed, single source of truth established

### Full Delivery (Add Phase 4-5)

6. Complete Phase 4: Add automated dbt tests
7. Complete Phase 5: Full regression validation
8. Ready for PR

---

## Notes

- This is a **zero-change-in-output** fix. All task verifications confirm numerically identical compensation values before and after.
- The fix is surgically scoped: 2 SQL files modified, 1 YAML file updated, ~10 lines changed total.
- `employee_annualized_compensation` and `employee_plan_year_compensation` are currently dead code (never consumed by downstream models). After this fix, `employee_annualized_compensation` becomes the canonical source for `current_compensation` in the baseline.
- Total tasks: 17
