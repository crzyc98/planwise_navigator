# Tasks: Fix Census Compensation Annualization Logic

**Input**: Design documents from `/specs/043-fix-annualization-logic/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Included per FR-007 and User Story 3 (P2) in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Baseline Capture)

**Purpose**: Capture current state before making changes to enable regression comparison

- [x] T001 Capture pre-fix baseline by running `dbt run --select stg_census_data int_baseline_workforce --threads 1` from `dbt/` directory and recording row counts and sample compensation values
- [x] T002 Run existing schema tests to confirm green baseline: `dbt test --select stg_census_data --threads 1` from `dbt/` directory

**Checkpoint**: Baseline state captured. All existing tests pass. Changes can now begin.

---

## Phase 2: User Story 1 - Correct Annualization in Staging Model (Priority: P1) MVP

**Goal**: Clarify the annualization logic in `stg_census_data.sql` so that `employee_annualized_compensation` and `employee_plan_year_compensation` are clearly documented with their correct semantics. No value changes — comments and clarity only.

**Independent Test**: Rebuild `stg_census_data` and verify `employee_annualized_compensation = employee_gross_compensation` for all rows. Verify `employee_plan_year_compensation` is correctly prorated by `days_active_in_year / 365.0`.

### Implementation for User Story 1

- [x] T003 [US1] Update the `annualized_data` CTE comment block (lines 79-80) in `dbt/models/staging/stg_census_data.sql` to clearly state the data contract: `employee_gross_compensation` is an annual salary rate, not prorated plan-year earnings
- [x] T004 [US1] Update the `comp_data` CTE comments (lines 107-118) in `dbt/models/staging/stg_census_data.sql` to clearly document: (1) `computed_plan_year_compensation` = prorated amount for active days in plan year, (2) `employee_annualized_compensation` = full-year equivalent rate (equals gross per data contract). Replace the misleading comment on line 115 ("Gross compensation is already an annual rate; no annualization needed")
- [x] T005 [US1] Verify edge case handling in `dbt/models/staging/stg_census_data.sql`: confirm that `days_active_in_year = 0` produces `computed_plan_year_compensation = 0.0` (line 112 CASE statement) and that `employee_annualized_compensation` retains the gross value regardless
- [x] T006 [US1] Rebuild staging model and verify zero value changes: `dbt run --select stg_census_data --threads 1` from `dbt/` directory, then run `dbt test --select stg_census_data --threads 1` to confirm existing schema tests pass

**Checkpoint**: Staging model has clarified comments. All values unchanged. Schema tests pass.

---

## Phase 3: User Story 2 - Remove HOTFIX from Baseline Workforce Model (Priority: P1)

**Goal**: Remove tech debt from `int_baseline_workforce.sql` by cleaning up HOTFIX/bypass comments and documenting that `current_compensation` comes from the corrected staging field.

**Independent Test**: Rebuild `int_baseline_workforce` and verify `current_compensation` matches `employee_annualized_compensation` from staging for all employees. Grep the file for HOTFIX/bypass/TODO and confirm zero matches.

### Implementation for User Story 2

- [x] T007 [US2] Review `dbt/models/intermediate/int_baseline_workforce.sql` and remove any HOTFIX, bypass, or TODO comments related to annualization. Add a brief comment on line 25 documenting that `current_compensation` equals the annual salary rate from `stg_census_data.employee_annualized_compensation`
- [x] T008 [US2] Rebuild baseline model and verify zero value changes: `dbt run --select stg_census_data int_baseline_workforce --threads 1` from `dbt/` directory, then validate with query: `SELECT COUNT(*) FROM int_baseline_workforce b JOIN stg_census_data s ON b.employee_id = s.employee_id WHERE b.current_compensation != s.employee_annualized_compensation` (expect 0 rows)

**Checkpoint**: Baseline model is clean. No HOTFIX comments remain. Values unchanged. Ready for test authoring.

---

## Phase 4: User Story 3 - Validate Annualization with Automated Tests (Priority: P2)

**Goal**: Add comprehensive dbt singular test covering proration math, boundary conditions, and cross-model consistency using the project's CRITICAL/ERROR/WARNING severity classification pattern.

**Independent Test**: Run `dbt test --select test_annualization_logic --vars "simulation_year: 2025" --threads 1` and verify 0 rows returned (all rules pass).

### Implementation for User Story 3

- [x] T009 [US3] Create `dbt/tests/data_quality/test_annualization_logic.sql` implementing 6 validation rules (ANN_004 dropped — days_active bounds are transitively validated by ANN_002+ANN_003): ANN_001 (CRITICAL: annualized = gross), ANN_002 (CRITICAL: plan_year_comp >= 0), ANN_003 (ERROR: plan_year_comp <= gross * 366/365), ANN_005 (WARNING: full-year employees plan_year approx gross), ANN_006 (ERROR: zero-day employees have plan_year = 0), ANN_007 (WARNING: cross-model baseline.current_compensation = staging.employee_annualized_compensation). Follow the severity-classified pattern from `dbt/tests/data_quality/test_employee_contributions.sql` with output columns: simulation_year, validation_rule, validation_source, severity, employee_id, validation_message
- [x] T010 [US3] Run the new annualization test: `dbt test --select test_annualization_logic --vars "simulation_year: 2025" --threads 1` from `dbt/` directory and verify 0 violations returned (all 6 rules pass)

**Checkpoint**: All 7 annualization validation rules pass. Test coverage gap is closed.

---

## Phase 5: Polish & Regression Validation

**Purpose**: Full regression to confirm zero downstream impact across all 52 models that reference `current_compensation`

- [x] T011 Run existing compensation regression tests: `dbt test --select test_compensation_bounds test_negative_compensation test_multi_year_compensation_inflation --vars "simulation_year: 2025" --threads 1` from `dbt/` directory
- [x] T012 Run full dbt build for complete regression validation: `dbt build --threads 1` from `dbt/` directory. 385 PASS, 1 pre-existing ERROR (unrelated int_deferral_rate_escalation_events compilation error). Also fixed 2 pre-existing schema.yml expression_is_true syntax bugs on annualization columns.
- [x] T013 Run quickstart.md validation queries against `dbt/simulation.duckdb` to confirm: (1) zero mismatches between annualized and gross, (2) proration ratios are valid for partial-year employees, (3) baseline-to-staging consistency is zero-diff

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **User Story 1 (Phase 2)**: Depends on Phase 1 — captures baseline before edits
- **User Story 2 (Phase 3)**: Depends on Phase 2 — staging must be clarified first
- **User Story 3 (Phase 4)**: Depends on Phase 3 — both models must be updated before tests validate them
- **Polish (Phase 5)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Setup (Phase 1). Modifies `stg_census_data.sql` only.
- **User Story 2 (P1)**: Depends on US1 completion. Modifies `int_baseline_workforce.sql` which consumes staging output.
- **User Story 3 (P2)**: Depends on US1 + US2 completion. Test validates both updated models.

### Within Each User Story

- Edit SQL comments/logic first
- Rebuild model to verify
- Validate with queries or tests
- Confirm no value changes before proceeding

### Parallel Opportunities

- T003 and T004 can be combined into a single edit session (same file, `stg_census_data.sql`)
- T001 and T002 (Setup) are independent and can run in parallel
- T011, T012, T013 (Polish) are sequential (each depends on prior success)

---

## Parallel Example: User Story 1

```bash
# T003 + T004 can be done in a single edit pass on stg_census_data.sql
# Then T005 is a verification step (read-only)
# Then T006 is a rebuild + test step
```

## Parallel Example: Polish Phase

```bash
# Sequential execution required:
# T011: Compensation-specific regression tests
# T012: Full dbt build (includes T011 scope plus all other models)
# T013: Manual validation queries from quickstart.md
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Capture baseline
2. Complete Phase 2: Clarify staging model comments
3. Complete Phase 3: Clean baseline model
4. **STOP and VALIDATE**: Both models rebuild with identical values
5. This alone resolves the tech debt and HOTFIX removal

### Full Delivery (Add User Story 3)

1. Complete MVP (Phases 1-3)
2. Complete Phase 4: Add annualization tests
3. Complete Phase 5: Full regression
4. All acceptance criteria met, all success criteria validated

---

## Notes

- **No value changes expected**: This is primarily a clarity and test coverage fix. `employee_annualized_compensation` equals `employee_gross_compensation` before and after.
- All dbt commands must run from the `dbt/` directory with `--threads 1` per constitution.
- The 7 test rules in `test_annualization_logic.sql` follow the established severity pattern from `test_employee_contributions.sql`.
- Total scope: 2 files modified (comments only), 1 file created (test), 52 downstream models validated via regression.
