# Tasks: Fix Tenure Eligibility Enforcement for Employer Contributions

**Input**: Design documents from `/specs/047-fix-tenure-eligibility/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included — spec explicitly requires extending existing Python and dbt tests.

**Organization**: Tasks grouped by user story. US2 (root cause fix) must complete before US1 (verification). US3 (warnings) is independent.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No project initialization needed — existing codebase. Verify current state and understand affected code paths.

- [x] T001 Verify current test suite passes by running `pytest tests/test_match_modes.py -v` and `cd dbt && dbt test --select int_employer_eligibility --threads 1`

---

## Phase 2: User Story 2 — `allow_new_hires` Defaults to `false` When Tenure > 0 (Priority: P1) 🎯 MVP

**Goal**: Change the unconditional `allow_new_hires: true` default to a conditional default: `true` when `minimum_tenure_years == 0`, `false` when `minimum_tenure_years > 0`. This is the root cause fix.

**Independent Test**: Configure `minimum_tenure_years: 2` without setting `allow_new_hires`, run simulation, verify new hires (tenure 0) are excluded from contributions.

### Implementation for User Story 2

- [x] T002 [US2] Add `@model_validator(mode='before')` to `EmployerMatchEligibilitySettings` that checks if `allow_new_hires` is present in the input dict; if absent, sets it to `True` when `minimum_tenure_years == 0` or `False` when `minimum_tenure_years > 0`. Keep the field default as `bool = Field(default=True)` unchanged (the validator runs first). File: `planalign_orchestrator/config/workforce.py`
- [x] T003 [US2] Change `employer_match_defaults` dict at line 289 in `_export_employer_match_vars()` to compute `allow_new_hires` based on `minimum_tenure_years` instead of hardcoded `True` in `planalign_orchestrator/config/export.py`
- [x] T004 [US2] Change Pydantic extraction at line 311 in `_export_employer_match_vars()` to use conditional `allow_new_hires` default based on `minimum_tenure_years` in `planalign_orchestrator/config/export.py`
- [x] T005 [US2] Change legacy extraction at line 366 in `_export_employer_match_vars()` to use conditional `allow_new_hires` default based on `minimum_tenure_years` in `planalign_orchestrator/config/export.py`
- [x] T006 [US2] Update core contribution nested var construction (lines 654-664) in `_export_core_contribution_vars()` to apply conditional `allow_new_hires` default when the value is not explicitly set in `planalign_orchestrator/config/export.py`
- [x] T007 [P] [US2] Change dbt Jinja fallback at line 44 from `.get('allow_new_hires', true)` to `.get('allow_new_hires', core_minimum_tenure_years == 0)` in `dbt/models/intermediate/int_employer_eligibility.sql`
- [x] T008 [P] [US2] Change dbt Jinja fallback at line 57 from `.get('allow_new_hires', true)` to `.get('allow_new_hires', match_minimum_tenure_years == 0)` in `dbt/models/intermediate/int_employer_eligibility.sql`
- [x] T025 [US2] Add `match_allow_new_hires` handling to dc_plan export in `_export_employer_match_vars()`: if `dc_plan_dict.get("match_allow_new_hires")` is not None, add it to `match_eligibility_overrides["allow_new_hires"]` in `planalign_orchestrator/config/export.py` (after line 500, FR-007)
- [x] T026 [US2] Add `core_allow_new_hires` handling to dc_plan export in `_export_core_contribution_vars()`: if `dc_plan_dict.get("core_allow_new_hires")` is not None, add it to `core_eligibility_overrides["allow_new_hires"]` in `planalign_orchestrator/config/export.py` (after line 700, FR-007)

### Tests for User Story 2

- [x] T009 [US2] Add test in `tests/test_match_modes.py` that `EmployerMatchEligibilitySettings(minimum_tenure_years=2)` resolves `allow_new_hires` to `False`
- [x] T010 [US2] Add test in `tests/test_match_modes.py` that `EmployerMatchEligibilitySettings(minimum_tenure_years=0)` resolves `allow_new_hires` to `True` (backward compatibility)
- [x] T011 [US2] Add test in `tests/test_match_modes.py` that `EmployerMatchEligibilitySettings(minimum_tenure_years=2, allow_new_hires=True)` preserves explicit `True` (not overridden)
- [x] T012 [US2] Add test in `tests/test_match_modes.py` that config export via `_export_employer_match_vars()` produces `allow_new_hires: false` when `minimum_tenure_years > 0` and no explicit override
- [x] T027 [US2] Add test in `tests/test_match_modes.py` that config export via `_export_employer_match_vars()` with `dc_plan.match_allow_new_hires` set correctly propagates `allow_new_hires` into the `employer_match` dbt var (FR-007 UI path)

**Checkpoint**: `allow_new_hires` default is now conditional. New hires are no longer auto-eligible when a tenure requirement exists. Backward compatibility preserved for `minimum_tenure_years: 0`.

---

## Phase 3: User Story 1 — Tenure-Based Eligibility Correctly Excludes Ineligible Employees (Priority: P1)

**Goal**: Verify that the default fix from US2 results in correct eligibility determination — employees with tenure below the configured minimum receive $0 employer match and $0 employer core contributions.

**Independent Test**: Configure `minimum_tenure_years: 2`, run single-year simulation, verify employees with `current_tenure < 2` have $0 in `fct_workforce_snapshot`.

**Depends on**: Phase 2 (US2) — the default fix must be in place for eligibility to work correctly.

### Tests for User Story 1

- [x] T013 [US1] Extend `new_hire_edge_cases` section in `dbt/tests/analysis/test_e058_business_logic.sql` to validate that when `match_allow_new_hires = false` and `match_minimum_tenure_years > 0`, employees with `current_tenure < match_minimum_tenure_years` have `eligible_for_match = false`
- [x] T014 [US1] Add boundary test in `dbt/tests/analysis/test_e058_business_logic.sql` verifying that an employee with exactly `minimum_tenure_years` of tenure IS eligible (`>=` check)

### Verification for User Story 1

- [x] T015 [US1] Run end-to-end verification per `specs/047-fix-tenure-eligibility/quickstart.md`: configure `minimum_tenure_years: 2`, run `planalign simulate 2025`, query `int_employer_eligibility` and `fct_workforce_snapshot` to confirm ineligible employees have $0 contributions

**Checkpoint**: Eligibility correctly excludes employees below tenure minimum. Boundary cases verified. End-to-end simulation produces correct financial outputs.

---

## Phase 4: User Story 3 — Configuration Validation Warning for Contradictory Settings (Priority: P2)

**Goal**: Emit a clear warning when `allow_new_hires: true` is explicitly set alongside `minimum_tenure_years > 0`, since this combination is likely unintentional.

**Independent Test**: Set contradictory config values and verify a warning appears during simulation startup.

### Implementation for User Story 3

- [x] T016 [US3] Add warning emission to the `@model_validator` in `EmployerMatchEligibilitySettings`: when `allow_new_hires` is explicitly `True` AND `minimum_tenure_years > 0`, call `warnings.warn()` in `planalign_orchestrator/config/workforce.py`
- [x] T017 [US3] Add `validate_eligibility_configuration()` method to `SimulationConfig` in `planalign_orchestrator/config/loader.py`, following the existing `validate_threading_configuration()` pattern at lines 144-150, checking both match and core eligibility for contradictory settings
- [x] T018 [US3] Call `validate_eligibility_configuration()` alongside the existing `validate_threading_configuration()` call in `planalign_orchestrator/config/loader.py`

### Tests for User Story 3

- [x] T019 [US3] Add test in `tests/test_match_modes.py` that `EmployerMatchEligibilitySettings(minimum_tenure_years=2, allow_new_hires=True)` emits a `warnings.warn()` (use `pytest.warns()`)
- [x] T020 [US3] Add test in `tests/test_match_modes.py` that `EmployerMatchEligibilitySettings(minimum_tenure_years=0, allow_new_hires=True)` does NOT emit a warning (non-contradictory)

**Checkpoint**: Contradictory config combinations produce clear warnings. Non-contradictory combinations are silent.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all user stories.

- [x] T021 Run full Python test suite: `pytest tests/test_match_modes.py -v`
- [x] T022 Run full dbt test suite: `cd dbt && dbt test --select int_employer_eligibility --threads 1`
- [x] T023 Verify backward compatibility: confirm existing `config/simulation_config.yaml` (with `minimum_tenure_years: 0`) produces identical behavior to pre-fix baseline

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — verify baseline
- **Phase 2 (US2)**: Depends on Phase 1 — root cause fix, BLOCKS US1
- **Phase 3 (US1)**: Depends on Phase 2 — verifies eligibility correctness
- **Phase 4 (US3)**: Depends on Phase 1 only — warnings are independent of US1/US2 implementation, but T016 modifies the same validator as T002
- **Phase 5 (Polish)**: Depends on all phases complete

### Recommended Execution Order

```
T001 (baseline) → T002-T012 (US2: default fix) → T013-T015 (US1: verification)
                                                 ↘ T016-T020 (US3: warnings, after T002)
                                                              → T021-T023 (polish)
```

### Within Phase 2 (US2)

- T002 (Pydantic model) should be done first — establishes the `mode='before'` conditional default pattern
- T003, T004, T005, T006, T025, T026 (export.py changes) depend on T002's pattern but are sequential within the same file
- T007, T008 (dbt Jinja) are parallel with T003-T006 (different file)
- T009-T012, T027 (tests) depend on T002-T008 and T025-T026 being complete

### Parallel Opportunities

- T007 + T008 can run in parallel with T003-T006 (different files: `int_employer_eligibility.sql` vs `export.py`)
- T009, T010, T011 can be written in parallel (independent test cases, same file but no dependencies between them)
- T013 + T014 can be written in parallel (independent dbt test cases)
- T019 + T020 can be written in parallel (independent Python test cases)

---

## Parallel Example: User Story 2

```bash
# These can run in parallel (different files):
Task T007: "Change core allow_new_hires Jinja default in dbt/models/intermediate/int_employer_eligibility.sql"
Task T008: "Change match allow_new_hires Jinja default in dbt/models/intermediate/int_employer_eligibility.sql"
# (same file but independent lines — can be combined into one edit)

# In parallel with:
Task T003-T006: "Update export.py conditional defaults in planalign_orchestrator/config/export.py"
```

---

## Implementation Strategy

### MVP First (User Story 2 Only)

1. Complete Phase 1: Verify baseline tests pass
2. Complete Phase 2: Fix `allow_new_hires` default (root cause)
3. **STOP and VALIDATE**: Run tests, verify default resolution works correctly
4. This alone fixes the bug for all configurations where `allow_new_hires` is not explicitly set

### Incremental Delivery

1. Phase 1 → Baseline verified
2. Phase 2 (US2) → Default fix in place → Test independently (MVP!)
3. Phase 3 (US1) → End-to-end eligibility verified → Confidence in correctness
4. Phase 4 (US3) → Warnings added → Better UX for administrators
5. Phase 5 → Full regression suite clean

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- T007 and T008 edit the same file (`int_employer_eligibility.sql`) but are on different lines — they can be combined into a single edit
- T003, T004, T005, T006 all edit `export.py` — execute sequentially or as a single coherent change
- The Pydantic `mode='before'` validator approach (T002) is critical — it checks if `allow_new_hires` is present in raw input before defaults are applied, enabling conditional defaulting while keeping the `bool` field type unchanged
- No new files are created; all changes are to existing files
- Total scope: ~40 lines changed across 6 files, plus ~70 lines of new tests
