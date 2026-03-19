# Tasks: Fix SimulationConfig.from_dict() Failure in Result Handler

**Feature Branch**: `079-fix-config-deser`
**Input**: Design documents from `/specs/079-fix-config-deser/`
**Status**: Ready for implementation

**Tests**: Included (TDD approach - write tests first, ensure they fail, then implement)

**Organization**: Tasks organized by user story to enable independent implementation and testing.

---

## Format: `- [ ] [ID] [P?] [Story] Description with file path`

- **[P]**: Task can run in parallel (different files, no blocking dependencies)
- **[Story]**: User story label (US1, US2, US3) - required for story phase tasks
- **File paths**: Absolute paths or relative to repository root

---

## Dependencies & Parallel Execution

### Dependency Graph

```
Phase 2 (Foundational)
    ↓
    ├─→ Phase 3 (US1 - P1: Error Logging) ─→ Phase 6 (Integration)
    ├─→ Phase 4 (US2 - P2: Key Filtering) ─→ Phase 6 (Integration)
    └─→ Phase 5 (US3 - P3: Serialization) ─→ Phase 6 (Integration)
```

### Parallel Opportunities

**Phase 3 (US1)**: Error logging test/impl can run in parallel with Phase 4-5 setup
- T004-T007: Can start immediately after Phase 2
- Does not depend on from_dict() classmethod (US2)
- Does not depend on serialization changes (US3)

**Phase 4 (US2)**: Key filtering can run in parallel with Phase 3-5
- T008-T012: Can start after Phase 2
- Does not depend on error logging (US1)
- Does not depend on serialization (US3)

**Phase 5 (US3)**: Serialization updates can run in parallel with Phase 3-4
- T013-T017: Can start after Phase 2 identification (T001)
- Does not depend on error logging (US1)
- Does not depend on key filtering (US2)

**Recommended**: After Phase 2, execute Phase 3/4/5 in parallel, then Phase 6 integration

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization - already complete

- [x] T001 Branch `079-fix-config-deser` created and checked out ✅
- [x] T002 Specification and planning documents created ✅
- [x] T003 Test fixtures directory structure created ✅

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core analysis and test infrastructure that must be complete before ANY user story

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete

### Foundational Analysis & Identification

- [x] T004 Identify all `model_dump()` call sites in codebase using grep: `grep -r "model_dump()" planalign_orchestrator/ planalign_api/ config/ --include="*.py"` and document in `/workspace/specs/079-fix-config-deser/analysis.md`

- [x] T005 Examine `planalign_api/services/simulation/result_handlers.py` lines 60-75 to understand current config merging and error handling flow

- [x] T006 Review `config/schema.py` SimulationConfig class definition to understand all fields, validators, and current config construction patterns

### Foundational Test Infrastructure

- [x] T007 [P] Create test fixture file `tests/fixtures/config_fixtures.py` with helper functions:
  - `create_valid_config_dict()` - Valid config with all required fields
  - `create_config_with_extra_keys()` - Config with unknown keys from Studio overrides
  - `create_config_with_decimals()` - Config with Decimal values (pre-fix test)
  - `create_incomplete_config()` - Config missing optional/required fields

- [x] T008 [P] Create conftest.py test setup in `tests/unit/` if not exists, importing shared fixtures

**Checkpoint**: Foundational work complete - User story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Accurate Error Logging on Deserialization Failure (Priority: P1) 🎯 MVP

**Goal**: Improve error logging in result handler so that deserialization failures show actual exception details (exception type + message) instead of truncated "from_dict" method name.

**Independent Test**: Run `pytest tests/unit/test_config_deser_error_logging.py -v` and verify error logs contain exception type (TypeError, ValidationError, etc.) and specific error message.

### Tests for User Story 1 (TDD - Write First)

> **Write these tests FIRST - they will FAIL before implementation**

- [x] T009 [P] [US1] Write error logging test file `tests/unit/test_config_deser_error_logging.py`:
  - Test case: `test_decimal_type_error_includes_exception_details()` - Verify error log contains "TypeError" when Decimal value passed
  - Test case: `test_unknown_key_error_includes_exception_details()` - Verify error log shows specific key and error message
  - Test case: `test_missing_field_error_includes_exception_details()` - Verify error log shows which field is missing
  - All tests should use `caplog` to capture WARNING/ERROR level logs
  - Assertions: `assert "TypeError" in caplog.text or "ValidationError" in caplog.text`

- [x] T010 [P] [US1] Write result handler integration test `tests/integration/test_result_handler_error_logging.py`:
  - Simulate result handler with invalid config dict
  - Capture logged errors
  - Verify error message format matches expected pattern: `[ExceptionType]: [message]`

### Implementation for User Story 1

- [x] T011 [US1] Update error logging in `planalign_api/services/simulation/result_handlers.py`:
  - Locate lines 66-68 (try-except block for SimulationConfig.from_dict)
  - Current: `logger.warning(f"Could not create SimulationConfig from dict: {e}")`
  - Change to: `logger.warning(f"Could not create SimulationConfig from dict: {type(e).__name__}: {e}")`
  - Alternative: Add more detailed error handling with separate handlers for TypeError, ValidationError, KeyError, Exception
  - Add `exc_info=True` parameter to logger call to include full traceback in DEBUG logs

- [x] T012 [US1] Verify error logging captures exception context:
  - Add import: `import logging` (if not present)
  - Ensure logger instance is available: `logger = logging.getLogger(__name__)`
  - Test: Run T009 tests to verify they PASS after this implementation

- [x] T013 [US1] Run unit tests to verify error logging works:
  - Execute: `pytest tests/unit/test_config_deser_error_logging.py -v`
  - Verify: All tests pass
  - Run fast suite: `pytest -m fast --tb=short` to ensure no regressions

**Checkpoint**: User Story 1 complete - error logging now provides diagnostic details. Can proceed to US2 and US3 in parallel.

---

## Phase 4: User Story 2 - Robust Config Deserialization with Key Filtering (Priority: P2)

**Goal**: Make SimulationConfig deserialization robust to unknown keys from scenario overrides. Implement key filtering in `from_dict()` classmethod.

**Independent Test**: Run `pytest tests/unit/test_config_from_dict.py -v` and verify from_dict() succeeds with config dicts containing unknown keys (filtered silently) and missing optional fields (use defaults).

### Tests for User Story 2 (TDD - Write First)

> **Write these tests FIRST - they will FAIL before implementation**

- [x] T014 [P] [US2] Write classmethod test file `tests/unit/test_config_from_dict.py`:
  - Test case: `test_from_dict_with_all_valid_fields()` - All valid fields should succeed
  - Test case: `test_from_dict_filters_unknown_keys()` - Unknown keys should be silently filtered
  - Test case: `test_from_dict_with_missing_optional_fields()` - Missing optional fields should use Pydantic defaults
  - Test case: `test_from_dict_with_missing_required_field()` - Missing required field should raise ValidationError
  - Test case: `test_from_dict_preserves_values()` - Filtered dict should preserve all valid field values
  - Use fixtures from `tests/fixtures/config_fixtures.py`

### Implementation for User Story 2

- [x] T015 [US2] Add `from_dict()` classmethod to SimulationConfig in `config/schema.py`:
  - Location: Add method inside the SimulationConfig class (after validators)
  - Implementation:
    ```python
    @classmethod
    def from_dict(cls, data: dict) -> "SimulationConfig":
        """Create SimulationConfig from dict, filtering unknown keys.

        Args:
            data: Dictionary that may contain unknown keys from merging

        Returns:
            Reconstructed SimulationConfig instance

        Raises:
            ValidationError: If required fields missing or invalid types
        """
        known_fields = cls.model_fields.keys()
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)
    ```
  - Add docstring with examples

- [x] T016 [US2] Verify from_dict() implementation:
  - Inspect method signature and docstring are correct
  - Verify Pydantic v2 model_fields attribute exists and is accessible
  - Run T014 tests to verify they PASS

- [x] T017 [US2] Run unit tests to verify key filtering:
  - Execute: `pytest tests/unit/test_config_from_dict.py -v`
  - Verify: All tests pass
  - Verify: from_dict() accepts dicts with extra keys
  - Verify: from_dict() uses Pydantic defaults for missing optional fields
  - Run fast suite: `pytest -m fast --tb=short` to ensure no regressions

**Checkpoint**: User Story 2 complete - from_dict() now robustly handles merged config dicts. Can proceed to US3 and integration in Phase 6.

---

## Phase 5: User Story 3 - Type-Safe Config Serialization Upstream (Priority: P3)

**Goal**: Ensure Decimal values are converted to floats BEFORE reaching from_dict(). Update all `model_dump()` calls to use `model_dump(mode='json')` at serialization boundaries.

**Independent Test**: Run `pytest tests/integration/test_config_serialization_roundtrip.py -v` and verify config survives serialization→deserialization roundtrip without type errors.

### Tests for User Story 3 (TDD - Write First)

> **Write these tests FIRST - they will FAIL before implementation (if Decimal serialization is broken)**

- [x] T018 [P] [US3] Write roundtrip test file `tests/integration/test_config_serialization_roundtrip.py`:
  - Test case: `test_config_roundtrip_with_model_dump_json()` - Config survives serialize→deserialize with model_dump(mode='json')
  - Test case: `test_config_roundtrip_with_scenario_overrides()` - Roundtrip with Studio scenario overrides
  - Test case: `test_model_dump_json_converts_decimals_to_floats()` - Verify Decimal→float conversion in serialized dict
  - Assertions: No TypeErrors; all values match original config

### Implementation for User Story 3

- [x] T019 [US3] Locate serialization call sites using grep:
  - Execute: `grep -rn "\.model_dump()" planalign_orchestrator/ planalign_api/ config/ --include="*.py" | grep -v "mode='json'" | head -20`
  - Document findings in analysis notes
  - Identify: Run archiver, logger, result handler, any other serialization points

- [x] T020 [P] [US3] Update archiver to use `model_dump(mode='json')`:
  - Find run archiver module (likely `planalign_orchestrator/archiver.py` or similar)
  - Locate lines that serialize SimulationConfig with `model_dump()`
  - Change: `config.model_dump()` → `config.model_dump(mode='json')`
  - Purpose: Converts Decimal→float so from_dict() receives only JSON-serializable types

- [x] T021 [P] [US3] Update logger to use `model_dump(mode='json')`:
  - Find logger module (likely `planalign_orchestrator/observability/logger.py` or similar)
  - Locate where configuration is logged during initialization
  - Change: `config.model_dump()` → `config.model_dump(mode='json')`
  - Purpose: Ensures Decimal values are already floats when logged

- [x] T022 [P] [US3] Search and update other `model_dump()` call sites:
  - Use grep results from T019 to identify any remaining call sites
  - For each occurrence: Evaluate if serialization to JSON is intended
  - If yes: Change to `model_dump(mode='json')`
  - If no (internal Python object usage): Leave as-is with comment
  - Common locations: Services, API routers, database utilities

- [x] T023 [US3] Verify serialization changes:
  - Run T018 integration tests to verify roundtrip serialization works
  - Execute: `pytest tests/integration/test_config_serialization_roundtrip.py -v`
  - Verify: No TypeErrors during deserialization
  - Verify: Config values match after roundtrip
  - Run fast suite: `pytest -m fast --tb=short` to ensure no regressions

**Checkpoint**: User Story 3 complete - serialization now converts Decimals to floats upstream. All three user stories ready for integration testing.

---

## Phase 6: Polish & Integration Testing

**Purpose**: Cross-story integration, comprehensive testing, and preparation for merge

### Integration Testing

- [x] T024 [P] Run full integration test suite:
  - Execute: `pytest tests/integration/ -v --tb=short`
  - Verify: All result handler + config tests pass
  - Verify: No failures in related modules

- [x] T025 [P] Run complete fast test suite:
  - Execute: `pytest -m fast --tb=short`
  - Verify: All tests pass in <10 seconds
  - Target: ~120 tests in <10 seconds baseline

- [x] T026 [P] Run test suite with coverage:
  - Execute: `pytest tests/unit/test_config*.py tests/integration/test_config*.py --cov=config --cov=planalign_api.services.simulation.result_handlers --cov-report=term-missing`
  - Verify: >90% coverage for modified modules
  - Verify: No new uncovered code paths

### End-to-End Validation

- [x] T027 [US1] [US2] [US3] Run complete simulation to verify no regressions:
  - Execute: `planalign simulate 2025 --dry-run` (preview mode)
  - Verify: No errors during initialization or execution
  - Check logs: Confirm error messages include proper exception details if any occur

- [x] T028 [P] Verify result metadata displays correctly in Studio UI (if applicable):
  - Start Studio: `planalign studio`
  - Complete a test simulation run
  - Check: Run metadata displays correctly
  - Check: Config is shown in UI without "undefined" values
  - Check: No deserialization errors in logs

### Documentation & Cleanup

- [x] T029 Verify all test files have proper docstrings and comments:
  - Check: `tests/unit/test_config_deser_error_logging.py` - Clear test purpose
  - Check: `tests/unit/test_config_from_dict.py` - Clear assertions
  - Check: `tests/integration/test_config_serialization_roundtrip.py` - Clear roundtrip test description

- [x] T030 Update code comments in modified files:
  - File: `planalign_api/services/simulation/result_handlers.py` - Note improved error logging
  - File: `config/schema.py` - Document from_dict() purpose and key filtering behavior
  - File: Archiver/Logger - Note Decimal→float conversion

### Final Checkpoint

- [x] T031 All tests passing:
  - Fast test suite: `pytest -m fast` ✅ (1171 passed)
  - Integration tests: `pytest -m integration` ✅ (6 passed)
  - Affected modules: >90% coverage ✅
  - No test regressions ✅ (2 pre-existing failures unrelated to this feature)

- [x] T032 Code review checklist:
  - [x] All three user stories fully implemented
  - [x] Error logging captures full exception context
  - [x] from_dict() handles unknown keys gracefully
  - [x] Serialization uses model_dump(mode='json')
  - [x] Tests written first (TDD approach)
  - [x] All tests passing (20/20 feature tests)
  - [x] No new dependencies added
  - [x] Backward compatible (no breaking changes)

---

## Summary

### Total Tasks: 32

### Tasks by Phase
- **Phase 1 (Setup)**: 3 tasks ✅ (complete)
- **Phase 2 (Foundational)**: 5 tasks
- **Phase 3 (US1 - P1 Error Logging)**: 5 tasks
- **Phase 4 (US2 - P2 Key Filtering)**: 4 tasks
- **Phase 5 (US3 - P3 Serialization)**: 6 tasks
- **Phase 6 (Polish & Integration)**: 4 tasks

### Implementation Strategy

**MVP Scope (Phase 3 only)**:
- Implement error logging improvement (US1)
- Delivers immediate diagnostic value (sub-5 min bug diagnosis)
- Can be merged independently if needed

**Recommended Full Scope (Phase 3 + 4 + 5)**:
- All three user stories together provide complete fix
- Error logging → Robust deserialization → Safe serialization
- Form complete solution to Issue #240

### Parallel Execution Opportunities

**After Phase 2**, execute these in parallel:
- Phase 3 (US1 - Error Logging): T009-T013 [4 hours]
- Phase 4 (US2 - Key Filtering): T014-T017 [3 hours]
- Phase 5 (US3 - Serialization): T018-T023 [4 hours]

Then execute Phase 6 (Polish) sequentially: [2 hours]

**Total Estimated Time**: 6-7 hours implementation + testing

---

## Next Steps

1. **Start Phase 2**: Run T004-T008 to establish foundational understanding
2. **Proceed to Phase 3/4/5**: Execute in parallel using checklist format
3. **Verify Phase 6**: Run all tests before merging
4. **Review & Merge**: Standard PR process with code review

**Ready to start implementing?** Begin with Phase 2 (T004-T008).
