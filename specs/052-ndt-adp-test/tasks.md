# Tasks: NDT ADP (Actual Deferral Percentage) Test

**Input**: Design documents from `/specs/052-ndt-adp-test/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.yaml

**Tests**: Included per Constitution Principle III (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Phase 1: Foundational (Shared Models & Infrastructure)

**Purpose**: Create data models and test infrastructure shared by all user stories. No user story work can begin until this phase is complete.

- [x] T001 [P] Add `ADPEmployeeDetail`, `ADPScenarioResult`, `ADPTestResponse` Pydantic models to `planalign_api/services/ndt_service.py` — place after existing `Section415TestResponse` model, following the exact field definitions in `specs/052-ndt-adp-test/data-model.md`
- [x] T002 [P] Add `ADPEmployeeDetail`, `ADPScenarioResult`, `ADPTestResponse` TypeScript interfaces and `runADPTest()` function to `planalign_studio/services/api.ts` — place after existing `run415Test()` function, matching the API contract in `specs/052-ndt-adp-test/contracts/api.yaml`
- [x] T003 [P] Create `tests/test_ndt_adp.py` with test fixture setup: in-memory DuckDB database with `fct_workforce_snapshot` and `config_irs_limits` tables, `MockStorage`, mocked `DatabasePathResolver`, and `_insert_employee()` helper — follow the exact pattern from `tests/test_ndt_service.py`

**Checkpoint**: Models defined in both backend and frontend; test infrastructure ready

---

## Phase 2: User Story 1 - Run ADP Test for a Single Scenario (Priority: P1) 🎯 MVP

**Goal**: A plan administrator can run the ADP test for a single scenario and year, receiving pass/fail result with HCE/NHCE average ADPs, applied prong, threshold, margin, and excess HCE amount on failure.

**Independent Test**: Select one scenario and year, run ADP test, verify pass/fail with correct two-prong calculation and excess amount.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T004 [P] [US1] Write test `test_adp_basic_pass` in `tests/test_ndt_adp.py` — insert HCE (comp $200K, deferrals $10K → ADP 5%) and NHCE (comp $100K, deferrals $4K → ADP 4%), verify test_result="pass", basic_threshold=5% (4% × 1.25), margin=0%
- [x] T005 [P] [US1] Write test `test_adp_basic_fail_with_excess` in `tests/test_ndt_adp.py` — insert HCE (ADP 10%) and NHCE (ADP 3%), verify test_result="fail", negative margin, and excess_hce_amount = (hce_avg - applied_threshold) × sum(hce_compensations)
- [x] T006 [P] [US1] Write test `test_adp_alternative_prong_selected` in `tests/test_ndt_adp.py` — insert HCE/NHCE where alternative test (min(NHCE×2, NHCE+2pp)) produces higher threshold than basic (NHCE×1.25), verify applied_test="alternative"
- [x] T007 [P] [US1] Write test `test_adp_zero_deferrals_included` in `tests/test_ndt_adp.py` — insert eligible participant with zero deferrals, verify they are included with individual_adp=0.0 and counted in nhce_count or hce_count
- [x] T008 [P] [US1] Write tests `test_adp_no_nhce_error` and `test_adp_no_hce_autopass` in `tests/test_ndt_adp.py` — verify no NHCE returns error result, no HCE returns auto-pass

### Implementation for User Story 1

- [x] T009 [US1] Implement `_compute_adp_result()` method on `NDTService` in `planalign_api/services/ndt_service.py` — basic threshold (nhce_avg × 1.25), alternative threshold (min(nhce_avg × 2.0, nhce_avg + 0.02)), select more favorable, compute margin, compute excess_hce_amount when failing as `(hce_avg - applied_threshold) × sum(hce_compensations)`
- [x] T010 [US1] Implement `run_adp_test()` method on `NDTService` in `planalign_api/services/ndt_service.py` — follow `run_acp_test()` pattern: resolve DB, ensure seed, load HCE threshold, check prior year, execute CTE-based SQL query using `prorated_annual_contributions` as numerator, loop rows to build HCE/NHCE ADP lists, handle edge cases (no NHCE → error, no HCE → auto-pass, zero comp → exclude), call `_compute_adp_result()`. Include `safe_harbor` short-circuit (return exempt immediately) and `testing_method` parameter handling (prior year queries prior snapshot for NHCE baseline)
- [x] T011 [US1] Add `GET /{workspace_id}/analytics/ndt/adp` endpoint to `planalign_api/routers/ndt.py` — follow existing endpoint pattern with query params: `scenarios`, `year`, `include_employees`, `safe_harbor` (bool, default False), `testing_method` (str, default "current"). Import `ADPTestResponse` from service. Validate workspace, parse scenarios, verify completed, loop calling `run_adp_test()`, return `ADPTestResponse`
- [x] T012 [US1] Add `'adp'` to `TestType` union, add `'adp': 'ADP Test'` to `TEST_TYPE_LABELS`, add `<option value="adp">ADP Test</option>` to test type selector, and add ADP branch to `handleRunTest()` dispatch in `planalign_studio/components/NDTTesting.tsx` — call `runADPTest()` with `(workspaceId, scenarioIds, year, showEmployees, safeHarbor, testingMethod)`
- [x] T013 [US1] Implement `ADPSingleResult` component in `planalign_studio/components/NDTTesting.tsx` — mirror `ACPSingleResult` structure: pass/fail/exempt status card with margin, HCE/NHCE average ADPs, basic and alternative thresholds with applied prong indicator, testing method indicator, and excess HCE amount section (displayed prominently when test_result="fail"). Accept props: `result: ADPScenarioResult`, `showEmployees: boolean`, `onToggleEmployees: () => void`, `loading: boolean`
- [x] T014 [US1] Add ADP results rendering to the results section of `NDTTesting.tsx` — add conditional chain for `testType === 'adp'` that renders `ADPSingleResult` (single mode) or `ADPComparisonResults` (comparison mode, placeholder for now), following the same ternary pattern as ACP/401(a)(4)/415

**Checkpoint**: ADP test fully functional for single scenario — pass/fail, two-prong thresholds, excess amount, edge cases all working. Run `pytest tests/test_ndt_adp.py -v` to verify.

---

## Phase 3: User Story 2 - Compare ADP Results Across Scenarios (Priority: P2)

**Goal**: A plan administrator can select 2-6 scenarios and view ADP results side-by-side in a comparison grid.

**Independent Test**: Select 2+ scenarios, run ADP in comparison mode, verify side-by-side grid with reorder controls.

### Implementation for User Story 2

- [x] T015 [US2] Implement `ADPComparisonResults` component in `planalign_studio/components/NDTTesting.tsx` — mirror `ACPComparisonResults` structure: accept `results: ADPScenarioResult[]` and `scenarioOrder: string[]`, sort results by scenarioOrder, render responsive grid (2/3 columns) of pass/fail cards showing scenario name, test result, HCE/NHCE averages, margin, and excess amount (when failing)
- [x] T016 [US2] Update the ADP results rendering conditional in `NDTTesting.tsx` to route to `ADPComparisonResults` when in comparison mode (replace the placeholder added in T014)

**Checkpoint**: ADP comparison mode fully functional — multiple scenarios displayed in grid with reorder support.

---

## Phase 4: User Story 3 - View Participant-Level ADP Detail (Priority: P2)

**Goal**: A plan administrator can expand ADP results to see individual participant details (employee ID, HCE status, deferrals, compensation, individual ADP).

**Independent Test**: Run ADP test, toggle employee detail, verify participant table with correct individual ADP calculations.

### Tests for User Story 3

- [x] T017 [P] [US3] Write test `test_adp_employee_detail_populated` in `tests/test_ndt_adp.py` — run with include_employees=True, verify each ADPEmployeeDetail has correct employee_id, is_hce, employee_deferrals, plan_compensation, individual_adp (deferrals/comp), and prior_year_compensation

### Implementation for User Story 3

- [x] T018 [US3] Add expandable employee detail table to `ADPSingleResult` component in `planalign_studio/components/NDTTesting.tsx` — 6 columns: Employee ID (mono font), Classification (HCE/NHCE badge), Deferrals (currency), Compensation (currency), ADP (percentage), Prior Year Comp (currency). Follow the same collapsible table pattern as `ACPSingleResult`
- [x] T019 [US3] Add ADP branch to `handleToggleEmployees()` dispatch in `planalign_studio/components/NDTTesting.tsx` — call `runADPTest()` with `includeEmployees=true` plus current safeHarbor and testingMethod state values

**Checkpoint**: Employee detail view fully functional — individual ADP data visible for audit support.

---

## Phase 5: User Story 4 - Safe Harbor & Testing Method Controls (Priority: P3)

**Goal**: A plan administrator can toggle "Safe Harbor" to get an exempt result, and select "Prior Year" testing method to use prior year NHCE baseline.

**Independent Test**: Toggle Safe Harbor on → verify exempt result. Select Prior Year → verify prior year NHCE average is used.

### Tests for User Story 4

- [x] T020 [P] [US4] Write test `test_adp_safe_harbor_exempt` in `tests/test_ndt_adp.py` — call run_adp_test with safe_harbor=True, verify test_result="exempt", safe_harbor=True, and no ADP calculations performed (hce_count=0, nhce_count=0)
- [x] T021 [P] [US4] Write test `test_adp_prior_year_testing_method` in `tests/test_ndt_adp.py` — insert different NHCE data for year 2024 and 2025, call with testing_method="prior", verify nhce_average_adp reflects 2024 NHCE data (not 2025)
- [x] T022 [P] [US4] Write test `test_adp_prior_year_fallback` in `tests/test_ndt_adp.py` — call with testing_method="prior" when no prior year data exists, verify falls back to current year with warning message in test_message

### Implementation for User Story 4

- [x] T023 [US4] Add `safeHarbor` state (`useState(false)`) and Safe Harbor toggle UI to `planalign_studio/components/NDTTesting.tsx` — render checkbox when `testType === 'adp'`, following the `includeMatch` toggle pattern from 401(a)(4). Wire to `handleRunTest()` and `handleToggleEmployees()` calls
- [x] T024 [US4] Add `testingMethod` state (`useState<'current' | 'prior'>('current')`) and Testing Method selector UI to `planalign_studio/components/NDTTesting.tsx` — render dropdown when `testType === 'adp'` with options "Current Year" (default) and "Prior Year". Wire to API calls

**Checkpoint**: Full feature complete — safe harbor exemption and prior/current year testing method working end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge case coverage, validation, and cleanup

- [x] T025 [P] Write test `test_adp_zero_compensation_excluded` in `tests/test_ndt_adp.py` — insert participant with zero prorated_annual_compensation, verify excluded_count incremented and participant not in HCE/NHCE groups
- [x] T026 [P] Write test `test_adp_missing_irs_limits_error` in `tests/test_ndt_adp.py` — query year with no config_irs_limits entry, verify test_result="error" with descriptive message
- [x] T027 [P] Write test `test_adp_database_not_found_error` in `tests/test_ndt_adp.py` — mock resolver returning non-existent path, verify test_result="error"
- [x] T028 Run full test suite `pytest tests/test_ndt_adp.py -v` and verify all ADP tests pass, then run `pytest tests/ -v --tb=short` to ensure no regressions in existing NDT tests

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies — can start immediately
- **Phase 2 (US1 - Core ADP)**: Depends on Phase 1 completion — BLOCKS all other stories
- **Phase 3 (US2 - Comparison)**: Depends on Phase 2 (needs ADPSingleResult and backend)
- **Phase 4 (US3 - Employee Detail)**: Depends on Phase 2 (needs ADPSingleResult component)
- **Phase 5 (US4 - Safe Harbor/Config)**: Depends on Phase 2 (needs working ADP test flow)
- **Phase 6 (Polish)**: Depends on Phases 2-5

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 1 — no dependencies on other stories
- **US2 (P2)**: Requires US1 backend complete (reuses same endpoint and service method)
- **US3 (P2)**: Requires US1 frontend complete (extends ADPSingleResult component)
- **US4 (P3)**: Requires US1 complete (adds toggles that feed into existing ADP flow)

### Within Each User Story

- Tests written FIRST, verified to FAIL before implementation (Constitution Principle III)
- Backend models before service methods
- Service methods before API endpoints
- API endpoints before frontend integration
- Frontend dispatch before result components

### Parallel Opportunities

**Phase 1** (all [P]):
- T001, T002, T003 can all run in parallel (different files)

**Phase 2 - US1 Tests** (all [P]):
- T004, T005, T006, T007, T008 can all run in parallel (same file but independent test functions)

**Phase 2 - US1 Implementation**:
- T009 (_compute_adp_result) and T012 (frontend TestType + dispatch) can run in parallel
- T013 (ADPSingleResult component) can start once T012 is committed

**Phases 3, 4, 5** after US1 is complete:
- US2 (T015-T016), US3 (T017-T019), US4 (T020-T024) can proceed in parallel since they modify different parts of the codebase

**Phase 6** (all [P]):
- T025, T026, T027 can all run in parallel (independent test functions)

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests in parallel (write first, verify they fail):
Task: T004 "test_adp_basic_pass in tests/test_ndt_adp.py"
Task: T005 "test_adp_basic_fail_with_excess in tests/test_ndt_adp.py"
Task: T006 "test_adp_alternative_prong_selected in tests/test_ndt_adp.py"
Task: T007 "test_adp_zero_deferrals_included in tests/test_ndt_adp.py"
Task: T008 "test_adp_no_nhce_error and test_adp_no_hce_autopass in tests/test_ndt_adp.py"

# Then launch backend + frontend models in parallel:
Task: T009 "_compute_adp_result() in planalign_api/services/ndt_service.py"
Task: T012 "TestType + dispatch in planalign_studio/components/NDTTesting.tsx"

# Then sequential: T010 → T011 → T013 → T014
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational models and test infrastructure
2. Complete Phase 2: US1 — Core ADP test (backend + frontend single result)
3. **STOP and VALIDATE**: Run `pytest tests/test_ndt_adp.py -v`, launch studio, run ADP test manually
4. Deploy/demo if ready — single scenario ADP testing is fully functional

### Incremental Delivery

1. Phase 1 (Foundational) → Models and test infra ready
2. Phase 2 (US1) → Single scenario ADP test working → **MVP Demo**
3. Phase 3 (US2) → Add comparison mode → Demo multi-scenario
4. Phase 4 (US3) → Add employee detail → Demo audit capability
5. Phase 5 (US4) → Add safe harbor + testing method → Demo full feature
6. Phase 6 (Polish) → Edge cases + regression check → Release ready

### Key Files Summary

| File | Tasks | Total Changes |
|------|-------|---------------|
| `planalign_api/services/ndt_service.py` | T001, T009, T010 | ~200 lines added |
| `planalign_api/routers/ndt.py` | T011 | ~50 lines added |
| `planalign_studio/components/NDTTesting.tsx` | T012, T013, T014, T015, T016, T018, T019, T023, T024 | ~250 lines added |
| `planalign_studio/services/api.ts` | T002 | ~60 lines added |
| `tests/test_ndt_adp.py` | T003-T008, T017, T020-T022, T025-T027 | ~300 lines (new file) |

---

## Notes

- [P] tasks = different files, no dependencies — safe to run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable after US1 backend is in place
- Constitution Principle III requires tests FIRST — verify they FAIL before implementing
- ADP mirrors ACP pattern — reference `run_acp_test()` and `ACPSingleResult` as implementation guides
- `prorated_annual_contributions` is the ADP numerator (not `employer_match_amount` used by ACP)
- Excess HCE amount formula: `(hce_avg_adp - applied_threshold) × sum(hce_plan_compensations)`
