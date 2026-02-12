# Tasks: DC Plan Metrics in Scenario Comparison

**Input**: Design documents from `/specs/048-comparison-dc-metrics/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included per SC-005 (automated tests required) and Constitution Principle III (test-first development).

**Organization**: Tasks grouped by user story. US1 and US2 (both P1) share a phase since delta calculations are inherently part of the comparison builder method (following the existing `_build_workforce_comparison` pattern).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Pydantic Models)

**Purpose**: Add type-safe models that all user stories depend on. Must complete before any service implementation.

- [x] T001 Add `DCPlanMetrics` Pydantic model with 8 fields (participation_rate, avg_deferral_rate, total_employee_contributions, total_employer_match, total_employer_core, total_employer_cost, employer_cost_rate, participant_count) with zero defaults, and `DCPlanComparisonYear` model with year/values/deltas fields in `planalign_api/models/comparison.py`. Follow the existing `WorkforceMetrics` / `WorkforceComparisonYear` pattern. See `specs/048-comparison-dc-metrics/contracts/comparison-api.md` for exact field definitions.

- [x] T002 Extend `ComparisonResponse` in `planalign_api/models/comparison.py` by adding `dc_plan_comparison: List[DCPlanComparisonYear] = Field(default_factory=list, description="Year-by-year DC plan comparison")`. Import `DCPlanComparisonYear` in the existing imports. This is a non-breaking change (default empty list).

**Checkpoint**: Models compile and existing tests still pass. Run `python -c "from planalign_api.models.comparison import DCPlanMetrics, DCPlanComparisonYear"` to verify.

---

## Phase 2: User Story 1 + User Story 2 - DC Plan Comparison with Deltas (Priority: P1)

**Goal**: Return per-year DC plan metrics for each scenario with delta calculations vs baseline.

**Independent Test**: Request a comparison between two scenarios and verify dc_plan_comparison contains values and deltas for each year.

### Tests (write first, verify they fail)

- [x] T003 [US1] Create test file `tests/test_comparison_dc_plan.py` with in-memory DuckDB fixture that creates `fct_workforce_snapshot` table with columns: simulation_year, employee_id, employment_status, is_enrolled_flag, current_deferral_rate, prorated_annual_contributions, employer_match_amount, employer_core_amount, prorated_annual_compensation. Follow the pattern in `tests/test_analytics_service.py`. Include a helper function to seed employee rows and a mock `DatabasePathResolver` that returns the in-memory database path.

- [x] T004 [US1] Add test `test_dc_plan_metrics_happy_path` in `tests/test_comparison_dc_plan.py` that seeds 2 scenarios (baseline + alternative) with different enrollment rates and match amounts across 2 years (2025, 2026). Call the comparison service and assert that `dc_plan_comparison` has 2 entries (one per year), each with `values` containing metrics for both scenarios. Verify participation_rate, avg_deferral_rate, total_employer_match, participant_count are correct. Mark with `@pytest.mark.fast`.

- [x] T005 [US2] Add tests in `tests/test_comparison_dc_plan.py`: (1) `test_dc_plan_deltas_vs_baseline` - verify deltas are computed as scenario minus baseline for all 8 metrics, baseline deltas are all zero; (2) `test_dc_plan_deltas_zero_baseline` - when baseline has zero employer match, verify delta_pct is 0% not an error; (3) `test_dc_plan_edge_cases` - verify zero enrollment returns 0% participation, NULL contribution columns return 0, zero active employees returns 0 for all rate metrics. Mark all with `@pytest.mark.fast`.

### Implementation

- [x] T006 [US1] Add DC plan metrics SQL query to `_load_scenario_data()` in `planalign_api/services/comparison_service.py`. Add a new try/except block (after the existing hires query) that executes the GROUP BY query from `specs/048-comparison-dc-metrics/data-model.md` (Data Source section) against `fct_workforce_snapshot`. Use `.fetchdf().to_dict("records")` and add the result as `dc_plan` key in the returned dict. On exception, set `dc_plan` to empty list. Compute `employer_cost_rate` in Python: `(total_employer_cost / total_compensation * 100) if total_compensation > 0 else 0.0` for each row. Also handle NULL `avg_deferral_rate` by defaulting to 0.0.

- [x] T007 [US2] Implement `_build_dc_plan_comparison()` method in `planalign_api/services/comparison_service.py`. Follow the pattern of `_build_workforce_comparison()`: iterate all years across all scenarios, build `values` dict (baseline + alternatives) and `deltas` dict (baseline=zeros, alternatives=scenario_value-baseline_value). Return `List[DCPlanComparisonYear]`. Import `DCPlanMetrics` and `DCPlanComparisonYear` from models.

- [x] T008 [US1] Wire `_build_dc_plan_comparison()` into `compare_scenarios()` in `planalign_api/services/comparison_service.py`. Call the new method after `_build_event_comparison()`, passing `scenario_data`, `baseline_data`, and `baseline_id`. Set the result on `dc_plan_comparison=` in the `ComparisonResponse` constructor.

**Checkpoint**: Run `pytest tests/test_comparison_dc_plan.py -v` - all US1 and US2 tests should pass. Verify dc_plan_comparison returns correct values and deltas.

---

## Phase 3: User Story 3 - DC Plan Summary Deltas (Priority: P2)

**Goal**: Add final-year participation rate and total employer cost to summary_deltas with delta calculations vs baseline.

**Independent Test**: Verify `summary_deltas` contains `final_participation_rate` and `final_employer_cost` keys with correct DeltaValue structure.

### Tests (write first, verify they fail)

- [x] T009 [US3] Add test `test_dc_plan_summary_deltas` in `tests/test_comparison_dc_plan.py` that verifies: (1) `summary_deltas` contains keys `final_participation_rate` and `final_employer_cost`; (2) baseline values match the final year's raw metrics; (3) deltas are computed correctly for non-baseline scenarios; (4) delta_pcts handle zero baseline gracefully. Also add `test_dc_plan_summary_single_year` verifying single-year simulation produces correct summary values. Mark with `@pytest.mark.fast`.

### Implementation

- [x] T010 [US3] Add DC plan summary delta logic to `_build_summary_deltas()` in `planalign_api/services/comparison_service.py`. After the existing `total_growth_pct` block, add two new summary entries: `final_participation_rate` and `final_employer_cost`. For each: extract the final year's value from each scenario's dc_plan data, compute deltas and delta_pcts vs baseline using the existing `DeltaValue` pattern. Handle zero baseline with `delta_pct = 0.0`.

**Checkpoint**: Run `pytest tests/test_comparison_dc_plan.py -v` - all tests including US3 should pass.

---

## Phase 4: Polish & Validation

**Purpose**: Final verification that everything integrates correctly.

- [x] T011 Run full test suite (`pytest tests/ -v --tb=short`) and verify no regressions in existing tests. Verify the comparison endpoint response matches the contract in `specs/048-comparison-dc-metrics/contracts/comparison-api.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies - start immediately
- **Phase 2 (US1+US2)**: Depends on Phase 1 (models must exist for type hints)
- **Phase 3 (US3)**: Depends on Phase 2 (summary deltas read from dc_plan data loaded in US1)
- **Phase 4 (Polish)**: Depends on Phases 1-3

### User Story Dependencies

- **US1 (P1) + US2 (P1)**: Combined phase. US2 delta logic is part of the same `_build_dc_plan_comparison()` method that produces US1 values. Splitting would create an artificial two-pass implementation.
- **US3 (P2)**: Depends on US1 — reads dc_plan data from `scenario_data` dict populated by `_load_scenario_data()`.

### Within Each Phase

- Tests MUST be written and FAIL before implementation
- Models before services
- Service methods before wiring into compare_scenarios()
- Commit after each logical group

### Parallel Opportunities

- T001 and T002 are both in `comparison.py` — sequential
- T003, T004, T005 are all in the test file — sequential (but written before implementation)
- T006, T007, T008 are all in `comparison_service.py` — sequential
- Phase 2 tests (T003-T005) and Phase 3 tests (T009) could theoretically be written together since they're in the same file, but Phase 3 tests depend on understanding the implementation from Phase 2

---

## Parallel Example: Phase 2

```bash
# Step 1: Write all tests first (sequential, same file)
T003: Create test fixtures in tests/test_comparison_dc_plan.py
T004: Add happy-path aggregation test
T005: Add delta and edge case tests

# Step 2: Implement service methods (sequential, same file)
T006: Add SQL query to _load_scenario_data()
T007: Implement _build_dc_plan_comparison()
T008: Wire into compare_scenarios()

# Step 3: Verify
pytest tests/test_comparison_dc_plan.py -v
```

---

## Implementation Strategy

### MVP First (US1 + US2 = Phase 1 + Phase 2)

1. Complete Phase 1: Add Pydantic models
2. Complete Phase 2: Tests + DC plan comparison with values and deltas
3. **STOP and VALIDATE**: Run tests, verify endpoint returns dc_plan_comparison
4. This delivers the core value: users can compare DC plan outcomes across scenarios

### Incremental Delivery

1. Phase 1 + Phase 2 → DC plan comparison with deltas (MVP)
2. Phase 3 → Summary deltas for at-a-glance comparison
3. Phase 4 → Final validation and regression check

---

## Notes

- Total tasks: 11
- Tasks per story: US1=4, US2=2, US3=2, Shared=3
- All service changes are in `comparison_service.py` (~100 lines added, staying under 600-line constitution limit)
- No router changes needed — `ComparisonResponse` extension with default_factory=list is backward compatible
- SQL query is proven from `analytics_service.py` — copy and adapt, don't reinvent
