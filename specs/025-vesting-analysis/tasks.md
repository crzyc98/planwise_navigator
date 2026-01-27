# Tasks: Vesting Analysis

**Input**: Design documents from `/specs/025-vesting-analysis/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included as the spec mentions backend unit tests and integration tests in the implementation checklist.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `planalign_api/` (FastAPI + Pydantic v2)
- **Frontend**: `planalign_studio/` (React + TypeScript)
- **Tests**: `tests/unit/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create base file structure and verify prerequisites

- [x] T001 Verify `fct_workforce_snapshot` contains required columns (employee_hire_date, current_tenure, tenure_band, termination_date, employment_status, total_employer_contributions, annual_hours_worked)
- [x] T002 [P] Create empty `planalign_api/models/vesting.py`
- [x] T003 [P] Create empty `planalign_api/services/vesting_service.py`
- [x] T004 [P] Create empty `planalign_api/routers/vesting.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core Pydantic models and vesting calculation logic that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Pydantic Models

- [x] T005 [P] Implement `VestingScheduleType` enum in `planalign_api/models/vesting.py` with values: IMMEDIATE, CLIFF_2_YEAR, CLIFF_3_YEAR, CLIFF_4_YEAR, QACA_2_YEAR, GRADED_3_YEAR, GRADED_4_YEAR, GRADED_5_YEAR
- [x] T006 [P] Implement `VestingScheduleInfo` model in `planalign_api/models/vesting.py` (schedule_type, name, description, percentages)
- [x] T007 [P] Implement `VestingScheduleConfig` model in `planalign_api/models/vesting.py` (schedule_type, name, require_hours_credit, hours_threshold)
- [x] T008 [P] Implement `VestingAnalysisRequest` model in `planalign_api/models/vesting.py` (current_schedule, proposed_schedule, simulation_year)
- [x] T009 [P] Implement `EmployeeVestingDetail` model in `planalign_api/models/vesting.py` (all 15 fields per data-model.md)
- [x] T010 [P] Implement `TenureBandSummary` model in `planalign_api/models/vesting.py` (tenure_band, employee_count, contributions, forfeitures)
- [x] T011 [P] Implement `VestingAnalysisSummary` model in `planalign_api/models/vesting.py` (analysis_year, totals, variance)
- [x] T012 [P] Implement `VestingAnalysisResponse` model in `planalign_api/models/vesting.py` (scenario info, summary, by_tenure_band, employee_details)
- [x] T013 [P] Implement `VestingScheduleListResponse` model in `planalign_api/models/vesting.py`

### Vesting Schedule Constants

- [x] T014 Define `VESTING_SCHEDULES` dictionary in `planalign_api/services/vesting_service.py` mapping VestingScheduleType to year→percentage dicts
- [x] T015 Define `SCHEDULE_INFO` dictionary in `planalign_api/services/vesting_service.py` with display names and descriptions per data-model.md

### Core Calculation Functions

- [x] T016 Implement `get_vesting_percentage(schedule_type, tenure_years, annual_hours, require_hours, hours_threshold)` in `planalign_api/services/vesting_service.py`
- [x] T017 Implement `calculate_forfeiture(total_contributions, vesting_pct)` in `planalign_api/services/vesting_service.py`
- [x] T018 Implement `get_schedule_list()` static method in `planalign_api/services/vesting_service.py` returning VestingScheduleListResponse

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Compare Vesting Schedules (Priority: P1) 🎯 MVP

**Goal**: Enable plan sponsors to compare two vesting schedules and see forfeiture differences for terminated employees

**Independent Test**: Select two schedules, run analysis, verify summary shows total forfeitures under each schedule and variance

### Tests for User Story 1

- [x] T019 [P] [US1] Unit test for `get_vesting_percentage()` in `tests/unit/test_vesting_service.py` covering all 8 schedule types
- [x] T020 [P] [US1] Unit test for `calculate_forfeiture()` in `tests/unit/test_vesting_service.py` with edge cases (0%, 100%, partial)
- [x] T021 [P] [US1] Unit test for tenure truncation (float to int) in `tests/unit/test_vesting_service.py`
- [x] T022 [P] [US1] Integration test for `POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting` in `tests/integration/test_vesting_api.py`

### Backend Implementation for User Story 1

- [x] T023 [US1] Implement `VestingService.__init__()` with WorkspaceStorage and DatabasePathResolver in `planalign_api/services/vesting_service.py`
- [x] T024 [US1] Implement `_get_final_year(conn)` private method to find max simulation_year in `planalign_api/services/vesting_service.py`
- [x] T025 [US1] Implement `_get_terminated_employees(conn, year)` private method with SQL query per research.md in `planalign_api/services/vesting_service.py`
- [x] T026 [US1] Implement `_calculate_employee_details(employees, current_schedule, proposed_schedule)` returning List[EmployeeVestingDetail] in `planalign_api/services/vesting_service.py`
- [x] T027 [US1] Implement `_build_summary(details, year)` returning VestingAnalysisSummary in `planalign_api/services/vesting_service.py`
- [x] T028 [US1] Implement `_aggregate_by_tenure_band(details)` returning List[TenureBandSummary] in `planalign_api/services/vesting_service.py`
- [x] T029 [US1] Implement `analyze_vesting(workspace_id, scenario_id, scenario_name, request)` main method in `planalign_api/services/vesting_service.py`
- [x] T030 [US1] Implement `GET /api/vesting/schedules` endpoint in `planalign_api/routers/vesting.py`
- [x] T031 [US1] Implement `POST /api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting` endpoint in `planalign_api/routers/vesting.py`
- [x] T032 [US1] Create `get_vesting_service` dependency function in `planalign_api/routers/vesting.py`
- [x] T033 [US1] Register vesting router in `planalign_api/main.py`

### Frontend Implementation for User Story 1

- [x] T034 [P] [US1] Add TypeScript types to `planalign_studio/services/api.ts`: VestingScheduleType, VestingScheduleInfo, VestingScheduleConfig, VestingAnalysisRequest, VestingAnalysisSummary, VestingAnalysisResponse
- [x] T035 [P] [US1] Add `listVestingSchedules()` API function in `planalign_studio/services/api.ts`
- [x] T036 [P] [US1] Add `analyzeVesting(workspaceId, scenarioId, request)` API function in `planalign_studio/services/api.ts`
- [x] T037 [US1] Create `VestingAnalysis.tsx` component in `planalign_studio/components/` with schedule selector dropdowns
- [x] T038 [US1] Add "Analyze" button and loading state to `VestingAnalysis.tsx`
- [x] T039 [US1] Add summary KPI cards (total forfeitures current, proposed, variance) to `VestingAnalysis.tsx`
- [x] T040 [US1] Add bar chart (forfeitures by tenure band) using Recharts in `VestingAnalysis.tsx`

**Checkpoint**: US1 complete - users can select two schedules and see summary forfeitures with tenure band breakdown

---

## Phase 4: User Story 2 - View Employee-Level Details (Priority: P2)

**Goal**: Provide drill-down capability into individual employee vesting calculations

**Independent Test**: Run analysis and view sortable data table with per-employee forfeiture amounts

### Tests for User Story 2

- [x] T041 [P] [US2] Unit test verifying `employee_details` array in response contains all required fields in `tests/unit/test_vesting_service.py`
- [x] T042 [P] [US2] Integration test verifying employee_details returns correct count matching terminated employees in `tests/integration/test_vesting_api.py`

### Frontend Implementation for User Story 2

- [x] T043 [P] [US2] Add TypeScript types for EmployeeVestingDetail and TenureBandSummary in `planalign_studio/services/api.ts`
- [x] T044 [US2] Add employee details data table component to `VestingAnalysis.tsx` with columns: employee_id, tenure_years, total_employer_contributions, current_vesting_pct, current_forfeiture, proposed_vesting_pct, proposed_forfeiture, forfeiture_variance
- [x] T045 [US2] Implement column sorting for employee details table in `VestingAnalysis.tsx`
- [x] T046 [US2] Add formatting for currency amounts ($X,XXX.XX) and percentages (XX.X%) in table cells

**Checkpoint**: US2 complete - users can drill down to individual employee vesting calculations with sorting

---

## Phase 5: User Story 3 - Configure Hours-Based Vesting Credit (Priority: P3)

**Goal**: Support hours-of-service requirements that reduce vesting credit for employees below threshold

**Independent Test**: Enable hours-based vesting, verify employee with <1000 hours loses one year of vesting credit

### Tests for User Story 3

- [x] T047 [P] [US3] Unit test for hours-based credit reduction in `get_vesting_percentage()` in `tests/unit/test_vesting_service.py`
- [x] T048 [P] [US3] Unit test verifying hours threshold of 500 vs 1000 produces different results in `tests/unit/test_vesting_service.py`

### Frontend Implementation for User Story 3

- [x] T049 [US3] Add "Require Hours Credit" toggle to schedule config in `VestingAnalysis.tsx`
- [x] T050 [US3] Add "Hours Threshold" input field (default 1000, range 0-2080) in `VestingAnalysis.tsx`
- [x] T051 [US3] Update request payload to include require_hours_credit and hours_threshold for each schedule

**Checkpoint**: US3 complete - users can model hours-based vesting requirements

---

## Phase 6: User Story 4 - Navigate to Vesting Analysis (Priority: P4)

**Goal**: Make the Vesting Analysis feature discoverable in PlanAlign Studio navigation

**Independent Test**: Open PlanAlign Studio, find Vesting link in navigation, navigate to page

### Frontend Implementation for User Story 4

- [x] T052 [P] [US4] Add route `<Route path="analytics/vesting" element={<VestingAnalysis />} />` in `planalign_studio/App.tsx`
- [x] T053 [US4] Add navigation link with Scale icon to Vesting Analysis in `planalign_studio/components/Layout.tsx`

**Checkpoint**: US4 complete - users can navigate to Vesting Analysis from main menu

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, edge cases, and validation

- [x] T054 [P] Add error state display when scenario has no terminated employees in `VestingAnalysis.tsx`
- [x] T055 [P] Add error state display when scenario simulation not complete in `VestingAnalysis.tsx`
- [x] T056 [P] Add loading spinner during API calls in `VestingAnalysis.tsx`
- [x] T057 Verify forfeiture totals match within $0.01 precision (SC-002)
- [x] T058 Verify tenure band totals sum to overall total (SC-005)
- [x] T059 Run quickstart.md validation commands

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories can proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3 → P4)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 - No dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 (employee_details included in response from US1 backend)
- **User Story 3 (P3)**: Can start after Phase 2 - Hours credit logic is independent
- **User Story 4 (P4)**: Depends on US1 (needs VestingAnalysis component to exist)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Services before routers
- Backend before frontend (API must exist for frontend to call)
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks (T002-T004) can run in parallel
- All Pydantic model tasks (T005-T013) can run in parallel
- All US1 tests (T019-T022) can run in parallel
- US1 frontend types (T034-T036) can run in parallel
- US2 tests (T041-T042) can run in parallel
- US3 tests (T047-T048) can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test schedule comparison end-to-end
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test → Deploy/Demo (MVP - core comparison)
3. Add User Story 2 → Test → Deploy/Demo (employee drill-down)
4. Add User Story 3 → Test → Deploy/Demo (hours credit)
5. Add User Story 4 → Test → Deploy/Demo (navigation)

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (backend)
   - Developer B: User Story 1 (frontend) + User Story 4
   - Developer C: User Story 3 (hours credit)
3. User Story 2 starts once US1 backend is complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Backend tests use `tests/unit/` and `tests/integration/`
- Follow existing patterns from `AnalyticsService` and `DCPlanAnalytics.tsx`
- All monetary calculations use Decimal with $0.01 precision
- Vesting percentage calculations use truncated whole years of tenure
