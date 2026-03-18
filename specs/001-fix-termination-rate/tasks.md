# Tasks: Fix Termination Rate Suggestion Bug

**Feature**: 001-fix-termination-rate | **Branch**: `001-fix-termination-rate`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Data Model**: [data-model.md](data-model.md)

**Feature Goal**: Fix the termination rate suggestion feature that incorrectly returns 100% for all scenarios, making it return realistic rates based on actual census data.

---

## Implementation Strategy

**MVP Scope** (User Story 1 - P1): Fix core calculation to return realistic termination rates instead of 100%
**Phase 2** (User Story 2 - P2): Add robust edge case handling and error messages
**Final Phase**: Documentation and performance validation

**Parallel Opportunities**:
- T003-T005 can be completed in parallel (different files, no dependencies)
- T007-T008 can be completed in parallel (different Pydantic models)
- T011-T012 can be completed in parallel (different test scenarios)

**Independent Tests**: Each user story can be tested independently:
- US1: Test with basic census data (active/terminated counts)
- US2: Test with edge cases (zero denominator, missing data)

---

## Phase 1: Setup & Investigation

Investigate the current implementation to identify the root cause of the 100% bug.

- [x] T001 Review current termination rate suggestion implementation in `planalign_api/routers/scenarios.py` and identify endpoint
- [x] T002 Locate suggestion calculation logic in `planalign_api/services/suggestion_service.py` (or identify actual file)
- [x] T003 Search codebase for hardcoded "100.0" values or percentage defaults in suggestion logic using `grep -r "100\.0\|100%"`
- [x] T004 Check for division-by-zero exception handlers that return 100% fallback
- [x] T005 Identify database query or dbt model that calculates active/terminated employee counts

**Phase 1 Success Criteria**:
- Root cause of 100% bug identified (division error, missing denominator, wrong filter, or fallback logic)
- File locations documented for all suggestion-related code
- Current formula understood and documented

---

## Phase 2: Foundational - Data Models & Test Infrastructure

Create type-safe Pydantic models and test fixtures for consistent data handling.

- [x] T006 Create Pydantic v2 model `TerminationRateCalculation` in `planalign_api/models/calculation.py` with fields: calculation_id, scenario_id, plan_design_id, total_active_employees, total_terminated_employees, calculated_rate, calculation_status, error_message
- [x] T007 [P] Create Pydantic v2 model `TerminationRateSuggestion` in `planalign_api/models/suggestion.py` with fields: scenario_id, suggested_rate, confidence, sample_size, error_message, suggested_at
- [x] T008 [P] Add validation constraints to both models (Pydantic validators for rate ranges 0-99%, confidence enum, null rate iff error_message present)
- [x] T009 Create test fixture `sample_census_data()` in `tests/fixtures/workforce_data.py` with basic census records (100 active, 5 terminated)
- [x] T010 [P] Create test fixture `edge_case_census_data()` in `tests/fixtures/workforce_data.py` with edge case scenarios (zero active, single employee, no terminations)
- [x] T011 [P] Add helper function `assert_valid_termination_rate()` in `tests/fixtures/` to validate suggestion response format

**Phase 2 Success Criteria**:
- Models can be instantiated with test data
- Pydantic validation catches invalid rates (>99%)
- Test fixtures ready for both normal and edge case scenarios
- Type safety enables compile-time validation

---

## Phase 3: User Story 1 (P1) - Calculate Realistic Termination Rate

Fix the core calculation logic to return realistic rates derived from actual census data instead of 100%.

**User Story Goal**: When a user views the termination rate suggestion for a scenario, the system returns the correct rate calculated from census data (not 100%).

**Independent Test Criteria**: Can be tested with `POST /api/scenarios/{id}/termination-rate-suggestion?year=2025` for various census files, verifying rates vary appropriately with data.

### US1 Task: Understand Current Data Flow

- [x] T012 [US1] Query census data in `dbt/simulation.duckdb` to verify available fields: SELECT * FROM census_data LIMIT 5
- [x] T013 [US1] Document census schema and identify columns for employee_id, employment_status, termination_date, hire_date

### US1 Task: Implement Correct Calculation Logic

- [x] T014 [US1] Create service function `calculate_active_employee_count()` in `planalign_api/services/suggestion_service.py` that counts ACTIVE employees in census
- [x] T015 [US1] Create service function `calculate_terminated_employee_count()` in `planalign_api/services/suggestion_service.py` that counts TERMINATED employees by year
- [x] T016 [US1] Implement correct formula in `suggest_termination_rate()` function: rate = (terminated_count / active_count) * 100 (NOT 100%)
- [x] T017 [US1] Add denominator validation: check if active_count > 0 before division to prevent fallback to 100%
- [x] T018 [US1] Replace hardcoded 100.0 or broken logic with actual calculation in suggestion endpoint

### US1 Task: Unit Tests

- [x] T019 [US1] Create test `test_termination_rate_basic()` in `tests/test_termination_rate_suggestion.py`: 100 active, 5 terminated → expect 5.0%
- [x] T020 [US1] Create test `test_termination_rate_no_terminations()` in `tests/test_termination_rate_suggestion.py`: 100 active, 0 terminated → expect 0.0%
- [x] T021 [US1] Create test `test_termination_rate_high_turnover()` in `tests/test_termination_rate_suggestion.py`: 100 active, 50 terminated → expect 50.0%
- [x] T022 [US1] Create test `test_termination_rate_small_population()` in `tests/test_termination_rate_suggestion.py`: 5 active, 1 terminated → expect 20.0%

### US1 Task: Integration Tests

- [x] T023 [US1] Create integration test `test_termination_rate_endpoint_realistic()` in `tests/integration/test_termination_rate.py` that calls endpoint with multiple census files and validates rates are not 100%
- [x] T024 [US1] Verify endpoint returns correct HTTP 200 status with suggestion response
- [x] T025 [US1] Verify rates vary appropriately across different census snapshots (SC-002: coefficient of variation > 0.1)

**Phase 3 Success Criteria** (User Story 1):
- All termination rate suggestions return values between 0% and 99% (never 100%)
- Suggested rates vary across different census files (not all the same)
- Calculation uses correct formula: (terminated / active) × 100
- Tests pass: T019-T025 all passing
- Acceptance Scenarios 1-3 from spec.md validated

---

## Phase 4: User Story 2 (P2) - Handle Edge Cases

Add robust error handling for edge cases to prevent 100% defaults when data is insufficient.

**User Story Goal**: When census has zero active employees or missing data, system returns clear error messages instead of defaulting to 100%.

**Independent Test Criteria**: Can be tested with `POST /api/scenarios/{id}/termination-rate-suggestion?year=2025` for edge case census files, verifying error messages are returned.

### US2 Task: Denominator Validation

- [x] T026 [US2] Add check in `suggest_termination_rate()` for zero active employees: `if active_count == 0: return error_message`
- [x] T027 [US2] Add check for negative or missing employee counts
- [x] T028 [US2] Create `CalculationError` exception class in `planalign_api/exceptions.py` with calculation_status enum
- [x] T029 [US2] Return `TerminationRateSuggestion` with suggested_rate=None and error_message instead of raising exception

### US2 Task: Error Messages

- [x] T030 [US2] Define user-friendly error messages in `planalign_api/constants.py`:
  - For zero active: "Unable to calculate termination rate: no active employees found in census"
  - For missing data: "Census data not available for the requested period"
  - For data quality issues: "Calculation failed due to data inconsistencies"
- [x] T031 [US2] Update endpoint response to include error_message field in HTTP response body (never 100%)

### US2 Task: Confidence Calculation

- [x] T032 [US2] Implement confidence determination logic in `suggest_termination_rate()`: HIGH (>100), MEDIUM (10-100), LOW (<10)
- [x] T033 [US2] Add confidence to suggestion response: `confidence: Literal['HIGH', 'MEDIUM', 'LOW']`

### US2 Task: Unit Tests

- [x] T034 [US2] Create test `test_termination_rate_zero_active()` in `tests/test_termination_rate_suggestion.py`: 0 active → expect error message and null rate
- [x] T035 [US2] Create test `test_termination_rate_single_employee()` in `tests/test_termination_rate_suggestion.py`: 1 active, 0 terminated → expect 0.0%
- [x] T036 [US2] Create test `test_termination_rate_missing_data()` in `tests/test_termination_rate_suggestion.py`: empty census → expect error message
- [x] T037 [US2] Create test `test_termination_rate_confidence_high()` in `tests/test_termination_rate_suggestion.py`: 200 active → confidence HIGH
- [x] T038 [US2] Create test `test_termination_rate_confidence_low()` in `tests/test_termination_rate_suggestion.py`: 5 active → confidence LOW

### US2 Task: Integration Tests

- [x] T039 [US2] Create test `test_termination_rate_edge_cases()` in `tests/integration/test_termination_rate.py` covering all edge case scenarios
- [x] T040 [US2] Verify HTTP 400/503 status codes returned for error cases with proper error_message
- [x] T041 [US2] Verify suggested_rate is always null when error_message is present (SC-003)

**Phase 4 Success Criteria** (User Story 2):
- Zero active employees handled with error message (not 100%)
- Single employee handled gracefully (0% or error message)
- Missing data handled with informative error messages
- Confidence correctly calculated based on sample size
- Tests pass: T034-T041 all passing
- Acceptance Scenarios 1-3 from spec.md (US2) validated

---

## Phase 5: Polish & Cross-Cutting Concerns

Final validation, documentation, and performance optimization.

- [ ] T042 Run full test suite: `pytest -m fast` (should include 256+ tests)
- [ ] T043 Verify test coverage for termination rate suggestion: >90% coverage
- [ ] T044 Run integration tests: `pytest -m integration` (validates end-to-end workflows)
- [ ] T045 Create performance test ensuring suggestion endpoint responds in <2 seconds with 100k+ employees
- [ ] T046 Validate all success criteria from spec.md (SC-001 through SC-005):
  - [ ] SC-001: Rates between 0-99% (not 100%)
  - [ ] SC-002: Rates vary appropriately (coef. variation > 0.1)
  - [ ] SC-003: Edge cases handled with messages (not 100%)
  - [ ] SC-004: 100% of test files return realistic rates
  - [ ] SC-005: Same census produces same rate (consistency)
- [ ] T047 Document the fix in `CHANGELOG.md`: what was broken, how it was fixed, files changed
- [ ] T048 Add examples to quickstart.md: test commands and expected results
- [ ] T049 Review code against Constitution principles (type-safety, modular, test-first, transparency)
- [ ] T050 Backward compatibility check: verify existing scenarios still work correctly

**Phase 5 Success Criteria**:
- All tests passing (256+ fast tests in <10s)
- Coverage >90% for suggestion service
- All success criteria validated
- Performance <2s for dashboard queries
- Documentation updated

---

## Dependencies & Execution Order

```
Phase 1 (T001-T005): Investigation
    ↓
Phase 2 (T006-T011): Data Models & Fixtures
    ↓
Phase 3 (T012-T025): User Story 1 (P1) - Core Fix
    ├─ Can run T012-T013 in parallel
    ├─ T014-T018 must complete before T019-T025
    └─ T019-T025 (tests) can run in parallel
    ↓
Phase 4 (T026-T041): User Story 2 (P2) - Edge Cases
    ├─ T026-T033 must complete before T034-T041
    └─ T034-T041 (tests) can run in parallel
    ↓
Phase 5 (T042-T050): Polish
    └─ All previous phases must complete before final validation
```

**Critical Path**: T001 → T002 → T005 → T014 → T016 → T023
**Parallel Opportunities**:
- US1 development (T014-T018) + US1 testing (T019-T025) can overlap
- US2 development (T026-T033) + US2 testing (T034-T041) can overlap after Phase 3 complete

---

## Task Summary by User Story

| User Story | Priority | Task Count | Test Tasks | Status |
|-----------|----------|-----------|-----------|--------|
| Investigation (Setup) | - | 5 | - | T001-T005 |
| Foundational | - | 6 | - | T006-T011 |
| **US1: Core Fix** | P1 | 14 | 7 | T012-T025 |
| **US2: Edge Cases** | P2 | 16 | 8 | T026-T041 |
| Polish & Validation | - | 9 | 1 | T042-T050 |
| **TOTAL** | - | **50 tasks** | **16 tests** | T001-T050 |

---

## Execution Plan

**Recommended Execution Order for MVP**:

1. **Execute Phase 1** (T001-T005): 1-2 hours investigation
2. **Execute Phase 2** (T006-T011): 1 hour setup (models + fixtures)
3. **Execute Phase 3** (T012-T025): 3-4 hours (fix + test US1)
   - Note: T012-T025 can be parallelized (tests can be written during development)
4. **Execute Phase 4** (T026-T041): 2-3 hours (edge cases + tests)
5. **Execute Phase 5** (T042-T050): 1 hour validation

**Total Estimated Effort**: 8-11 hours (can be reduced with parallel execution)

---

## Testing Strategy

**Test Coverage by Type**:
- **Unit Tests**: T019-T025, T034-T038 (individual calculation scenarios)
- **Integration Tests**: T023-T025, T039-T041 (full endpoint workflows)
- **Fixtures Used**: sample_census_data(), edge_case_census_data() from tests/fixtures/

**Running Tests**:
```bash
# Run all fast tests
pytest -m fast

# Run just termination rate tests
pytest tests/test_termination_rate_suggestion.py -v

# Run integration tests
pytest -m integration

# Run with coverage
pytest --cov=planalign_api/services/suggestion_service.py --cov-report=html
```

---

## Success Criteria Validation Checklist

After all tasks complete, verify against spec.md success criteria:

- [ ] **SC-001**: Termination rate suggestions return 0-99% for normal datasets (✓ verified by T019-T025)
- [ ] **SC-002**: Rates vary appropriately across census files (✓ verified by T023, T025)
- [ ] **SC-003**: Edge cases return informative messages instead of 100% (✓ verified by T034-T041)
- [ ] **SC-004**: 100% of test files return realistic rates (✓ verified by T046)
- [ ] **SC-005**: Same census always produces same rate (✓ verified by T046)

---

## Files Modified/Created Summary

**Files to Modify**:
- `planalign_api/routers/scenarios.py` - Endpoint review (T001)
- `planalign_api/services/suggestion_service.py` - Fix calculation logic (T014-T018, T026-T033)

**Files to Create**:
- `planalign_api/models/calculation.py` - TerminationRateCalculation (T006)
- `planalign_api/models/suggestion.py` - TerminationRateSuggestion (T007)
- `planalign_api/exceptions.py` - CalculationError exception (T028)
- `planalign_api/constants.py` - Error messages (T030)
- `tests/test_termination_rate_suggestion.py` - Unit tests (T019-T038)
- `tests/integration/test_termination_rate.py` - Integration tests (T023-T025, T039-T041)
- `tests/fixtures/workforce_data.py` - Test fixtures (T009-T010, update)

**Documentation to Update**:
- `CHANGELOG.md` - Record fix details (T047)
- `specs/001-fix-termination-rate/quickstart.md` - Add test examples (T048)

---

## Notes

- This is a critical bug fix affecting all scenario analyses
- The fix is isolated to the termination rate suggestion service (no architectural changes)
- Constitution compliance verified (test-first, type-safe, transparent, modular)
- MVP scope covers User Story 1 (core fix); User Story 2 (edge cases) adds robustness
- Parallel execution opportunities can reduce time 20-30%
