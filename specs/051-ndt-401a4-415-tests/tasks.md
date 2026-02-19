# Tasks: NDT 401(a)(4) General Test & 415 Annual Additions Limit Test

**Input**: Design documents from `/specs/051-ndt-401a4-415-tests/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — constitution requires test-first development (Principle III).

**Organization**: Tasks grouped by user story. US1 and US2 are both P1 and can be implemented in parallel after foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in all descriptions

---

## Phase 1: Setup (Seed Data)

**Purpose**: Add IRS Section 415 annual additions limit to centralized IRS limits seed

- [X] T001 Add `annual_additions_limit` column to dbt/seeds/config_irs_limits.csv with values: 2024=$69,000; 2025=$70,000; 2026=$70,000; 2027=$71,000(est); 2028=$72,000(est); 2029=$73,000(est); 2030=$74,000(est); 2031=$75,000(est); 2032=$76,000(est); 2033=$77,000(est); 2034=$78,000(est); 2035=$79,000(est)
- [X] T002 Update `_ensure_seed_current()` in planalign_api/services/ndt_service.py to include `annual_additions_limit` in the column existence check alongside `hce_compensation_threshold` and `super_catch_up_limit` — auto-reload seed from CSV if column is missing

---

## Phase 2: Foundational (Pydantic Response Models)

**Purpose**: Type-safe response models that MUST be complete before service methods can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Add 401(a)(4) Pydantic response models to planalign_api/services/ndt_service.py: `Section401a4EmployeeDetail` (employee_id, is_hce, employer_nec_amount, employer_match_amount, total_employer_amount, plan_compensation, contribution_rate, years_of_service), `Section401a4ScenarioResult` (scenario_id, scenario_name, simulation_year, test_result, test_message, applied_test, hce_count, nhce_count, excluded_count, hce_average_rate, nhce_average_rate, hce_median_rate, nhce_median_rate, ratio, ratio_test_threshold=0.70, margin, include_match, service_risk_flag, service_risk_detail, hce_threshold_used, employees), `Section401a4TestResponse` (test_type="401a4", year, results) — follow existing ACPScenarioResult pattern
- [X] T004 Add 415 Pydantic response models to planalign_api/services/ndt_service.py: `Section415EmployeeDetail` (employee_id, status, employee_deferrals, employer_match, employer_nec, total_annual_additions, gross_compensation, applicable_limit, headroom, utilization_pct), `Section415ScenarioResult` (scenario_id, scenario_name, simulation_year, test_result, test_message, total_participants, excluded_count, breach_count, at_risk_count, passing_count, max_utilization_pct, warning_threshold_pct=0.95, annual_additions_limit, employees), `Section415TestResponse` (test_type="415", year, results)

**Checkpoint**: All response models defined — service implementation can begin

---

## Phase 3: User Story 1 - 401(a)(4) General Nondiscrimination Test (Priority: P1) MVP

**Goal**: Plan administrators can run the 401(a)(4) general test for any completed scenario/year and receive pass/fail with HCE/NHCE contribution rate analysis, ratio test, general test fallback, and service-based risk flag.

**Independent Test**: Load a scenario with known employer NEC and match amounts, run the test, verify pass/fail against hand-calculated expected results.

### Tests for User Story 1

> **Write these tests FIRST, ensure they FAIL before implementation**

- [X] T005 [US1] Write unit tests for 401(a)(4) test in tests/test_ndt_401a4.py: (1) ratio test pass — HCE avg 8%, NHCE avg 6%, ratio 75% > 70%, passes with +5pp margin; (2) ratio test fail → general test pass — NHCE avg < 70% of HCE avg but NHCE median >= 70% of HCE median; (3) ratio test fail → general test fail — both ratio and median checks fail; (4) service-based risk flag triggered — employer_core_status='graded_by_service' AND avg HCE tenure exceeds NHCE by >3 years; (5) NEC-only mode (default) — contribution rate uses employer_core_amount only; (6) NEC+match mode — include_match=True adds employer_match_amount to numerator; (7) edge case: all HCE — returns informational message; (8) edge case: all NHCE — auto-passes; (9) edge case: no employer contributions — returns informational message; (10) edge case: zero compensation excluded from calculation. Use in-memory DuckDB with fixture data, mock WorkspaceStorage and DatabasePathResolver.

### Implementation for User Story 1

- [X] T006 [US1] Implement `run_401a4_test()` method in planalign_api/services/ndt_service.py: (1) resolve database via `self.db_resolver.resolve(workspace_id, scenario_id)`; (2) call `_ensure_seed_current()`; (3) get HCE threshold from `config_irs_limits` for prior year (same pattern as `run_acp_test()`); (4) query `fct_workforce_snapshot` with prior-year LEFT JOIN for HCE determination; (5) calculate contribution rate per participant: `COALESCE(employer_core_amount, 0)` (+ `COALESCE(employer_match_amount, 0)` if include_match) / `prorated_annual_compensation`; (6) filter: `current_eligibility_status = 'eligible' OR IS NULL`, `prorated_annual_compensation > 0`; (7) separate HCE/NHCE groups; (8) compute averages and medians; (9) call `_compute_401a4_result()` for pass/fail logic
- [X] T007 [US1] Implement `_compute_401a4_result()` helper in planalign_api/services/ndt_service.py: (1) ratio test: `nhce_avg / hce_avg >= 0.70`; (2) if ratio fails, general test: `nhce_median / hce_median >= 0.70`; (3) margin = ratio - 0.70 (for ratio test) or median_ratio - 0.70 (for general test); (4) return `Section401a4ScenarioResult` with applied_test, margin, all metrics
- [X] T008 [US1] Implement service-based risk detection in `run_401a4_test()` in planalign_api/services/ndt_service.py: (1) read scenario config via `self.storage` to check `employer_core_contribution.status`; (2) if `status == 'graded_by_service'`, compute avg `current_tenure` for HCE and NHCE groups from query results; (3) flag `service_risk_flag=True` if HCE avg tenure - NHCE avg tenure > 3 years; (4) populate `service_risk_detail` with "HCE avg tenure: X.X yrs, NHCE avg tenure: Y.Y yrs"
- [X] T009 [US1] Add GET `/{workspace_id}/analytics/ndt/401a4` endpoint to planalign_api/routers/ndt.py: params `scenarios` (str, comma-separated), `year` (int), `include_employees` (bool, default False), `include_match` (bool, default False); follow exact pattern of existing ACP endpoint — parse scenario_ids, validate each scenario exists and is completed, loop calling `ndt_service.run_401a4_test()`, return `Section401a4TestResponse`

**Checkpoint**: 401(a)(4) test fully functional — can run via API and verify against hand-calculated examples

---

## Phase 4: User Story 2 - 415 Annual Additions Limit Test (Priority: P1)

**Goal**: Plan administrators can run the 415 test for any completed scenario/year and receive per-participant breach/at-risk/pass results with total annual additions, applicable limits, and headroom.

**Independent Test**: Load a scenario with known contribution amounts, run the test, verify each participant's total additions against IRS limit.

### Tests for User Story 2

> **Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US2] Write unit tests for 415 test in tests/test_ndt_415.py: (1) no breaches — all participants under 415 limit, test passes; (2) breach via IRS dollar limit — participant with $70K total additions vs $69K limit; (3) breach via 100% comp rule — participant earning $60K with $65K total additions, applicable limit is $60K not $69K; (4) at-risk flagging — participant at 96% utilization with default 95% threshold; (5) custom threshold — warning_threshold=0.90 flags participants at 91% utilization; (6) threshold at 100% — only actual breaches flagged, no at-risk; (7) catch-up exclusion — total contributions $35K but base_limit=$23.5K, so base deferrals capped at $23.5K for 415 calc; (8) plan-level summary — overall fail if any breach, counts correct; (9) edge case: zero compensation excluded; (10) edge case: missing IRS limits year returns error. Use in-memory DuckDB with fixture data, mock WorkspaceStorage and DatabasePathResolver.

### Implementation for User Story 2

- [X] T011 [US2] Implement `run_415_test()` method in planalign_api/services/ndt_service.py: (1) resolve database; (2) call `_ensure_seed_current()`; (3) query `config_irs_limits` for `annual_additions_limit` and `base_limit` for test year; (4) return error result if limits not found; (5) query `fct_workforce_snapshot` for eligible participants (`prorated_annual_compensation > 0`); (6) calculate base deferrals: `LEAST(COALESCE(prorated_annual_contributions, 0), base_limit)`; (7) calculate total annual additions: `base_deferrals + COALESCE(employer_match_amount, 0) + COALESCE(employer_core_amount, 0)`; (8) calculate applicable 415 limit per participant: `LEAST(annual_additions_limit, current_compensation)` using `current_compensation` (uncapped gross); (9) classify each participant: breach if `total > applicable_limit`, at_risk if `total >= warning_threshold * applicable_limit`, else pass; (10) compute plan-level summary: overall pass/fail, breach_count, at_risk_count, passing_count, max_utilization_pct; (11) return `Section415ScenarioResult`
- [X] T012 [US2] Add GET `/{workspace_id}/analytics/ndt/415` endpoint to planalign_api/routers/ndt.py: params `scenarios` (str), `year` (int), `include_employees` (bool, default False), `warning_threshold` (float, default 0.95, min 0.0, max 1.0); follow existing ACP endpoint pattern — parse, validate, loop, return `Section415TestResponse`

**Checkpoint**: 415 test fully functional — can run via API and verify breach detection against known data

---

## Phase 5: User Story 3 - Scenario Comparison & Frontend (Priority: P2)

**Goal**: Benefits consultants can compare 401(a)(4) and 415 test results across multiple scenarios in PlanAlign Studio, with a unified test-type selector and per-test result views.

**Independent Test**: Run both tests against two scenarios via the UI and verify side-by-side comparison displays correct results.

**Dependencies**: US1 (T009) and US2 (T012) must be complete — frontend calls backend endpoints

### Implementation for User Story 3

- [X] T013 [P] [US3] Add TypeScript interfaces and API client functions in planalign_studio/services/api.ts: (1) `Section401a4TestResponse`, `Section401a4ScenarioResult`, `Section401a4EmployeeDetail` interfaces matching Pydantic models; (2) `Section415TestResponse`, `Section415ScenarioResult`, `Section415EmployeeDetail` interfaces; (3) `run401a4Test(workspaceId, scenarioIds, year, includeEmployees, includeMatch)` function calling `/analytics/ndt/401a4`; (4) `run415Test(workspaceId, scenarioIds, year, includeEmployees, warningThreshold)` function calling `/analytics/ndt/415`
- [X] T014 [US3] Add test-type selector and parameter controls to planalign_studio/components/NDTTesting.tsx: (1) add `testType` state: `'acp' | '401a4' | '415'` with tab-style selector; (2) for 401(a)(4): add `includeMatch` toggle checkbox; (3) for 415: add `warningThreshold` input (default 0.95); (4) update `handleRunTest` to call appropriate API function based on `testType`; (5) preserve existing ACP behavior as default tab
- [X] T015 [US3] Add 401(a)(4) result rendering to planalign_studio/components/NDTTesting.tsx: (1) pass/fail badge with applied test name (ratio/general); (2) HCE/NHCE average rates, ratio, margin display; (3) service risk warning banner when `service_risk_flag=true`; (4) optional employee table with contribution rate, NEC amount, match amount, plan comp, HCE status, years of service; (5) comparison view showing side-by-side scenario results
- [X] T016 [US3] Add 415 result rendering to planalign_studio/components/NDTTesting.tsx: (1) pass/fail badge; (2) summary cards: breach count (red), at-risk count (yellow), passing count (green); (3) max utilization percentage display; (4) IRS limit and warning threshold info; (5) optional participant table with status, deferrals, match, NEC, total additions, applicable limit, headroom, utilization %; (6) comparison view for multi-scenario with breach/at-risk counts per scenario

**Checkpoint**: All three test types accessible from PlanAlign Studio with scenario comparison working

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge case hardening and validation across all stories

- [X] T017 Verify all edge cases from spec across both tests: all-HCE population, all-NHCE population, zero compensation exclusion, missing IRS limits year, no employer contributions, warning threshold at 100%, forfeiture limitation message in 415 test output
- [X] T018 Run quickstart.md validation — verify API examples from specs/051-ndt-401a4-415-tests/quickstart.md return expected output format against a completed simulation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on T001 (seed data needed for model defaults)
- **US1 (Phase 3)**: Depends on Phase 2 completion (Pydantic models)
- **US2 (Phase 4)**: Depends on Phase 2 completion (Pydantic models)
- **US3 (Phase 5)**: Depends on US1 (T009) and US2 (T012) — needs backend endpoints
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Independent after Phase 2 — no dependency on US2 or US3
- **US2 (P1)**: Independent after Phase 2 — no dependency on US1 or US3
- **US3 (P2)**: Depends on US1 and US2 backend endpoints being available

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Constitution Principle III)
- Service methods before router endpoints
- Core logic before service-based risk detection (US1 only)

### Parallel Opportunities

- **T003 + T004**: Pydantic models for 401(a)(4) and 415 can be written sequentially in same file (not parallel)
- **T005 + T010**: Test files for US1 and US2 are different files — CAN run in parallel
- **US1 + US2**: After foundational phase, US1 and US2 can proceed in parallel (different service methods, different test files, different endpoints)
- **T013**: API client functions can be written in parallel with backend work (codes to contract)

---

## Parallel Example: US1 + US2 After Foundational

```bash
# After Phase 2 completes, launch both user stories in parallel:

# Stream 1: US1 - 401(a)(4) Test
Task: "Write unit tests for 401(a)(4) in tests/test_ndt_401a4.py"           # T005
Task: "Implement run_401a4_test() in planalign_api/services/ndt_service.py"  # T006
Task: "Implement _compute_401a4_result() helper"                              # T007
Task: "Implement service-based risk detection"                                # T008
Task: "Add 401a4 endpoint to planalign_api/routers/ndt.py"                   # T009

# Stream 2: US2 - 415 Test (parallel with Stream 1)
Task: "Write unit tests for 415 in tests/test_ndt_415.py"                    # T010
Task: "Implement run_415_test() in planalign_api/services/ndt_service.py"    # T011
Task: "Add 415 endpoint to planalign_api/routers/ndt.py"                     # T012
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (seed data)
2. Complete Phase 2: Foundational (Pydantic models)
3. Complete Phase 3: US1 — 401(a)(4) test
4. **STOP and VALIDATE**: Run 401(a)(4) test via API, verify against hand-calculated examples
5. Deploy/demo if ready — 401(a)(4) test is independently valuable

### Full Delivery

1. Setup + Foundational → Seed and models ready
2. US1 + US2 in parallel → Both compliance tests functional via API
3. US3 → Frontend integration with test-type selector and comparison views
4. Polish → Edge case verification and quickstart validation

### Task Count Summary

| Phase | Tasks | Parallel? |
|-------|-------|-----------|
| Setup | 2 (T001-T002) | Sequential |
| Foundational | 2 (T003-T004) | Sequential (same file) |
| US1: 401(a)(4) | 5 (T005-T009) | Sequential within story |
| US2: 415 | 3 (T010-T012) | Sequential within story |
| US3: Frontend | 4 (T013-T016) | T013 parallel, rest sequential |
| Polish | 2 (T017-T018) | Sequential |
| **Total** | **18 tasks** | |

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- US1 and US2 are BOTH P1 and can proceed in parallel after Phase 2
- US3 frontend can begin T013 (API client) in parallel with backend work (codes to OpenAPI contract)
- Both service methods add to the same file (ndt_service.py) but to different methods — coordinate if parallelizing
- Both router endpoints add to the same file (ndt.py) — coordinate if parallelizing
- Commit after each completed task or logical group
