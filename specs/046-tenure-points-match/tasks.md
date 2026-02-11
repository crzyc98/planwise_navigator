# Tasks: Tenure-Based and Points-Based Employer Match Modes

**Input**: Design documents from `/specs/046-tenure-points-match/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included per spec requirements (FR validation + regression + smoke tests).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **dbt layer**: `dbt/macros/`, `dbt/models/intermediate/events/`, `dbt/dbt_project.yml`
- **Python config**: `planalign_orchestrator/config/workforce.py`, `planalign_orchestrator/config/export.py`
- **Config**: `config/simulation_config.yaml`
- **API/Studio**: `planalign_api/storage/workspace_storage.py`, `planalign_studio/src/components/`
- **Tests**: `tests/test_match_modes.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Understand existing code, verify prerequisites

- [ ] T001 Review existing match calculation model to understand branch structure and available columns in `dbt/models/intermediate/events/int_employee_match_calculations.sql`
- [ ] T002 [P] Review existing tiered match macro to understand pattern for new points-based macro in `dbt/macros/get_tiered_match_rate.sql`
- [ ] T003 [P] Review existing EmployerMatchSettings and export function in `planalign_orchestrator/config/workforce.py` and `planalign_orchestrator/config/export.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic tier models with validation + dbt variable defaults — blocks ALL user stories

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Add `TenureMatchTier` and `PointsMatchTier` Pydantic models with field validation in `planalign_orchestrator/config/workforce.py`
- [ ] T005 Add `validate_tier_contiguity()` shared validator function (gaps, overlaps, start-at-zero, valid ranges) in `planalign_orchestrator/config/workforce.py`
- [ ] T006 Extend `EmployerMatchSettings` to accept `tenure_match_tiers: list[TenureMatchTier]` and `points_match_tiers: list[PointsMatchTier]` with model-level validation in `planalign_orchestrator/config/workforce.py`
- [ ] T007 Add `tenure_match_tiers` and `points_match_tiers` variable defaults (empty arrays) in `dbt/dbt_project.yml`

**Checkpoint**: Pydantic models loaded and validated; dbt variables have safe defaults — user story implementation can now begin

---

## Phase 3: User Story 1 — Configure Points-Based Match Formula (Priority: P1) MVP

**Goal**: Enable `employer_match_status: 'points_based'` mode where match rates are determined by FLOOR(age) + FLOOR(tenure) point tiers

**Independent Test**: Configure a scenario with `points_based` mode, 4 point tiers, run a 3-year simulation, verify match amounts reflect each employee's age+tenure points tier and `applied_points` audit field is populated

### Implementation for User Story 1

- [ ] T008 [P] [US1] Create `get_points_based_match_rate(points_col, points_schedule, default_rate)` macro that generates a descending CASE expression for points-tier match rates in `dbt/macros/get_points_based_match_rate.sql`
- [ ] T009 [P] [US1] Create `get_points_based_max_deferral(points_col, points_schedule, default_pct)` macro that generates a descending CASE expression for points-tier max deferral in `dbt/macros/get_points_based_match_rate.sql`
- [ ] T010 [US1] Add `{% elif employer_match_status == 'points_based' %}` branch to match calculation model: compute `applied_points = FLOOR(ec.current_age) + years_of_service`, call points macros, apply formula `tier_rate x min(deferral%, tier_max_deferral_pct) x capped_compensation` in `dbt/models/intermediate/events/int_employee_match_calculations.sql`
- [ ] T011 [US1] Add `applied_points` output column (INTEGER, NULL for non-points modes) to the final SELECT of the match calculation model in `dbt/models/intermediate/events/int_employee_match_calculations.sql`
- [ ] T012 [US1] Extend `_export_employer_match_vars()` to export `points_match_tiers` with field name mapping (match_rate -> rate, percentage conversion) and extended `employer_match_status` values in `planalign_orchestrator/config/export.py`
- [ ] T013 [P] [US1] Add commented `points_based` configuration example with 4 tiers in `config/simulation_config.yaml`

**Checkpoint**: Points-based match mode is fully functional — run `planalign simulate 2025` with `employer_match_status: 'points_based'` and verify `applied_points` + correct match amounts

---

## Phase 4: User Story 2 — Configure Tenure-Based Match Formula (Priority: P2)

**Goal**: Enable `employer_match_status: 'tenure_based'` mode where match rates are determined by years-of-service tiers using the same formula as graded_by_service but with the new tier schema

**Independent Test**: Configure a scenario with `tenure_based` mode, 4 tenure tiers, run a simulation, verify match amounts match expected tenure-tier rates and `applied_years_of_service` is populated

### Implementation for User Story 2

- [ ] T014 [US2] Add `{% elif employer_match_status == 'tenure_based' %}` branch to match calculation model: reuse `get_tiered_match_rate()` and `get_tiered_match_max_deferral()` macros with `tenure_match_tiers` variable, populate `applied_years_of_service` in `dbt/models/intermediate/events/int_employee_match_calculations.sql`
- [ ] T015 [US2] Extend `_export_employer_match_vars()` to export `tenure_match_tiers` with field name mapping (match_rate -> rate, percentage conversion) in `planalign_orchestrator/config/export.py`
- [ ] T016 [P] [US2] Add commented `tenure_based` configuration example with 4 tiers in `config/simulation_config.yaml`

**Checkpoint**: Tenure-based match mode is fully functional — run `planalign simulate 2025` with `employer_match_status: 'tenure_based'` and verify correct match amounts

---

## Phase 5: User Story 3 — Validate Tier Configurations (Priority: P2)

**Goal**: Ensure all tier configurations (tenure and points) are validated for contiguity, with clear error messages for gaps, overlaps, and malformed tiers

**Independent Test**: Provide various valid and invalid tier configurations to Pydantic models and verify acceptance/rejection with descriptive error messages

### Implementation for User Story 3

- [ ] T017 [US3] Create `tests/test_match_modes.py` with validation tests for `TenureMatchTier` and `PointsMatchTier`: valid configs accepted, gap detection, overlap detection, missing start-at-zero, invalid ranges (max <= min), empty tier list when mode active, descriptive error messages
- [ ] T018 [US3] Add integration tests in `tests/test_match_modes.py` for `EmployerMatchSettings` loading with `tenure_based` and `points_based` modes: verify config round-trip through Pydantic validation, verify export produces correct dbt variables
- [ ] T019 [P] [US3] Add dbt test for `int_employee_match_calculations` verifying `applied_points` is populated for points_based mode and NULL for other modes in `dbt/tests/`

**Checkpoint**: All validation rules confirmed — invalid configs produce clear error messages, valid configs pass through cleanly

---

## Phase 6: User Story 4 — Edit Match Mode in PlanAlign Studio (Priority: P3)

**Goal**: Allow plan administrators to select match modes and configure tier breakpoints visually in the web UI

**Independent Test**: Launch PlanAlign Studio, select each match mode, edit tier breakpoints, save, and verify configuration persists

### Implementation for User Story 4

- [ ] T020 [US4] Extend workspace default config to include empty `tenure_match_tiers` and `points_match_tiers` arrays in `planalign_api/storage/workspace_storage.py`
- [ ] T021 [US4] Add match mode selector dropdown with all four options (deferral_based, graded_by_service, tenure_based, points_based) to the match configuration UI in `planalign_studio/src/components/`
- [ ] T022 [US4] Implement dynamic tier editor table that adapts columns based on selected mode (Min Years/Max Years for tenure, Min Points/Max Points for points) with add/remove row support in `planalign_studio/src/components/`
- [ ] T023 [US4] Add inline validation feedback for tier configurations (gap detection, overlap detection, start-at-zero) in the tier editor component in `planalign_studio/src/components/`

**Checkpoint**: Studio UI fully supports all four match modes with visual tier editing and real-time validation

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Regression testing, multi-year validation, quickstart verification

- [ ] T024 Run regression test — verify `deferral_based` mode produces identical output before and after changes by running simulation and comparing match results
- [ ] T025 [P] Run regression test — verify `graded_by_service` mode produces identical output before and after changes
- [ ] T026 Run multi-year simulation (3 years) with `points_based` mode and verify tier transitions when employees cross point boundaries (e.g., points 59 in Year 1 to 61 in Year 2)
- [ ] T027 [P] Run multi-year simulation with `tenure_based` mode and verify tier transitions when employees cross tenure boundaries
- [ ] T028 Run quickstart.md smoke tests for both `points_based` and `tenure_based` modes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 Points-Based (Phase 3)**: Depends on Foundational (Phase 2) — no dependency on other stories
- **US2 Tenure-Based (Phase 4)**: Depends on Foundational (Phase 2) — shares files with US1 (`int_employee_match_calculations.sql`, `export.py`, `simulation_config.yaml`), so best executed after US1
- **US3 Validation Testing (Phase 5)**: Depends on Foundational (Phase 2) — can start after T004-T006 are complete; test file is independent
- **US4 Studio UI (Phase 6)**: Depends on Foundational (Phase 2) — can start in parallel with US1/US2 for UI scaffolding
- **Polish (Phase 7)**: Depends on US1 + US2 being complete

### Within Each User Story

- Macros before model changes (US1: T008/T009 before T010)
- Model changes before export function (US1: T010 before T012; US2: T014 before T015)
- Export function changes enable end-to-end testing
- Config examples (T013, T016) can be done in parallel with implementation

### File Contention Map

These files are modified by multiple stories — execute sequentially:
- `int_employee_match_calculations.sql`: T010, T011 (US1) then T014 (US2)
- `export.py`: T012 (US1) then T015 (US2)
- `simulation_config.yaml`: T013 (US1) then T016 (US2) — parallel-safe if editing different sections

### Parallel Opportunities

**Within US1 (Phase 3)**:
```
T008 + T009 (macros, same file but paired) → T010 + T011 (model) → T012 (export)
T013 (config example) can run in parallel with any US1 task
```

**Across Stories (after Foundational)**:
```
US3 Testing (T017-T019) can start as soon as Foundational completes
US4 UI scaffolding (T020-T021) can start in parallel with US1
```

**Polish Phase**:
```
T024 + T025 (regression tests) can run in parallel
T026 + T027 (multi-year tests) can run in parallel
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (review existing code)
2. Complete Phase 2: Foundational (Pydantic models + dbt defaults)
3. Complete Phase 3: User Story 1 (points-based match)
4. **STOP and VALIDATE**: Run points_based smoke test from quickstart.md
5. Deploy/demo if ready — administrators can use YAML config for points-based matching

### Incremental Delivery

1. Setup + Foundational → Configuration infrastructure ready
2. Add US1 (Points-Based) → Test independently → **MVP!**
3. Add US2 (Tenure-Based) → Test independently → Both new modes available
4. Add US3 (Validation Testing) → Confirms all edge cases → Production confidence
5. Add US4 (Studio UI) → Visual configuration → Full feature complete
6. Polish → Regression + multi-year → Ship

### Risk Notes

- **Shared file contention**: `int_employee_match_calculations.sql` and `export.py` are modified by both US1 and US2 — implement US1 first, then add US2 branches
- **Existing mode regression**: Phase 7 regression tests (T024-T025) are critical — run BEFORE merging
- **Macro pattern**: Points macro follows exact pattern of existing tiered macro — low risk
- **Tenure reuse**: Tenure mode reuses existing macros with new config key — lowest risk change

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- `[min, max)` interval convention throughout: lower bound inclusive, upper bound exclusive
- Tier rates in dbt variables are percentages (50 = 50%); macros divide by 100
- `applied_points` is NULL for non-points modes; `applied_years_of_service` is NULL for deferral_based mode
