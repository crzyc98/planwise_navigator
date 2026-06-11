# Tasks: scheduled_hours_per_week + Part-Time Eligibility Fix (#093)

**Input**: Design documents from `/specs/093-part-time-scheduled-hours/`
**Branch**: `093-part-time-scheduled-hours` | **GitHub Issue**: #282

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Exact file paths in all descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm current file state and establish the branch baseline

- [X] T001 Verify `dbt/models/staging/stg_census_data.sql` schema scaffold pattern (UNION ALL BY NAME structure) to confirm insertion point for `scheduled_hours_per_week`
- [X] T002 [P] Verify `planalign_api/services/sql_security.py` frozenset structure to confirm insertion point for new alias group

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add `scheduled_hours_per_week` to the census/staging pipeline — required by all downstream phases

**⚠️ CRITICAL**: All three eligibility + hiring phases depend on this column being available in staging

- [X] T003 Add `CENSUS_SCHEDULED_HOURS_COLUMNS` frozenset (`"scheduled_hours_per_week"`, `"hours_per_week"`, `"scheduled_hours"`, `"weekly_hours"`) to `planalign_api/services/sql_security.py` and union it into `ALL_CENSUS_COLUMNS`
- [X] T004 Add nullable `scheduled_hours_per_week DECIMAL(5,2)` column to the schema scaffold in `dbt/models/staging/stg_census_data.sql` (default `NULL` for backward compatibility)
- [X] T005 Document `scheduled_hours_per_week` in `dbt/models/staging/schema.yml` with description and `accepted_range` test (min: 1, max: 40)
- [X] T006 Add `part_time_new_hire_pct: float = Field(default=0.0, ge=0, le=1)` to `WorkforceSettings` in `planalign_orchestrator/config/workforce.py`

**Checkpoint**: `stg_census_data` now exposes `scheduled_hours_per_week`; config param exists. Downstream phases can begin.

---

## Phase 3: User Story 1 — Fix Eligibility Hours Formula (Priority: P1) 🎯 MVP

**Goal**: Part-time employees with a `scheduled_hours_per_week` value are credited the correct annual hours instead of 2080, making eligibility determinations accurate.

**Independent Test**:
```bash
cd dbt && dbt run --select stg_census_data int_employer_eligibility int_eligibility_computation_period --vars "simulation_year: 2025" --threads 1
# Query: SELECT employee_id, scheduled_hours_per_week, annual_hours_worked FROM fct_workforce_snapshot WHERE simulation_year = 2025 LIMIT 20
# Employee with scheduled_hours_per_week = 20 employed full year → annual_hours_worked ≈ 1040
# Employee with scheduled_hours_per_week = NULL employed full year → annual_hours_worked = 2080
```

### Implementation for User Story 1

- [X] T007 [US1] Replace all hardcoded `2080.0` / `2080` constants in the annual hours calculation block (lines ~271–300) of `dbt/models/intermediate/int_employer_eligibility.sql` with `COALESCE(scheduled_hours_per_week, 40.0) * 52.0` — join alias for `scheduled_hours_per_week` must come from the staging CTE (verify alias at read time)
- [X] T008 [US1] Apply the same `COALESCE(scheduled_hours_per_week, 40.0) * 52.0` replacement for all `2080.0` / `2080` occurrences in `dbt/models/intermediate/int_eligibility_computation_period.sql` (IECP year1_hours, year2_hours, plan_year_hours formulas ~lines 189–255)
- [X] T009 [US1] Add `scheduled_hours_per_week` to the final SELECT of `dbt/models/marts/fct_workforce_snapshot.sql` (place adjacent to `annual_hours_worked`)
- [X] T010 [US1] Write unit test `tests/unit/test_part_time_hours_formulas.py` (combined with T014) covering: (a) NULL → 2080 hours full year, (b) 20 hrs/wk → ~1040 hours full year, (c) 20 hrs/wk + partial year proration

**Checkpoint**: User Story 1 complete. `fct_workforce_snapshot` has correct `annual_hours_worked` for part-time census employees. Run the independent test above to verify.

---

## Phase 4: User Story 2 — Part-Time New Hire Assignment (Priority: P2)

**Goal**: Simulation-generated new hires can be assigned a part-time schedule via `part_time_new_hire_pct` config, producing correct eligibility hours in subsequent years.

**Independent Test**:
```bash
# Set part_time_new_hire_pct: 0.2 in simulation config, run:
cd dbt && dbt run --select int_hiring_events --vars "simulation_year: 2025" --threads 1
# Query: SELECT COUNT(*), AVG(CASE WHEN scheduled_hours_per_week = 20 THEN 1.0 ELSE 0 END) AS pt_pct FROM int_hiring_events WHERE simulation_year = 2025
# ~20% of new hires should have scheduled_hours_per_week = 20, rest NULL
```

### Implementation for User Story 2

- [X] T011 [US2] Add part-time assignment CTE `hire_with_part_time` to `dbt/models/intermediate/events/int_hiring_events.sql` after the `hire_with_age` CTE using the deterministic hash pattern: `ABS(MOD(HASH(CONCAT(CAST(hire_sequence_num AS VARCHAR), '_pt_', CAST({{ simulation_year }} AS VARCHAR)))::DOUBLE, 1000000.0)) / 1000000.0 < {{ var('part_time_new_hire_pct', 0.0) }}` → assign `scheduled_hours_per_week = 20.0`, else `NULL`
- [X] T012 [US2] Include `scheduled_hours_per_week` in the final SELECT of `dbt/models/intermediate/events/int_hiring_events.sql`
- [X] T013 [US2] Add `scheduled_hours_per_week` to the `previous_year_snapshot` CTE SELECT in `dbt/models/intermediate/int_workforce_previous_year.sql` (sourced from `fws.scheduled_hours_per_week`)
- [X] T014 [US2] Write unit test `tests/unit/test_part_time_hours_formulas.py` (combined with T010) covering: (a) `part_time_new_hire_pct = 0.0` → no part-time hires, (b) `part_time_new_hire_pct = 0.2` → ~20% of hires get 20 hrs/wk, (c) determinism — same seed + year → same assignment

**Checkpoint**: User Story 2 complete. New hires carry `scheduled_hours_per_week` forward into subsequent simulation years.

---

## Phase 5: User Story 3 — `/analyze-part-time-pct` Magic Button (Priority: P2)

**Goal**: A "Match Census" button in the UI auto-populates `part_time_new_hire_pct` by analyzing the uploaded census file, and is disabled when the census lacks a `scheduled_hours_per_week` column.

**Independent Test**:
```bash
# With census containing scheduled_hours_per_week:
curl -X POST http://localhost:8000/api/workspaces/{id}/analyze-part-time-pct \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/census.parquet"}'
# Expected: { "column_present": true, "headcount": N, "part_time_count": M, "part_time_pct": 0.XX }

# With census lacking the column:
# Expected: { "column_present": false, "headcount": N, "part_time_count": 0, "part_time_pct": 0.0 }
```

### Implementation for User Story 3

- [X] T015 [P] [US3] Add `PartTimePctResponse` Pydantic model to `planalign_api/models/files.py`: fields `column_present: bool`, `headcount: int`, `part_time_count: int`, `part_time_pct: float`
- [X] T016 [US3] Add `analyze_part_time_pct(workspace_id, file_path) -> PartTimePctResponse` method to the file service in `planalign_api/services/` (read census parquet, check for column, count employees where `scheduled_hours_per_week * 52 < 1000`)
- [X] T017 [US3] Add `POST /{workspace_id}/analyze-part-time-pct` endpoint to `planalign_api/routers/files.py` following the same pattern as the existing `analyze-age-distribution` endpoint (lines 243–269): accepts `FileValidationRequest`, delegates to service, returns `PartTimePctResponse`
- [X] T018 [US3] Write unit test `tests/unit/test_analyze_part_time_pct.py` covering: (a) census with column → correct `part_time_pct`, (b) census without column → `column_present: false`, (c) empty census → `part_time_pct = 0.0`

**Checkpoint**: API endpoint functional. Magic button can be verified via `curl` before frontend is wired.

---

## Phase 6: User Story 4 — Frontend UI (Priority: P3)

**Goal**: The New Hire Demographics panel has a `Part-Time New Hire %` input and a "Match Census" button that calls the endpoint and auto-populates the field.

**Independent Test**: Launch `planalign studio`, open a workspace with a census file, navigate to New Hire Demographics — the part-time % input is visible, the Match Census button populates it when the census has `scheduled_hours_per_week`, and the button is disabled with a tooltip when the census lacks the column.

### Implementation for User Story 4

- [X] T019 [P] [US4] Add `partTimeNewHirePct: number` field to `FormData` interface in `planalign_studio/src/types.ts` (alongside existing new hire fields)
- [X] T020 [P] [US4] Add `analyzePartTimePct(workspaceId: string, filePath: string): Promise<PartTimePctResponse>` function to the API service file in `planalign_studio/src/services/` (mirrors existing `analyzeAgeDistribution`)
- [X] T021 [US4] Add part-time section to `planalign_studio/src/components/NewHireSection.tsx`: number input (0–100%) bound to `partTimeNewHirePct`, "Match Census" button with loading/error/success states following the existing `matchCensusLoading` pattern, button disabled + tooltip when `column_present = false`

**Checkpoint**: Full feature complete. UI, API, dbt models, and config all wired end-to-end.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T022 [P] Run full dbt build to confirm no regressions: `cd dbt && dbt build --threads 1 --fail-fast`
- [X] T023 [P] Run fast pytest suite: `pytest -m fast`
- [X] T024 Run new unit tests: `pytest tests/unit/test_part_time_eligibility.py tests/unit/test_part_time_new_hire.py tests/unit/test_analyze_part_time_pct.py -v`
- [X] T025 Verify backward compatibility: run simulation with a census that has **no** `scheduled_hours_per_week` column and confirm `annual_hours_worked` values are unchanged from pre-feature behavior
- [X] T026 [P] Run `black .` to ensure formatting compliance

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS Phases 3, 4, 5**
- **Phase 3 (US1 — Eligibility Fix)**: Depends on Phase 2 (needs `scheduled_hours_per_week` in staging)
- **Phase 4 (US2 — New Hire Assignment)**: Depends on Phase 2; independent of Phase 3
- **Phase 5 (US3 — API Endpoint)**: Depends on Phase 2 for `PartTimePctResponse` model; independent of Phases 3 & 4
- **Phase 6 (US4 — Frontend)**: Depends on Phase 5 endpoint being complete
- **Phase 7 (Polish)**: Depends on all implementation phases

### Parallel Opportunities Per Phase

**Phase 2** (run together after T001/T002):
- T003, T004, T005, T006 all touch different files → fully parallel

**Phase 3** (US1):
- T007 and T008 touch different SQL files → parallel
- T009 (`fct_workforce_snapshot`) depends on T007/T008 being merged first
- T010 (tests) can be written first (TDD) or after

**Phases 3 + 4 + 5** (after Phase 2):
- All three user story phases can proceed in parallel

---

## Implementation Strategy

### MVP (User Stories 1 + 2 Only — no UI)

1. Phase 1: Setup
2. Phase 2: Foundational
3. Phase 3: Eligibility hours fix → validate with dbt query
4. Phase 4: Part-time new hire assignment → validate with dbt query
5. **STOP and VALIDATE**: dbt build passes, existing tests pass, part-time employees get ~1040 hours

### Full Feature

1. Complete MVP above
2. Phase 5: API endpoint
3. Phase 6: Frontend UI
4. Phase 7: Polish + full test run

---

## Notes

- All dbt commands must be run from the `/dbt` directory with `--threads 1`
- `COALESCE(NULL, 40.0) * 52.0 = 2080.0` — NULL rows are bit-for-bit identical to current behavior
- Verify the join alias for `scheduled_hours_per_week` in each eligibility model at read time before editing
- Commit after each phase checkpoint
