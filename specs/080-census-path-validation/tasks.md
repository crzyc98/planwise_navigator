# Tasks: Enforce Census Path Validation on Simulation Start

**Input**: Design documents from `/specs/080-census-path-validation/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included per Constitution III (Test-First Development) and plan.md requirements.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Verify existing infrastructure and prepare for implementation

- [x] T001 Read current `_validate_census()` implementation in `planalign_api/services/simulation/service.py` (lines 404-412) and confirm silent fallback behavior matches research.md findings
- [x] T002 Read `planalign_orchestrator/exceptions.py` to confirm `ConfigurationError`, `ExecutionContext`, and `ErrorSeverity` classes exist and match data-model.md contracts
- [x] T003 [P] Read `planalign_orchestrator/error_catalog.py` to confirm `ErrorPattern`, `ErrorCatalog`, and `ResolutionHint` classes exist and identify insertion point for new patterns

**Checkpoint**: Existing infrastructure verified — implementation can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Error catalog entries that both US1/US2 and US3 depend on

**CRITICAL**: Error catalog patterns must exist before validation logic can be fully tested with resolution hints

- [x] T004 [P] Add "Census File Not Configured" error pattern to `_initialize_patterns()` in `planalign_orchestrator/error_catalog.py` — regex matching `census_parquet_path is required.*not found.*scenario config`, category CONFIGURATION, with ResolutionHint including 5-step upload instructions per quickstart.md
- [x] T005 [P] Add "Census File Missing or Moved" error pattern to `_initialize_patterns()` in `planalign_orchestrator/error_catalog.py` — regex matching `Census file not found at.*Upload a valid census parquet`, category CONFIGURATION, with ResolutionHint including 5-step verify-and-reupload instructions per quickstart.md

**Checkpoint**: Error catalog ready — validation logic can reference catalog patterns

---

## Phase 3: User Story 1 & 2 — Census Validation Happy Path + Missing Path Error (Priority: P1) MVP

**Goal**: Replace silent fallback with hard-fail validation when `census_parquet_path` is missing or empty. Users uploading a valid census file get successful simulation; users without a census file get an immediate, actionable error.

**Independent Test**: Launch simulation with valid census file → succeeds. Launch simulation without census file → immediate ConfigurationError with actionable message before any data processing.

### Tests for User Story 1 & 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T006 [P] [US1] Write test `test_validate_census_valid_path` in `tests/test_census_validation.py` — create temp parquet file via `tmp_path`, pass config with valid `setup.census_parquet_path`, assert `_validate_census()` returns without error
- [x] T007 [P] [US2] Write test `test_validate_census_missing_key` in `tests/test_census_validation.py` — pass config `{"setup": {}}` (no census_parquet_path key), assert raises `ConfigurationError` with message matching FR-002: "census_parquet_path is required but was not found in the scenario config"
- [x] T008 [P] [US2] Write test `test_validate_census_empty_string` in `tests/test_census_validation.py` — pass config `{"setup": {"census_parquet_path": ""}}`, assert raises `ConfigurationError` with FR-002 message
- [x] T009 [P] [US2] Write test `test_validate_census_whitespace_only` in `tests/test_census_validation.py` — pass config `{"setup": {"census_parquet_path": "   "}}`, assert raises `ConfigurationError` with FR-002 message
- [x] T010 [P] [US2] Write test `test_validate_census_none_value` in `tests/test_census_validation.py` — pass config `{"setup": {"census_parquet_path": None}}`, assert raises `ConfigurationError` with FR-002 message
- [x] T011 [P] [US2] Write test `test_validate_census_error_context` in `tests/test_census_validation.py` — assert raised `ConfigurationError` has `context` with `metadata` containing `missing_field: "setup.census_parquet_path"` per data-model.md validation contract

### Implementation for User Story 1 & 2

- [x] T012 [US1] [US2] Update `_validate_census()` method signature in `planalign_api/services/simulation/service.py` — add `scenario_id: str = ""` and `workspace_id: str = ""` parameters. Remove `@staticmethod` decorator (or keep static with new params). Update call site in `_prepare_simulation()` (line 147) to pass `workspace_id` and `scenario_id` from its own parameters.
- [x] T013 [US1] [US2] Replace `_validate_census()` body in `planalign_api/services/simulation/service.py` — remove silent fallback `else` clause (lines 411-412), add check: if `census_parquet_path` is missing/None/empty/whitespace-only, raise `ConfigurationError` with FR-002 message and `ExecutionContext(scenario_id=scenario_id, metadata={"missing_field": "setup.census_parquet_path", "workspace_id": workspace_id})`. Keep existing `logger.info` for valid path success case.
- [x] T014 [US1] [US2] Add imports to `planalign_api/services/simulation/service.py` — import `ConfigurationError`, `ExecutionContext`, `ErrorSeverity` from `planalign_orchestrator.exceptions` (move from inline import to top-level if not already present)
- [x] T015 [US1] [US2] Run tests: `pytest tests/test_census_validation.py -k "missing_key or empty_string or whitespace or none_value or valid_path or error_context" -v` — all 6 tests must pass (Green phase)

**Checkpoint**: US1 & US2 complete — valid census file simulations succeed; missing census file raises immediate, actionable ConfigurationError

---

## Phase 4: User Story 3 — Invalid Census File Path Handling (Priority: P2)

**Goal**: Validate that the census file exists on the filesystem at the configured path. If the file has been deleted or the path is wrong, raise a clear error with the path included.

**Independent Test**: Configure a `census_parquet_path` pointing to a non-existent file → immediate ConfigurationError with path in message and FR-004 guidance.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T016 [P] [US3] Write test `test_validate_census_file_not_found` in `tests/test_census_validation.py` — pass config with `census_parquet_path: "/nonexistent/path/census.parquet"`, assert raises `ConfigurationError` with message matching FR-004: "Census file not found at '/nonexistent/path/census.parquet'"
- [x] T017 [P] [US3] Write test `test_validate_census_file_not_found_includes_path` in `tests/test_census_validation.py` — assert error message contains the actual configured path string for debugging
- [x] T018 [P] [US3] Write test `test_validate_census_file_not_found_context` in `tests/test_census_validation.py` — assert raised `ConfigurationError` has `context` with `metadata` containing `expected_path` and `scenario_id` per data-model.md contract

### Implementation for User Story 3

- [x] T019 [US3] Update `_validate_census()` in `planalign_api/services/simulation/service.py` — replace existing `ValueError` raise (line 409) with `ConfigurationError` using FR-004 message: `f"Census file not found at '{census_path}'. Upload a valid census parquet file to the scenario folder and retry."` and `ExecutionContext(scenario_id=scenario_id, metadata={"expected_path": str(census_path), "workspace_id": workspace_id})`
- [x] T020 [US3] Run tests: `pytest tests/test_census_validation.py -k "file_not_found" -v` — all 3 tests must pass (Green phase)

**Checkpoint**: US3 complete — non-existent census file paths raise immediate, actionable ConfigurationError with path in message

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Ensure all tests pass together, verify audit logging, validate against quickstart.md checklist

- [x] T021 Run full test suite: `pytest tests/test_census_validation.py -v --tb=short` — all 10 tests must pass
- [x] T022 [P] Verify FR-005 compliance: grep `planalign_api/services/simulation/service.py` for any remaining fallback/default census path logic — must find zero instances
- [x] T023 [P] Verify FR-007 compliance: confirm `logger.info` logs census path on success and `ConfigurationError` context includes `scenario_id` and `workspace_id` metadata for audit trail
- [x] T024 Run quickstart.md validation checklist: verify error messages match FR-002 and FR-004 exactly, no `ValueError` remains, `ConfigurationError` used consistently

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — read-only verification
- **Foundational (Phase 2)**: No code dependencies on Phase 1 (can start immediately), but Phase 1 confirms insertion points
- **User Story 1 & 2 (Phase 3)**: Depends on Phase 2 for error catalog entries; tests written first per Constitution III
- **User Story 3 (Phase 4)**: Depends on Phase 3 (builds on `_validate_census()` changes from US1/US2); T019 adds file-not-found branch to method already modified in T013
- **Polish (Phase 5)**: Depends on Phases 3 and 4

### User Story Dependencies

- **US1 & US2 (P1)**: Combined because they modify the same method (`_validate_census()`) — US1 is the happy path, US2 is the missing-path error path. T012 changes method signature (adds `scenario_id`, `workspace_id` params and updates call site). Can start after Phase 2.
- **US3 (P2)**: Builds on the `_validate_census()` method modified in US1/US2. Must follow Phase 3.

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Constitution III)
- Implementation modifies `_validate_census()` to pass the tests
- Verification run confirms all tests pass

### Parallel Opportunities

**Phase 1** (all parallel):
```
T001 | T002 | T003  (all read-only, different files)
```

**Phase 2** (parallel):
```
T004 | T005  (different error patterns, same file but different insertion points)
```

**Phase 3 tests** (all parallel):
```
T006 | T007 | T008 | T009 | T010 | T011  (all write to same test file but independent test functions)
```

**Phase 4 tests** (all parallel):
```
T016 | T017 | T018  (independent test functions)
```

**Phase 5 verification** (parallel where marked):
```
T022 | T023  (different verification targets)
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2)

1. Complete Phase 1: Setup (verify existing code)
2. Complete Phase 2: Foundational (error catalog entries)
3. Complete Phase 3: User Stories 1 & 2 (tests → implementation → verify)
4. **STOP and VALIDATE**: Run `pytest tests/test_census_validation.py -v` — 6 tests pass
5. MVP delivers: valid census → success; missing census → actionable error

### Incremental Delivery

1. Setup + Foundational → Infrastructure ready
2. US1 & US2 → Test independently → MVP complete
3. US3 → Test independently → Full feature complete
4. Polish → All 10 tests pass, compliance verified

### Key Files Modified

| File | Phase | Change |
|------|-------|--------|
| `planalign_orchestrator/error_catalog.py` | 2 | Add 2 error patterns with resolution hints |
| `tests/test_census_validation.py` | 3, 4 | New file: 10 test cases |
| `planalign_api/services/simulation/service.py` | 3, 4 | Update `_validate_census()` signature (add scenario_id/workspace_id), remove fallback, add ConfigurationError |

---

## Notes

- [P] tasks = different files or independent functions, no dependencies
- [Story] label maps task to specific user story for traceability
- US1 & US2 are combined in Phase 3 because they modify the same method and are both P1
- US3 is separated because it builds on the Phase 3 changes
- All error messages must match FR-002 and FR-004 **exactly** (string constants, not paraphrased)
- Test file named `test_census_validation.py` (not `test_simulation_service.py`) to keep tests focused on this feature
