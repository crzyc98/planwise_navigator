# Tasks: Fix Yearly Participation Rate Consistency

**Input**: Design documents from `/specs/041-fix-yearly-participation-rate/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included — plan.md mandates unit tests for previously untested service (Constitution III: Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Test Infrastructure)

**Purpose**: Create shared test fixtures for in-memory DuckDB analytics testing

- [x] T001 Create test file with in-memory DuckDB fixture and `fct_workforce_snapshot` table schema in `tests/test_analytics_service.py`
  - Create a pytest fixture that:
    - Initializes an in-memory DuckDB connection
    - Creates `fct_workforce_snapshot` table with columns: `simulation_year`, `employment_status`, `is_enrolled_flag`, `prorated_annual_contributions`, `employer_match_amount`, `employer_core_amount`, `current_deferral_rate`, `prorated_annual_compensation`, `participation_status_detail`, `has_deferral_escalations`, `total_deferral_escalations`, `total_escalation_amount`, `irs_limit_reached`, `employee_id`, `scenario_id`, `plan_design_id`
    - Provides helper function to seed rows with controlled data
  - Create a mock `DatabasePathResolver` that returns a path to the in-memory database
  - Create a mock `WorkspaceStorage` for `AnalyticsService` instantiation

**Checkpoint**: Test infrastructure ready — user story implementation can begin

---

## Phase 2: User Story 1 — Consistent Per-Year Participation Rate (Priority: P1) 🎯 MVP

**Goal**: Fix the per-year participation rate to use only active employees as the population, matching the top-level rate calculation.

**Independent Test**: Query analytics endpoint for a multi-year simulation with active and terminated employees; verify per-year final-year rate matches top-level rate.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation (T002–T005), then implement the fix (T006)**

- [x] T002 [P] [US1] Write `test_participation_rate_active_only` in `tests/test_analytics_service.py`
  - Seed `fct_workforce_snapshot` with year 2025 data: 8 active employees (6 enrolled, 2 not enrolled) + 2 terminated employees (1 enrolled, 1 not enrolled)
  - Call `_get_contribution_by_year()` and assert `participation_rate` == 75.0 (6/8 active, not 7/10 total)
  - This test MUST FAIL before T006 is implemented (current code would return 70.0)

- [x] T003 [P] [US1] Write `test_zero_active_employees` in `tests/test_analytics_service.py`
  - Seed with year 2025: 0 active employees, 3 terminated employees
  - Assert `participation_rate` == 0.0 (not division error)
  - Validates FR-004

- [x] T004 [P] [US1] Write `test_all_active_enrolled` in `tests/test_analytics_service.py`
  - Seed with year 2025: 5 active employees all enrolled, 2 terminated employees not enrolled
  - Assert `participation_rate` == 100.0

- [x] T005 [P] [US1] Write `test_contribution_totals_include_all_employees` in `tests/test_analytics_service.py`
  - Seed with active and terminated employees with known contribution amounts
  - Assert `total_employee_contributions` includes contributions from terminated employees
  - Assert `total_employer_match` includes match amounts from terminated employees
  - This validates the assumption that only `participation_rate` changes scope, not contribution totals

### Implementation for User Story 1

- [x] T006 [US1] Fix participation rate SQL in `_get_contribution_by_year()` in `planalign_api/services/analytics_service.py`
  - Replace line 185:
    ```
    COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as participation_rate
    ```
  - With:
    ```
    COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' AND is_enrolled_flag THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' THEN 1 END), 0) as participation_rate
    ```
  - Do NOT change any other aggregations in the query (contribution sums, avg deferral rate, participant_count)

- [x] T007 [US1] Run tests T002–T005 and verify all pass in `tests/test_analytics_service.py`
  - Execute: `pytest tests/test_analytics_service.py -v`
  - All 4 tests must pass

**Checkpoint**: Per-year participation rate now uses active-only population. Core fix complete and verified.

---

## Phase 3: User Story 2 — Backward-Compatible Top-Level Rate (Priority: P2)

**Goal**: Verify the top-level `participation_rate` in `DCPlanAnalytics` remains unchanged (final-year value from `_get_participation_summary()`).

**Independent Test**: Compare the top-level participation rate field before and after the fix against the same test data.

### Tests for User Story 2

- [x] T008 [P] [US2] Write `test_final_year_matches_top_level` in `tests/test_analytics_service.py`
  - Seed multi-year data (2025, 2026) with active and terminated employees
  - Call `get_dc_plan_analytics()` (full service method)
  - Assert `DCPlanAnalytics.participation_rate` (top-level) matches `contribution_by_year[-1].participation_rate` (final year per-year) within 0.01 pp
  - Validates SC-001

- [x] T009 [P] [US2] Write `test_single_year_matches_top_level` in `tests/test_analytics_service.py`
  - Seed single-year data (2025 only)
  - Call `get_dc_plan_analytics()`
  - Assert top-level `participation_rate` == single-year `contribution_by_year[0].participation_rate`
  - Validates edge case from spec

### Verification for User Story 2

- [x] T010 [US2] Run all tests and verify backward compatibility in `tests/test_analytics_service.py`
  - Execute: `pytest tests/test_analytics_service.py -v`
  - All 6 tests (T002–T005, T008–T009) must pass

**Checkpoint**: Both per-year and top-level participation rates are consistent and backward compatible.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across the full test suite

- [x] T011 Run full fast test suite to verify no regressions: `pytest -m fast`
- [x] T012 Run quickstart.md validation — verify the documented fix matches what was implemented in `planalign_api/services/analytics_service.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **User Story 1 (Phase 2)**: Depends on Setup (T001)
- **User Story 2 (Phase 3)**: Depends on User Story 1 completion (T006 must be done for top-level/per-year match tests to pass)
- **Polish (Phase 4)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Setup (Phase 1). This is the core fix — must be done first.
- **User Story 2 (P2)**: Depends on US1 completion. Tests verify the relationship between per-year and top-level rates, which requires the fix from US1 to be in place.

### Within Each User Story

- Tests (T002–T005) MUST be written and FAIL before implementation (T006)
- Implementation (T006) makes tests pass
- Verification (T007) confirms all pass

### Parallel Opportunities

- **Phase 1**: Single task, no parallelism needed
- **Phase 2 Tests**: T002, T003, T004, T005 can all be written in parallel (different test functions, same file)
- **Phase 3 Tests**: T008, T009 can be written in parallel

---

## Parallel Example: User Story 1

```bash
# Write all US1 tests in parallel (they target different test functions):
Task: "Write test_participation_rate_active_only in tests/test_analytics_service.py"
Task: "Write test_zero_active_employees in tests/test_analytics_service.py"
Task: "Write test_all_active_enrolled in tests/test_analytics_service.py"
Task: "Write test_contribution_totals_include_all_employees in tests/test_analytics_service.py"

# Then implement the fix (sequential, single line change):
Task: "Fix participation rate SQL in planalign_api/services/analytics_service.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: User Story 1 tests + fix (T002–T007)
3. **STOP and VALIDATE**: Run `pytest tests/test_analytics_service.py -v` — all 4 tests pass
4. The core fix is done. Per-year participation rate now matches active-only methodology.

### Full Delivery

1. Complete MVP (Phase 1 + Phase 2)
2. Add User Story 2 tests (T008–T010) → Verify backward compatibility
3. Polish (T011–T012) → Full regression check
4. Total: 12 tasks, ~30 minutes estimated work

---

## Notes

- The fix is a single SQL subexpression change in one file
- All test tasks target the same new file (`tests/test_analytics_service.py`) but different test functions
- No model changes needed — `ContributionYearSummary.participation_rate` field already exists
- No frontend changes — TypeScript interface already has the field
- No API contract changes — response schema unchanged, only computed values change
