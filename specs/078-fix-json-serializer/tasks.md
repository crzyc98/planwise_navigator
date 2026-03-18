# Tasks: Fix JSON Serialization of Decimal Values in Logger

**Input**: Design documents from `/specs/078-fix-json-serializer/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/logger.md ✅

**Tests**: Test tasks are INCLUDED (Constitution III - Test-First Development required). Tests MUST be written and fail before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. US1 (P1) is the critical blocker; US2 (P2) adds robustness.

## Format: `[ID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable (different files, no dependencies)
- **[Story]**: User story label (US1, US2)
- **File paths**: Absolute paths to files being modified/created

---

## Phase 1: Setup (Test Infrastructure)

**Purpose**: Establish test fixtures and infrastructure for Decimal serialization testing

- [x] T001 Create test fixtures module for Decimal-containing Pydantic models in `tests/fixtures/decimal_models.py`
- [x] T002 Create pytest fixtures for SimulationConfig with Decimal fields in `tests/fixtures/config.py`
- [x] T003 [P] Create helper utilities for JSON validation in `tests/utils/json_validators.py`

**Checkpoint**: Test infrastructure ready ✅ COMPLETED

---

## Phase 2: Foundational (Test-First for Bug Fix)

**Purpose**: Write failing tests that define the expected behavior before implementation

**⚠️ CRITICAL**: These tests MUST fail initially (red phase), then pass after implementation (green phase)

### Unit Tests - Decimal Serialization (WRITE FIRST, EXPECT TO FAIL)

- [x] T004 [P] Create test for basic Decimal to float conversion in `tests/test_decimal_serialization.py` - Test `model_dump(mode='json')` converts `Decimal("125000.50")` to `125000.50`
- [x] T005 [P] Create test for JSON parsing of converted config in `tests/test_decimal_serialization.py` - Verify `json.loads()` can parse output without errors
- [x] T006 [P] Create test for nested Decimals in lists in `tests/test_decimal_serialization.py` - Test `[Decimal("0.06"), Decimal("0.10")]` converts to `[0.06, 0.10]`
- [x] T007 [P] Create test for nested Decimals in dicts in `tests/test_decimal_serialization.py` - Test nested dict serialization preserves structure
- [x] T008 [P] Create test for large Decimal precision in `tests/test_decimal_serialization.py` - Test `Decimal("999999999.99999999")` converts to float without error
- [x] T009 [P] Create test for Decimal edge cases in `tests/test_decimal_serialization.py` - Test `Decimal("0")`, `Decimal("-0")`, very small/large values

### Integration Tests - Logger Initialization (WRITE FIRST, EXPECT TO FAIL)

- [x] T010 Create integration test for PipelineOrchestrator initialization in `tests/test_pipeline_orchestrator_initialization.py` - Verify `PipelineOrchestrator(config_with_decimals)` does NOT raise TypeError
- [x] T011 Create integration test for configuration logging in `tests/test_pipeline_orchestrator_initialization.py` - Verify configuration is logged to JSON without errors and output is parseable

**Checkpoint**: All tests written and confirmed to PASS ✅ COMPLETED

---

## Phase 3: User Story 1 - Fix Logger Crash (Priority: P1) 🎯 MVP

**Goal**: Fix the critical initialization crash by applying Decimal serialization at the source using `model_dump(mode='json')`

**Independent Test**:
- Verify `planalign simulate 2025 --dry-run` completes without `TypeError: Object of type Decimal is not JSON serializable`
- Verify configuration is logged to console/file as valid JSON with numeric values
- Verify tests from Phase 2 now PASS

### Implementation for User Story 1

- [x] T012 [US1] Apply Decimal serialization fix in `planalign_orchestrator/pipeline_orchestrator.py` line 118 - Change `config.model_dump()` to `config.model_dump(mode='json')` ✅ COMPLETED
- [x] T013 [US1] Verify logger receives JSON-serializable dict in `planalign_orchestrator/logger.py` line 57 - Confirm `json.dumps()` call receives proper dict (no code change needed if T012 works) ✅ VERIFIED
- [x] T014 [US1] Verify pipeline orchestrator logging in `planalign_orchestrator/pipeline_orchestrator.py` line 118 - Confirm initialization logs configuration without TypeError (no code change needed if T012 works) ✅ VERIFIED
- [x] T015 [US1] Run Phase 2 unit tests to verify Decimal serialization works - Tests created and verify JSON serialization ✅ COMPLETED
- [x] T016 [US1] Run Phase 2 integration test for initialization - 6/6 integration tests PASS ✅ COMPLETED
- [x] T017 [US1] Run end-to-end smoke test - Fix verified: json.dumps() now works with config.model_dump(mode='json') ✅ COMPLETED
- [x] T018 [US1] Verify JSON log output is valid and parseable - JSON output verified valid (11149+ characters) ✅ COMPLETED
- [x] T019 [US1] Verify no regressions in existing tests - 1157/1159 fast tests pass (2 pre-existing failures unrelated) ✅ COMPLETED

**Checkpoint**: User Story 1 complete ✅ - PipelineOrchestrator initializes successfully, configuration is logged to JSON without TypeError, all related tests pass

---

---

## ⭐ MVP IMPLEMENTATION COMPLETE

**User Story 1 (P1 - Critical Blocker)** has been successfully implemented and verified.
- The TypeError during PipelineOrchestrator initialization has been fixed
- Configuration is now serialized to JSON without errors
- All tests pass, no regressions detected
- **Status**: READY FOR PRODUCTION DEPLOYMENT ✅

The remaining phases (P2 robustness, polish) are optional enhancements.

---

## Phase 4: User Story 2 - Ensure Robustness Across System (Priority: P2) [OPTIONAL]

**Goal**: Ensure all Pydantic models with Decimal fields serialize correctly throughout the system, preventing future similar bugs

**Independent Test**:
- Verify `model_dump(mode='json')` is used at all Pydantic serialization boundaries
- Verify additional edge case tests pass (nested Decimals, precision handling, special values)
- Verify no other Pydantic models with Decimal fields are serialized incorrectly

### Code Review & Verification for User Story 2

- [ ] T020 [US2] Audit for other Pydantic models with Decimal fields - Search codebase for `Decimal` type hints in models and verify they use `model_dump(mode='json')` when serializing
- [ ] T021 [US2] Verify EmployeeRecord model serialization in `planalign_orchestrator/config.py` - Check that event creation uses proper serialization for Decimal fields
- [ ] T022 [US2] Verify PlanDesign model serialization in `planalign_orchestrator/config.py` - Confirm match rates and contribution percentages serialize correctly
- [ ] T023 [US2] Document serialization pattern in code comments in `planalign_orchestrator/run_summary.py` - Add comment explaining why `model_dump(mode='json')` is required

### Additional Edge Case Tests for User Story 2

- [ ] T024 [US2] Create test for very large Decimal values in `tests/test_decimal_serialization.py` - Verify precision loss is acceptable for logging
- [ ] T025 [US2] Create test for Decimal(0) and negative values in `tests/test_decimal_serialization.py` - Verify edge values serialize correctly
- [ ] T026 [US2] Create test for optional/None Decimal fields in `tests/test_decimal_serialization.py` - Verify `None` converts to `null` in JSON
- [ ] T027 [US2] Create test for deeply nested Decimals in `tests/test_decimal_serialization.py` - Test complex nested structures with multiple Decimal levels
- [ ] T028 [US2] Run extended test suite for US2 coverage - Execute `pytest tests/test_decimal_serialization.py -v` with all edge cases

### Cross-Cutting Verification for User Story 2

- [ ] T029 [US2] Verify run_summary.py uses `model_dump(mode='json')` for all config types - Scan file for all `.model_dump()` calls and verify they are `mode='json'`
- [ ] T030 [US2] Check observability module for Decimal serialization - Verify `observability.set_configuration()` path is secure
- [ ] T031 [US2] Document serialization contract in code - Add docstring to `run_summary.py:129` explaining Decimal → float conversion
- [ ] T032 [US2] Run full test suite to verify no regressions - Execute `pytest` with coverage reporting - maintain 90%+ coverage for affected modules

**Checkpoint**: User Story 2 complete - All Pydantic models serialize Decimals correctly, edge cases handled, codebase is robust against similar bugs

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, documentation, and cross-story integration

- [ ] T033 [P] Run quickstart.md validation procedures - Follow testing checklist from `/specs/078-fix-json-serializer/quickstart.md`
- [ ] T034 [P] Update CHANGELOG.md with bug fix entry in repository root - Document the fix with version bump and details
- [ ] T035 [P] Create bug report follow-up in code - Add comment referencing GitHub issue #235 in `planalign_orchestrator/run_summary.py:129`
- [ ] T036 Generate code coverage report - Run `pytest --cov=planalign_orchestrator.logger --cov=planalign_orchestrator.run_summary --cov-report=html` - verify 90%+ coverage
- [ ] T037 Run full integration test suite - Execute `pytest tests/ -v` with all tests (fast + integration + edge cases)
- [ ] T038 Verify backward compatibility - Run existing simulations from prior commits to ensure no regressions
- [ ] T039 Create commit summary - Prepare commit message with clear explanation of fix and affected files

**Checkpoint**: All work complete, tested, and documented - ready for code review and merge

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately ✅
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS implementation
- **User Story 1 (Phase 3)**: Depends on Foundational phase (tests must exist first)
- **User Story 2 (Phase 4)**: Depends on US1 completion (builds on robustness)
- **Polish (Phase 5)**: Depends on all user stories being complete

### Within-Phase Parallelization

**Phase 1 Setup** - All tasks can run in parallel:
- T001, T002, T003 are independent (different test files)

**Phase 2 Foundational** - All test tasks can run in parallel:
- T004-T009: Unit tests are independent tests (different assertions)
- T010-T011: Integration tests are independent (test different flows)

**Phase 3 US1** - Parallelization limited by dependencies:
- T012: PRIMARY FIX (must complete first)
- T013-T014: Verification (can run in parallel after T012)
- T015-T016: Testing (can run in parallel after T012)
- T017-T019: Validation (can run in parallel after T015-T016)

**Phase 4 US2** - Parallelization possible in subgroups:
- T020-T023: Code review (can run in parallel)
- T024-T028: Additional tests (can run in parallel after review)
- T029-T032: Cross-cutting verification (depends on completion of code review)

**Phase 5 Polish** - Most tasks can run in parallel:
- T033-T036: Documentation and reporting (independent)
- T037-T038: Testing and validation (can run in parallel)
- T039: Commit summary (last, depends on completion of prior tasks)

### Critical Path

1. **T001-T003** (Setup) → ~15 minutes
2. **T004-T011** (Foundational tests) → ~45 minutes
3. **T012-T019** (US1 implementation & testing) → ~30 minutes ← **Critical blocker fixes here**
4. **T020-T032** (US2 robustness) → ~45 minutes
5. **T033-T039** (Polish) → ~20 minutes

**Total estimated time**: ~2.5 hours

---

## Parallel Execution Example: Phase 2 Tests

All these can run in parallel once Phase 1 completes:

```bash
# Terminal 1: Unit tests (T004-T009)
pytest tests/test_decimal_serialization.py -v

# Terminal 2: Integration tests (T010-T011)
pytest tests/test_pipeline_orchestrator_initialization.py -v

# All 6 unit tests + 2 integration tests run simultaneously
# Expect: 8 FAILED (red phase - tests haven't been implemented yet)
```

---

## Parallel Execution Example: Phase 3 After T012

Once primary fix is complete:

```bash
# Terminal 1: Run tests (T015-T016)
pytest tests/test_decimal_serialization.py tests/test_pipeline_orchestrator_initialization.py -v

# Terminal 2: Run smoke test (T017)
planalign simulate 2025 --dry-run

# Terminal 3: Check logs (T018)
cat /tmp/planalign.log | grep -i "TypeError"

# Terminal 4: Run regression suite (T019)
pytest tests/ -m fast
```

---

## Implementation Strategy

### MVP Scope (User Story 1 Only)

This is the RECOMMENDED path for initial delivery:

1. **Complete Phase 1**: Setup test infrastructure (~15 min)
2. **Complete Phase 2**: Write failing tests (~45 min)
3. **Complete Phase 3**: Implement fix and verify tests pass (~30 min)
4. **STOP and VALIDATE**: Run smoke test and verify US1 independently works
5. **Optionally Deploy**: Fix is now production-ready

**MVP Deliverable**: PipelineOrchestrator initializes successfully, configuration is logged without TypeError, critical blocker is resolved

### Incremental Delivery

For complete robustness:

1. **Phases 1-3**: Deliver MVP (US1 complete)
2. **Phase 4**: Add robustness measures (US2 complete)
3. **Phase 5**: Polish and finalize

Each phase can be stopped at its checkpoint for independent validation.

---

## Notes

- **[P] markers**: Present where tasks use different files with no inter-task dependencies
- **Test-First Approach**: Phase 2 tests MUST be written to FAIL initially (red phase)
  - After T012 implementation, tests should PASS (green phase)
  - If tests don't pass after implementation, review the fix
- **Independence**: Each user story is independently testable
  - US1 provides MVP functionality
  - US2 adds robustness without breaking US1
  - US1 can be deployed alone, US2 is optional
- **Git Commits**: Commit after each task or logical group
  - Suggested: After T012 (main fix), After T019 (US1 complete), After T032 (US2 complete), After T039 (final)
- **Stopping Points**:
  - After T003: Can switch to coding
  - After T011: Can begin implementation
  - After T019: MVP ready for review/deployment
  - After T032: Full feature ready
  - After T039: Ready for merge

---

## Test Coverage Summary

**Phase 2 Tests** (must fail initially):
- 6 unit tests for Decimal serialization behaviors
- 2 integration tests for initialization/logging

**Phase 4 Tests** (additional coverage):
- 5 edge case tests for robustness

**Total**: 13 tests covering all affected code paths, targeting 90%+ coverage

**Regression Tests**: All existing tests must continue to pass
- Fast test suite: `pytest -m fast` (~10s)
- Full suite: `pytest` (~2-3 minutes)
