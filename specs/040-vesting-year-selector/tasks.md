# Tasks: Vesting Year Selector

**Input**: Design documents from `/specs/040-vesting-year-selector/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Integration tests included for the new backend endpoint per Constitution Principle III (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `planalign_api/` (FastAPI routers, services, models)
- **Frontend**: `planalign_studio/` (React components, API client)
- **Tests**: `tests/integration/` (pytest integration tests)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Backend service method and response model needed by all user stories

- [x] T001 Add `ScenarioYearsResponse` Pydantic model with `years: List[int]` and `default_year: int` fields in `planalign_api/models/vesting.py`
- [x] T002 Add `get_available_years(workspace_id, scenario_id)` method to `VestingService` class that queries `SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year ASC` and returns `ScenarioYearsResponse` (or `None` if database not found) in `planalign_api/services/vesting_service.py`
- [x] T003 Add `GET /workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting/years` endpoint to vesting router that validates workspace/scenario existence (reusing pattern from `analyze_vesting`), calls `vesting_service.get_available_years()`, and returns `ScenarioYearsResponse` or 404 in `planalign_api/routers/vesting.py`

**Checkpoint**: Backend years endpoint functional — can be tested with `curl`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Frontend API client function needed before UI work

- [x] T004 Add `ScenarioYearsResponse` interface (`years: number[], default_year: number`) and `getScenarioYears(workspaceId, scenarioId)` async function (following `analyzeVesting` fetch pattern) in `planalign_studio/services/api.ts`

**Checkpoint**: Frontend can call the years endpoint — ready for UI integration

---

## Phase 3: User Story 1 — Select Analysis Year Before Running Vesting Analysis (Priority: P1) MVP

**Goal**: Add a year selector dropdown to the Vesting Analysis page that lets users choose which simulation year to analyze, with the selected year passed to the existing analysis API.

**Independent Test**: Select a year from the dropdown, click "Analyze", and verify results are specific to that year.

### Tests for User Story 1

- [x] T005 [P] [US1] Add integration test `test_get_vesting_years_valid_scenario` that verifies GET years endpoint returns sorted years list and correct `default_year` for a scenario with simulation data in `tests/integration/test_vesting_api.py`
- [x] T006 [P] [US1] Add integration test `test_get_vesting_years_missing_scenario` that verifies GET years endpoint returns 404 when scenario does not exist in `tests/integration/test_vesting_api.py`

### Implementation for User Story 1

- [x] T007 [US1] Add state variables `selectedYear: number | undefined`, `availableYears: number[]`, and `loadingYears: boolean` to `VestingAnalysis` component in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T008 [US1] Add `useEffect` that calls `getScenarioYears(selectedWorkspaceId, selectedScenarioId)` when `selectedScenarioId` changes, populates `availableYears`, and sets `selectedYear` to `default_year` from the response in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T009 [US1] Add year selector dropdown in a new row between the 4-column grid and the Analyze button, styled to match existing selectors (same `appearance-none`, border, focus ring classes), showing `availableYears` options with `selectedYear` as value, disabled when `loadingYears` or no scenario selected, in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T010 [US1] Update `handleAnalyze` to include `simulation_year: selectedYear` in the `VestingAnalysisRequest` object passed to `analyzeVesting()` in `planalign_studio/components/VestingAnalysis.tsx`

**Checkpoint**: Year selector visible, populated from API, selected year sent to analysis endpoint. Full P1 story functional.

---

## Phase 4: User Story 2 — Available Years Populated from Scenario Data (Priority: P2)

**Goal**: Ensure year selector only shows valid years from actual simulation data and handles scenario changes correctly.

**Independent Test**: Switch between scenarios with different year ranges and verify dropdown options match each scenario's actual data.

### Implementation for User Story 2

- [x] T011 [US2] Update scenario change handler (`setSelectedScenarioId` onChange) to reset `availableYears` to `[]`, `selectedYear` to `undefined`, and `analysisResult` to `null` when scenario changes, so the `useEffect` from T008 fetches fresh years in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T012 [US2] Handle single-year scenario edge case: when `availableYears.length === 1`, auto-select the single year and keep the dropdown visible but effectively read-only in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T013 [P] [US2] Add integration test `test_get_vesting_years_no_simulation_data` that verifies GET years endpoint returns 404 when scenario database has no `fct_workforce_snapshot` data in `tests/integration/test_vesting_api.py`

**Checkpoint**: Year selector correctly reflects each scenario's actual simulation years. Switching scenarios resets state cleanly.

---

## Phase 5: User Story 3 — Analysis Year Displayed in Results (Priority: P3)

**Goal**: Ensure the results banner clearly shows which year was analyzed, matching the user's selection.

**Independent Test**: Select different years, run analyses, and verify the year in the results banner matches the dropdown selection.

### Implementation for User Story 3

- [x] T014 [US3] Verify the existing results banner display at `analysisResult.summary.analysis_year` correctly reflects the selected year (the backend already returns `analysis_year` based on the request's `simulation_year` — this task confirms end-to-end correctness and makes no code changes unless the display needs updating) in `planalign_studio/components/VestingAnalysis.tsx`

**Checkpoint**: Results banner shows the user-selected year. All three user stories functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling and validation

- [x] T015 Update `canAnalyze` guard condition to also require `selectedYear` is defined (ensuring user cannot click Analyze without a year selected) in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T016 Add `Calendar` icon import from `lucide-react` and display it next to the year selector label for visual consistency with other selectors in `planalign_studio/components/VestingAnalysis.tsx`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately. T001 → T002 → T003 (sequential: model → service → router)
- **Foundational (Phase 2)**: Depends on Phase 1 (needs endpoint URL). T004 after T003.
- **User Story 1 (Phase 3)**: Depends on Phase 2. Tests T005-T006 can run in parallel. Implementation T007-T010 sequential within component.
- **User Story 2 (Phase 4)**: Depends on Phase 3 (builds on year state from T007-T008). T011-T012 sequential, T013 parallel.
- **User Story 3 (Phase 5)**: Depends on Phase 3 (needs working analysis with year). T014 standalone.
- **Polish (Phase 6)**: Depends on all user stories complete. T015-T016 parallel.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependencies on other stories
- **User Story 2 (P2)**: Builds on US1's year state management but is independently testable
- **User Story 3 (P3)**: Requires US1's working analysis flow; verifies existing display behavior

### Parallel Opportunities

- T005 and T006 can run in parallel (separate test functions, same file)
- T015 and T016 can run in parallel (different concerns in same file)
- Backend (T001-T003) and frontend API client (T004) are near-sequential but T004 only needs the endpoint URL pattern, not a running server

---

## Parallel Example: User Story 1

```bash
# Launch tests in parallel:
Task: "Integration test for valid scenario years in tests/integration/test_vesting_api.py"
Task: "Integration test for missing scenario in tests/integration/test_vesting_api.py"

# Then implementation sequentially (all in same component file):
Task: "Add year state variables in VestingAnalysis.tsx"
Task: "Add useEffect for fetching years in VestingAnalysis.tsx"
Task: "Add year selector dropdown UI in VestingAnalysis.tsx"
Task: "Wire selectedYear into handleAnalyze in VestingAnalysis.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Backend endpoint (T001-T003)
2. Complete Phase 2: Frontend API client (T004)
3. Complete Phase 3: Year selector dropdown + wiring (T005-T010)
4. **STOP and VALIDATE**: Select a year, click Analyze, verify year-specific results
5. Deploy/demo if ready — users can now choose analysis year

### Incremental Delivery

1. Backend + API client → Foundation ready
2. Add US1 (year selector + analysis) → Test independently → **MVP delivered**
3. Add US2 (scenario change handling) → Test independently → Robust UX
4. Add US3 (results display verification) → Test independently → Confidence in display
5. Polish → Production-ready

---

## Notes

- [P] tasks = different files or independent concerns, no dependencies
- [Story] label maps task to specific user story for traceability
- Most implementation is in a single file (`VestingAnalysis.tsx`), so within-story tasks are sequential
- Backend endpoint (Phase 1) is the only net-new code; frontend is wiring existing capabilities
- The backend `VestingAnalysisRequest` and `analyzeVesting` service already support `simulation_year` — no changes needed there
- Commit after each phase checkpoint for clean git history
