# Tasks: Match Census for Opt-Out Rate Configuration

**Input**: Design documents from `/specs/085-optout-match-census/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api-contract.md ✅

**Tests**: Included — constitution requires test-first development (Red-Green-Refactor).

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Skeleton Files)

**Purpose**: Create new empty files so test frameworks and imports resolve before any implementation.

- [x] T001 Create empty `planalign_api/models/opt_out.py` with module docstring placeholder
- [x] T002 [P] Create empty `planalign_api/services/opt_out_service.py` with module docstring placeholder
- [x] T003 [P] Create empty `tests/test_opt_out_analysis.py` with module docstring and pytest import

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models and SQL column allowlist that every subsequent task depends on.

**⚠️ CRITICAL**: No service, endpoint, or frontend work can begin until T004 and T005 are complete.

- [x] T004 Add `CENSUS_DEFERRAL_COLUMNS = frozenset({"employee_deferral_rate", "deferral_rate"})` after `CENSUS_STATUS_COLUMNS` and include it in `ALL_CENSUS_COLUMNS` union in `planalign_api/services/sql_security.py`
- [x] T005 [P] Implement `OptOutRateAnalysisRequest` (fields: `file_path: str`, `lookback_years: int = Field(default=3, ge=1, le=50)`) and `OptOutRateAnalysisResult` (all fields from data-model.md) Pydantic v2 models in `planalign_api/models/opt_out.py`

**Checkpoint**: Models importable and SQL security extended — service and endpoint work can begin.

---

## Phase 3: User Story 1 - Derive Opt-Out Rate from Census (Priority: P1) 🎯 MVP

**Goal**: Analyst clicks "Match Census" in the Opt-Out Assumptions panel, sees a preview with eligible count, non-participant count, and suggested rate (using default 3-year lookback), then applies the rate to the `dcOptOutRateTarget` field or dismisses the preview.

**Independent Test**: Open DC Plan config in PlanAlign Studio with a census file uploaded. Click "Match Census". Verify the preview panel appears showing numeric stats (eligible_count, non_participant_count, suggested_rate as %). Click "Apply". Verify the Target Opt-Out Rate field updates to the suggested value. Reload scenario — verify value persists.

### Tests for User Story 1 (write first — verify they FAIL before implementing service)

- [x] T006 [US1] Write unit test `test_enrolled_excluded_from_non_participant_count`: create in-memory DuckDB CSV fixture with 3 enrolled employees (deferral_rate>0) and 2 non-enrolled (deferral_rate=0); assert non_participant_count=2, eligible_count=5, suggested_rate≈0.4 in `tests/test_opt_out_analysis.py`
- [x] T007 [P] [US1] Write unit test `test_null_deferral_treated_as_non_participant`: fixture with 1 employee where deferral_rate IS NULL; assert non_participant_count=1 in `tests/test_opt_out_analysis.py`
- [x] T008 [P] [US1] Write integration test `test_analyze_opt_out_rate_endpoint_success`: use FastAPI TestClient to POST to `/api/workspaces/{workspace_id}/analyze-opt-out-rate` with valid CSV fixture and assert HTTP 200 with correct `OptOutRateAnalysisResult` shape in `tests/test_opt_out_analysis.py`

### Implementation for User Story 1

- [x] T009 [US1] Implement `OptOutAnalysisService` class with `analyze_opt_out_rate(workspace_id, file_path, lookback_years)` method in `planalign_api/services/opt_out_service.py`: resolve file path, load CSV/Parquet into DuckDB in-memory, detect hire_date column from `CENSUS_HIRE_DATE_COLUMNS`, detect deferral column from `CENSUS_DEFERRAL_COLUMNS`, compute lookback cutoff from `MAX(hire_date) - lookback_years*365`, count eligible_count/non_participant_count/excluded_null_tenure, compute suggested_rate, return `OptOutRateAnalysisResult`
- [x] T010 [US1] Add `POST /{workspace_id}/analyze-opt-out-rate` endpoint to `planalign_api/routers/bands.py`: import `OptOutRateAnalysisRequest`/`OptOutRateAnalysisResult` from `..models.opt_out`, import `OptOutAnalysisService` from `..services.opt_out_service`, add `get_opt_out_service()` dependency, add async handler with `ValueError`→400 and `Exception`→500 error handling (mirror `analyze_turnover` pattern at line ~257)
- [x] T011 [P] [US1] Add `OptOutRateAnalysisRequest` and `OptOutRateAnalysisResult` TypeScript interfaces and `analyzeOptOutRate(workspaceId, request)` async function to `planalign_studio/services/api.ts` (place after `analyzeTurnoverRates` at line ~1136, use same `handleResponse<T>` pattern)
- [x] T012 [US1] Add `analyzing`, `analysis` (`OptOutRateAnalysisResult | null`), `analysisError` state variables and `handleMatchCensus` async function (mirrors `TurnoverSection.tsx` pattern) to `planalign_studio/components/config/DCPlanSection.tsx`; add imports: `useState` from react, `BarChart3` from lucide-react, `analyzeOptOutRate`/`OptOutRateAnalysisResult` from `../../services/api`
- [x] T013 [US1] Add "Match Census" button (with `BarChart3` icon, disabled when `analyzing || !formData.censusDataPath`) and inline preview panel (shows `eligible_count`, `non_participant_count`, `suggested_rate` formatted as %; "Apply X%" button that calls `handleApply`; "Dismiss" button that clears `analysis`) to the Opt-Out Assumptions section in `planalign_studio/components/config/DCPlanSection.tsx`; `handleApply` must update `formData.dcOptOutRateTarget` via `setFormData` and clear `analysis`

**Checkpoint**: US1 fully functional — button visible, preview appears with stats, Apply updates the rate field, Dismiss cancels. Run `pytest tests/test_opt_out_analysis.py -v` to confirm T006–T008 pass.

---

## Phase 4: User Story 2 - Adjust Lookback and Re-preview (Priority: P2)

**Goal**: Within the open preview panel, the analyst changes the tenure lookback years value and the preview statistics (eligible_count, non_participant_count, suggested_rate) update automatically to reflect the new window.

**Independent Test**: Open the "Match Census" preview. Change the lookback input from 3 to 1. Verify the stats update without clicking any additional button. Change to 5 — verify stats update again. All changes reflect only employees within the new window.

### Tests for User Story 2 (write first — verify they FAIL before implementation changes)

- [x] T014 [US2] Write unit test `test_lookback_filter_excludes_older_employees`: fixture with 5 employees hired 4 years ago and 3 hired 1 year ago (all non-enrolled); with lookback_years=2, assert eligible_count=3; with lookback_years=5, assert eligible_count=8 in `tests/test_opt_out_analysis.py`
- [x] T015 [P] [US2] Write unit test `test_lookback_anchor_uses_max_hire_date_not_today`: fixture with all employees hired in 2019-2020 (old census); assert lookback_years=3 filters relative to 2020 max hire date, not current year — eligible_count > 0 in `tests/test_opt_out_analysis.py`

### Implementation for User Story 2

- [x] T016 [US2] Add `lookbackYears` state variable (default 3) and numeric stepper input (min=1, step=1, label "Lookback (years)") to the preview panel in `planalign_studio/components/config/DCPlanSection.tsx`; the input should be visible only when the preview panel is shown (`analysis !== null`)
- [x] T017 [US2] Wire `lookbackYears` input `onChange` to re-call `handleMatchCensus` with the new value (debounce 500ms via `useEffect` on `lookbackYears` dependency when `analysis !== null`) in `planalign_studio/components/config/DCPlanSection.tsx`

**Checkpoint**: US1 + US2 both work — preview refreshes on lookback change. Run `pytest tests/test_opt_out_analysis.py::test_lookback_filter_excludes_older_employees tests/test_opt_out_analysis.py::test_lookback_anchor_uses_max_hire_date_not_today -v`.

---

## Phase 5: User Story 3 - No Census File Handling (Priority: P3)

**Goal**: When the analyst clicks "Match Census" with no census file uploaded, a clear explanatory message appears instead of a silent failure or unhandled error. When the census file exists but lacks required columns, the system returns an actionable error.

**Independent Test**: In a scenario with no census file, click "Match Census". Verify a message appears explaining the census file requirement. No spinner, no crash. In a scenario with a census file missing the hire_date column, the preview shows a clear column-not-found error.

### Tests for User Story 3 (write first — verify they FAIL before implementation changes)

- [x] T018 [US3] Write unit test `test_missing_file_raises_value_error`: call `analyze_opt_out_rate` with a non-existent file path; assert `ValueError` is raised with message containing "not found" in `tests/test_opt_out_analysis.py`
- [x] T019 [P] [US3] Write unit test `test_missing_hire_date_column_raises_value_error`: fixture CSV with no hire_date variant; assert `ValueError` raised with message listing expected column names in `tests/test_opt_out_analysis.py`
- [x] T020 [P] [US3] Write unit test `test_missing_deferral_column_raises_value_error`: fixture CSV with hire_date but no deferral_rate variant; assert `ValueError` raised with message listing expected column names in `tests/test_opt_out_analysis.py`
- [x] T021 [P] [US3] Write integration test `test_endpoint_returns_400_for_missing_file`: POST to endpoint with non-existent file_path; assert HTTP 400 with detail message in `tests/test_opt_out_analysis.py`

### Implementation for User Story 3

- [x] T022 [US3] Add guard at top of `handleMatchCensus` in `planalign_studio/components/config/DCPlanSection.tsx`: if `!formData.censusDataPath`, set `analysisError` to "Upload a census file first to use Match Census" and return early (no API call made)
- [x] T023 [P] [US3] Add disabled state and `title` tooltip to "Match Census" button in `planalign_studio/components/config/DCPlanSection.tsx`: when `!formData.censusDataPath`, button appears disabled with tooltip "Upload a census file first" (same pattern as `TurnoverSection.tsx` line 71-74)
- [x] T024 [US3] Add `ValueError` handling in `OptOutAnalysisService.analyze_opt_out_rate()` for missing hire_date column and missing deferral column in `planalign_api/services/opt_out_service.py`: raise `ValueError` with message "No hire date column found in census. Expected one of: hire_date, employee_hire_date, hiredate, start_date" and "No deferral rate column found in census. Expected one of: employee_deferral_rate, deferral_rate" respectively

**Checkpoint**: All three user stories work. Run full test suite: `pytest tests/test_opt_out_analysis.py -v && pytest -m fast` to confirm no regressions.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Defensive UX, low-confidence warnings, and excluded-record transparency.

- [x] T025 Add low-confidence warning display in preview panel when `analysis.eligible_count < 20`: show amber warning "Small sample — only N employees in window. Consider a longer lookback." in `planalign_studio/components/config/DCPlanSection.tsx`
- [x] T026 [P] Add `excluded_null_tenure` note in preview panel when `analysis.excluded_null_tenure > 0`: show "N employees excluded (missing hire date)" below the stats in `planalign_studio/components/config/DCPlanSection.tsx`
- [x] T027 [P] Write unit test `test_empty_lookback_window_returns_null_rate_with_message`: all employees older than lookback; assert `suggested_rate=None` and `message` is non-empty in `tests/test_opt_out_analysis.py`; add "No eligible employees in window" informative state to preview panel (no Apply button shown) in `planalign_studio/components/config/DCPlanSection.tsx`
- [x] T028 [P] Write unit test `test_null_hire_date_excluded_and_counted`: mix of employees with valid and NULL hire dates; assert `excluded_null_tenure` equals null-tenure count; add `pytest.mark.fast` markers to all unit tests in `tests/test_opt_out_analysis.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T002 and T003 can run in parallel with T001
- **Foundational (Phase 2)**: Depends on Phase 1 completion; T004 and T005 can run in parallel
- **US1 (Phase 3)**: Depends on Phase 2 — T006/T007/T008 and T011 can start in parallel with T009; T010 depends on T009; T012 depends on T011; T013 depends on T012
- **US2 (Phase 4)**: Depends on Phase 3; T014/T015 can run in parallel; T017 depends on T016
- **US3 (Phase 5)**: Depends on Phase 3; T018/T019/T020/T021 can run in parallel; T022/T023 can run in parallel; T024 can run in parallel with T022/T023
- **Polish (Phase 6)**: Depends on all user story phases; T025/T026/T027/T028 can all run in parallel

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 2 — no dependency on US2 or US3
- **US2 (P2)**: Starts after US1 service is implemented (T009) — US2 adds frontend-only lookback UX; backend service already handles arbitrary `lookback_years`
- **US3 (P3)**: Can start after T005 (models) and T009 (service skeleton) — error path tests and UI guard are independent

### Within Each User Story

1. Tests written first and confirmed FAILING
2. Service/models before endpoints
3. Endpoint before frontend API function
4. Frontend API function before UI component
5. Story complete and tested before moving to next

---

## Parallel Opportunities

### Phase 3 (US1) — can start these simultaneously after Phase 2:

```
Parallel group A (backend tests + service):
  T006: Unit test enrolled/non-enrolled detection
  T007: Unit test null deferral handling
  T009: Service implementation (after T006/T007 written and failing)

Parallel group B (frontend API):
  T011: TypeScript interface + analyzeOptOutRate function in api.ts
  T008: Integration test for endpoint (can be written before T010 is implemented)
```

### Phase 5 (US3) — can start these simultaneously:

```
Parallel group:
  T018: Missing file ValueError unit test
  T019: Missing hire_date column ValueError unit test
  T020: Missing deferral column ValueError unit test
  T021: Endpoint 400 integration test
  T022: Frontend guard in handleMatchCensus
  T023: Button disabled state + tooltip
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Create skeleton files
2. Complete Phase 2: Pydantic models + SQL security column (BLOCKS everything)
3. Complete Phase 3: US1 — full happy path (button → preview → apply)
4. **STOP and VALIDATE**: Manually test in PlanAlign Studio with a real census file
5. Run `pytest tests/test_opt_out_analysis.py -v` — all Phase 3 tests must pass

### Incremental Delivery

1. Phase 1 + 2 → Foundation ready
2. Phase 3 → US1 working → Demo: "Match Census gives you a data-backed opt-out rate"
3. Phase 4 → US2 working → Demo: "Change the lookback and the rate updates live"
4. Phase 5 → US3 working → Demo: "Handles missing census gracefully"
5. Phase 6 → Polish → Final release-ready state

---

## Notes

- All unit tests MUST be tagged `@pytest.mark.fast` for inclusion in the fast suite
- `validate_column_name_from_set()` MUST be called on any census column name before it appears in dynamic SQL
- Active employee detection uses case-insensitive matching: `UPPER(CAST(active AS VARCHAR)) IN ('ACTIVE', 'Y', '1', 'TRUE', 'YES')`; treat NULL active as active (permissive fallback)
- Lookback anchor is `MAX(hire_date)` in census — NOT `date.today()` (see research.md D-004)
- No dbt model changes required — this feature only reads raw census files in-memory
- The "Match Census" button and `Reset to Default` button coexist in the Opt-Out Assumptions header row (flex justify-between layout)
