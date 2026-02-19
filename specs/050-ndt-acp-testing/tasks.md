# Tasks: NDT ACP Testing

**Input**: Design documents from `/specs/050-ndt-acp-testing/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/ndt-api.yaml

**Tests**: Test tasks included in Polish phase (not TDD — tests validate after implementation).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `planalign_api/` (FastAPI routers and services)
- **Frontend**: `planalign_studio/` (React components and services)
- **Data**: `dbt/seeds/` (CSV seed files)
- **Tests**: `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Seed data extension required by all downstream computation

- [X] T001 Add `hce_compensation_threshold` column to `dbt/seeds/config_irs_limits.csv` with values for years 2024-2035 ($155K for 2024, $160K for 2025, increasing ~$5K/year). Run `cd dbt && dbt seed --threads 1` to load.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend models, router registration, and frontend navigation that MUST be complete before any user story work

**All tasks target different files and can run in parallel.**

- [X] T002 [P] Create Pydantic response models (`ACPTestResponse`, `ACPScenarioResult`, `ACPEmployeeDetail`, `AvailableYearsResponse`) and `NDTService` class skeleton with constructor following `DatabasePathResolver` pattern in `planalign_api/services/ndt_service.py`. See `contracts/ndt-api.yaml` for schema and `planalign_api/services/analytics_service.py` for constructor pattern.
- [X] T003 [P] Create NDT router with dependency injection (`get_settings` → `WorkspaceStorage` → `NDTService`) and stub endpoints for `GET /analytics/ndt/acp` and `GET /analytics/ndt/available-years` in `planalign_api/routers/ndt.py`. Register router with `app.include_router(ndt_router, prefix="/api/workspaces", tags=["NDT Testing"])` in `planalign_api/main.py`.
- [X] T004 [P] Add NDT Testing nav item `<NavItem to="/analytics/ndt" icon={<Shield size={20} />} label="NDT Testing" />` after Vesting in sidebar nav in `planalign_studio/components/Layout.tsx`. Add `Shield` to lucide-react imports. Add `<Route path="analytics/ndt" element={<NDTTesting />} />` in `planalign_studio/App.tsx`.
- [X] T005 [P] Add `runACPTest(workspaceId, scenarioIds, year, includeEmployees?)` and `getNDTAvailableYears(workspaceId, scenarioId)` functions in `planalign_studio/services/api.ts`. Follow existing `compareDCPlanAnalytics` pattern with comma-separated scenario query params.

**Checkpoint**: Router returns stubs, nav item visible, API client ready — user story implementation can begin.

---

## Phase 3: User Story 1 — Run ACP Test for a Single Scenario (Priority: P1) MVP

**Goal**: A plan administrator can select a single scenario + year, run the ACP test, and see pass/fail with HCE/NHCE average ACP percentages.

**Independent Test**: Navigate to NDT Testing → select a completed scenario → select year → click Run Test → verify pass/fail result and group averages displayed.

### Implementation for User Story 1

- [X] T006 [US1] Implement `get_available_years(workspace_id, scenario_id)` method in `planalign_api/services/ndt_service.py`. Query `SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year` via `DatabasePathResolver`. Return `AvailableYearsResponse` with years list and latest as default.
- [X] T007 [US1] Implement `run_acp_test(workspace_id, scenario_id, year)` core method in `planalign_api/services/ndt_service.py`. The single CTE-based DuckDB query must: (1) fetch HCE threshold from `config_irs_limits`, (2) join current-year `fct_workforce_snapshot` with prior-year for HCE determination, (3) filter to `current_eligibility_status = 'eligible'` and `prorated_annual_compensation > 0`, (4) compute per-employee ACP as `COALESCE(employer_match_amount, 0) / prorated_annual_compensation`, (5) aggregate by `is_hce` group. See `quickstart.md` for reference SQL.
- [X] T008 [US1] Implement IRS test pass/fail logic as a private method in `planalign_api/services/ndt_service.py`. Compute `basic_threshold = nhce_avg * 1.25`, `alt_threshold = MIN(nhce_avg * 2.0, nhce_avg + 0.02)`, select more favorable. Handle edge cases: no NHCE group → error, no HCE group → auto-pass, no eligible employees → error, first simulation year (no prior-year data) → fallback to current-year compensation, missing HCE threshold in seed → error with descriptive message. Return populated `ACPScenarioResult`.
- [X] T009 [US1] Wire `run_acp_test` and `get_available_years` endpoint handlers in `planalign_api/routers/ndt.py`. Add workspace existence validation, scenario existence + completion status validation, year parameter validation. Parse comma-separated `scenarios` query param. Loop over scenarios calling service method for each. Return `ACPTestResponse` with results array.
- [X] T010 [US1] Build NDTTesting page component in `planalign_studio/components/NDTTesting.tsx`. Include: (1) test type dropdown defaulting to "ACP" (only option for now), (2) scenario dropdown populated from completed scenarios via `useOutletContext<LayoutContextType>()` for active workspace, (3) year dropdown populated from `getNDTAvailableYears()` cascading off scenario selection, (4) "Run Test" button with `canRun` guard (scenario + year selected). Follow `VestingAnalysis.tsx` year-selector and `DCPlanAnalytics.tsx` scenario-selector patterns.
- [X] T011 [US1] Implement single-scenario results display in `planalign_studio/components/NDTTesting.tsx`. Show a result card with: pass/fail badge (green/red), HCE average ACP %, NHCE average ACP %, and the applied threshold. Use conditional rendering pattern: loading → error → empty → results.

**Checkpoint**: User Story 1 complete — single scenario ACP test is fully functional. The user can navigate to NDT Testing, pick a scenario and year, run the test, and see a clear pass/fail result.

---

## Phase 4: User Story 2 — View ACP Test Details and Breakdown (Priority: P2)

**Goal**: After running the ACP test, the administrator sees the full numerical breakdown and can expand a per-employee detail table.

**Independent Test**: Run an ACP test → verify detailed breakdown shows both thresholds, applied method, group counts, and margin → expand per-employee table → verify individual ACP, HCE status, match amount, and compensation for each employee.

### Implementation for User Story 2

- [X] T012 [US2] Add `include_employees` parameter support to `run_acp_test()` in `planalign_api/services/ndt_service.py`. When true, return the full per-employee result set as `ACPEmployeeDetail` list in the `employees` field of `ACPScenarioResult`. Include: employee_id, is_hce, is_enrolled, employer_match_amount, eligible_compensation, individual_acp, prior_year_compensation.
- [X] T013 [US2] Add detailed stats breakdown section below the pass/fail card in `planalign_studio/components/NDTTesting.tsx`. Display: HCE count, NHCE count, excluded count, eligible-not-enrolled count, basic test threshold (NHCE x 1.25), alternative test threshold (lesser of NHCE x 2 and NHCE + 2%), which test was applied, margin (how much room before threshold), and the HCE compensation dollar threshold used.
- [X] T014 [US2] Add expandable per-employee detail table in `planalign_studio/components/NDTTesting.tsx`. Collapsed by default with a "Show Employee Details" toggle button. Table columns: Employee ID, HCE/NHCE badge, Enrolled status, Employer Match ($), Eligible Compensation ($), Individual ACP (%). Call API with `include_employees=true` when table is expanded.

**Checkpoint**: User Story 2 complete — detailed breakdown and per-employee drill-down are functional.

---

## Phase 5: User Story 3 — Compare ACP Results Across Multiple Scenarios (Priority: P3)

**Goal**: The administrator can select 2+ scenarios and see ACP results side-by-side for comparison.

**Independent Test**: Select two completed scenarios → run ACP test → verify comparison layout shows pass/fail + group averages for each scenario → verify passing/failing scenarios are visually distinct.

### Implementation for User Story 3

- [X] T015 [US3] Add comparison mode toggle and multi-scenario pill selector in `planalign_studio/components/NDTTesting.tsx`. Follow `DCPlanAnalytics.tsx` pattern: comparison mode button toggles between single-select and multi-select. In comparison mode, show completed scenarios as selectable pills with `bg-fidelity-green` for selected. Cap at `MAX_SCENARIO_SELECTION` (6). Update API call to pass all selected scenario IDs.
- [X] T016 [US3] Add side-by-side comparison results layout in `planalign_studio/components/NDTTesting.tsx`. When multiple scenarios selected, render one result card per scenario in a responsive grid (1 column on mobile, 2-3 on desktop). Each card shows: scenario name, pass/fail badge with color coding (green pass, red fail), HCE average ACP, NHCE average ACP, applied threshold, and margin.

**Checkpoint**: User Story 3 complete — multi-scenario comparison is functional with color-coded pass/fail.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, tests, and UX refinement across all stories

- [X] T017 [P] Add comprehensive loading, error, and empty state handling in `planalign_studio/components/NDTTesting.tsx`. Loading: spinner during API calls. Error: descriptive messages with retry button. Empty: guidance message when no scenarios available or no simulation completed. Use existing `Loader2` spinner pattern from lucide-react.
- [X] T018 [P] Write pytest unit tests for NDT service in `tests/test_ndt_service.py`. Test cases: (1) correct HCE classification based on prior-year comp vs threshold, (2) correct per-employee ACP = match/comp, (3) correct group average computation, (4) basic test threshold = NHCE x 1.25, (5) alternative test threshold = min(NHCE x 2, NHCE + 0.02), (6) more favorable test selected, (7) edge case: no NHCE → error, (8) edge case: no HCE → pass, (9) edge case: first-year fallback to current-year comp. Use in-memory DuckDB for test isolation.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (seed data loaded before service queries it)
- **User Story 1 (Phase 3)**: Depends on Phase 2 — implements core ACP test
- **User Story 2 (Phase 4)**: Depends on Phase 3 — extends results display and adds drill-down
- **User Story 3 (Phase 5)**: Depends on Phase 3 — extends with multi-scenario comparison
- **Polish (Phase 6)**: Can start after Phase 3; ideally after all stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Requires Foundational (Phase 2). No other story dependencies.
- **User Story 2 (P2)**: Requires User Story 1 (extends the results view and API with employee detail).
- **User Story 3 (P3)**: Requires User Story 1 (extends single-scenario to multi-scenario). Independent of US2.

### Within Each User Story

- Backend service logic before router wiring
- Router endpoint before frontend page
- Core display before enhancements

### Parallel Opportunities

**Phase 2** (all 4 tasks target different files):
```
T002 (ndt_service.py) | T003 (ndt.py + main.py) | T004 (Layout.tsx + App.tsx) | T005 (api.ts)
```

**Phase 3** (backend then frontend):
```
T006 → T007 → T008 (service, sequential - same file)
T009 (router, after T006-T008)
T010 → T011 (frontend, after T009)
```

**Phase 4 + Phase 5** (independent stories, can run in parallel after US1):
```
US2: T012 → T013 → T014
US3: T015 → T016
(These two streams can run concurrently)
```

**Phase 6** (both tasks target different files):
```
T017 (NDTTesting.tsx) | T018 (test_ndt_service.py)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001) — ~5 minutes
2. Complete Phase 2: Foundational (T002-T005) — parallel
3. Complete Phase 3: User Story 1 (T006-T011) — core ACP test
4. **STOP and VALIDATE**: Run a simulation, navigate to NDT Testing, run the ACP test, verify pass/fail
5. Deploy/demo if ready — feature delivers compliance value at this point

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. User Story 1 → Single-scenario ACP test works → **MVP deployed**
3. User Story 2 → Detailed breakdown + drill-down → Enhanced analytics
4. User Story 3 → Multi-scenario comparison → Full plan design analysis tool
5. Polish → Tests + error handling → Production-hardened

### Parallel Strategy (US2 + US3 after US1)

After User Story 1 is complete:
- Stream A: User Story 2 (T012-T014) — backend employee detail + frontend breakdown
- Stream B: User Story 3 (T015-T016) — frontend multi-scenario comparison
- These can run concurrently since US2 modifies backend + frontend detail view while US3 modifies frontend selection/layout

---

## Notes

- All NDT computation is read-only analytics — no writes to simulation database
- No new dbt models needed — avoids circular int→fct dependency
- ACP formula uses employer match only (after-tax not modeled yet)
- IRS test uses full formula: alternative = lesser of (NHCE x 2, NHCE + 2%)
- Test population: all plan-eligible employees including non-enrolled (ACP = 0%)
- HCE determination: prior-year compensation > IRS threshold; first-year fallback to current-year comp
