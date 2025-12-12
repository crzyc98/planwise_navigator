# Tasks: Unified Database Path Resolver

**Input**: Design documents from `/specs/005-database-path-resolver/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are included as this is infrastructure code requiring high coverage (SC-006: 95%+) per the success criteria.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Based on plan.md structure:
- Source: `planalign_api/services/`, `planalign_api/models/`
- Tests: `tests/unit/`, `tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project structure verification and test infrastructure setup

- [x] T001 Verify existing project structure matches plan.md in planalign_api/services/
- [x] T002 [P] Create test fixtures directory structure at tests/fixtures/ if not exists
- [x] T003 [P] Verify pytest configuration supports fast marker for unit tests in pyproject.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core resolver components that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create IsolationMode enum in planalign_api/services/database_path_resolver.py
- [x] T005 Create ResolvedDatabasePath Pydantic model in planalign_api/services/database_path_resolver.py
- [x] T006 Create WorkspaceStorageProtocol in planalign_api/services/database_path_resolver.py
- [x] T007 Create DatabasePathResolver class skeleton with __init__ in planalign_api/services/database_path_resolver.py
- [x] T008 Implement _validate_identifier method for path traversal prevention in planalign_api/services/database_path_resolver.py
- [x] T009 Implement _detect_project_root method in planalign_api/services/database_path_resolver.py
- [x] T010 Add module exports to planalign_api/services/__init__.py

**Checkpoint**: Foundation ready - DatabasePathResolver class exists with supporting types

---

## Phase 3: User Story 1 - API Developer Injects Resolver (Priority: P1) 🎯 MVP

**Goal**: Complete resolver implementation with fallback chain; refactor all three services to use it

**Independent Test**: Verify resolver returns same paths as original inline implementations in all three services

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T011 [P] [US1] Unit test: scenario-level resolution in tests/unit/test_database_path_resolver.py
- [x] T012 [P] [US1] Unit test: workspace-level fallback in tests/unit/test_database_path_resolver.py
- [x] T013 [P] [US1] Unit test: project-level fallback with warning in tests/unit/test_database_path_resolver.py
- [x] T014 [P] [US1] Unit test: path traversal rejection in tests/unit/test_database_path_resolver.py
- [x] T015 [P] [US1] Unit test: not found returns None in tests/unit/test_database_path_resolver.py

### Implementation for User Story 1

- [x] T016 [US1] Implement resolve() method core fallback chain in planalign_api/services/database_path_resolver.py
- [x] T017 [US1] Add logging for fallback warnings in planalign_api/services/database_path_resolver.py
- [x] T018 [US1] Refactor AnalyticsService to inject and use DatabasePathResolver in planalign_api/services/analytics_service.py
- [x] T019 [US1] Refactor ComparisonService to inject and use DatabasePathResolver in planalign_api/services/comparison_service.py
- [x] T020 [US1] Refactor SimulationService.get_results to use DatabasePathResolver in planalign_api/services/simulation_service.py
- [x] T021 [US1] Remove duplicated _get_database_path methods from all three services
- [x] T022 [US1] Update service instantiation in routers to pass resolver (or use default)

**Checkpoint**: All three services use resolver; backward compatibility verified

---

## Phase 4: User Story 2 - Test Author Validates Path Resolution in Isolation (Priority: P2)

**Goal**: Comprehensive unit test suite using mocks; verify <100ms execution

**Independent Test**: Run `pytest -m fast tests/unit/test_database_path_resolver.py` completes in <100ms

### Tests for User Story 2

- [x] T023 [P] [US2] Unit test: mock WorkspaceStorage with scenario path returns scenario db in tests/unit/test_database_path_resolver.py
- [x] T024 [P] [US2] Unit test: mock storage fallback to workspace level in tests/unit/test_database_path_resolver.py
- [x] T025 [P] [US2] Unit test: mock storage fallback to project level in tests/unit/test_database_path_resolver.py
- [x] T026 [P] [US2] Unit test: configurable project_root override in tests/unit/test_database_path_resolver.py

### Implementation for User Story 2

- [x] T027 [US2] Create MockWorkspaceStorage fixture in tests/fixtures/mock_storage.py
- [x] T028 [US2] Add pytest.mark.fast to all resolver unit tests in tests/unit/test_database_path_resolver.py
- [x] T029 [US2] Verify all unit tests run without filesystem I/O using tmpdir fixtures in tests/unit/test_database_path_resolver.py
- [x] T030 [US2] Add timing assertion to test suite confirming <100ms execution in tests/unit/test_database_path_resolver.py

**Checkpoint**: Full test coverage with mocks; tests run in <100ms

---

## Phase 5: User Story 3 - Operator Configures Multi-Tenant Isolation (Priority: P3)

**Goal**: Add multi-tenant isolation mode that prevents project-level fallback

**Independent Test**: Resolver with MULTI_TENANT mode returns None when workspace db missing

### Tests for User Story 3

- [x] T031 [P] [US3] Unit test: MULTI_TENANT mode stops at workspace level in tests/unit/test_database_path_resolver.py
- [x] T032 [P] [US3] Unit test: SINGLE_TENANT mode allows project fallback (default) in tests/unit/test_database_path_resolver.py
- [x] T033 [P] [US3] Unit test: isolation_mode enum validation in tests/unit/test_database_path_resolver.py

### Implementation for User Story 3

- [x] T034 [US3] Add isolation_mode check to resolve() method in planalign_api/services/database_path_resolver.py
- [x] T035 [US3] Add integration test for multi-tenant isolation in tests/integration/test_database_path_resolver_integration.py
- [x] T036 [US3] Document multi-tenant configuration in quickstart.md

**Checkpoint**: Multi-tenant mode works; isolation is enforced

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, and cleanup

- [x] T037 [P] Verify zero code duplication by grepping for old fallback pattern
- [x] T038 [P] Run existing API integration tests to confirm backward compatibility
- [x] T039 [P] Add docstrings to all public methods in planalign_api/services/database_path_resolver.py
- [x] T040 [P] Update CLAUDE.md with DatabasePathResolver usage patterns if needed
- [x] T041 Run coverage report and verify 95%+ for DatabasePathResolver
- [x] T042 Run full test suite: pytest -m fast (should be <10s per constitution)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can then proceed in priority order (P1 → P2 → P3)
  - Or in parallel if staffed
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - Core implementation
- **User Story 2 (P2)**: Can start after US1 - Adds comprehensive test coverage
- **User Story 3 (P3)**: Can start after Foundational - Isolation mode is additive

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Resolver implementation before service refactoring
- Service refactoring one at a time (Analytics → Comparison → Simulation)
- Verify backward compatibility after each service change

### Parallel Opportunities

Within Phase 2 (Foundational):
- T004, T005, T006 can run in parallel (different components, same file sections)

Within User Story 1:
- T011-T015 (all unit tests) can run in parallel
- T018, T019, T020 (service refactors) can run in parallel after T016-T017

Within User Story 2:
- T023-T026 (all mock tests) can run in parallel

Within User Story 3:
- T031-T033 (all isolation tests) can run in parallel

Within Phase 6 (Polish):
- T037, T038, T039, T040 can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 unit tests in parallel:
Task: "Unit test: scenario-level resolution in tests/unit/test_database_path_resolver.py"
Task: "Unit test: workspace-level fallback in tests/unit/test_database_path_resolver.py"
Task: "Unit test: project-level fallback with warning in tests/unit/test_database_path_resolver.py"
Task: "Unit test: path traversal rejection in tests/unit/test_database_path_resolver.py"
Task: "Unit test: not found returns None in tests/unit/test_database_path_resolver.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (3 tasks)
2. Complete Phase 2: Foundational (7 tasks) - CRITICAL
3. Complete Phase 3: User Story 1 (12 tasks)
4. **STOP and VALIDATE**: All three services use resolver; existing tests pass
5. Deploy/demo if ready - this delivers SC-001, SC-002, SC-005

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready (10 tasks)
2. Add User Story 1 → Test independently → Deploy (12 tasks) - **MVP!**
3. Add User Story 2 → Test independently → Achieves SC-003, SC-006 (8 tasks)
4. Add User Story 3 → Test independently → Enables multi-tenant (6 tasks)
5. Polish phase → Final validation (6 tasks)

### Total Task Count

| Phase | Tasks | Cumulative |
|-------|-------|------------|
| Phase 1: Setup | 3 | 3 |
| Phase 2: Foundational | 7 | 10 |
| Phase 3: US1 (MVP) | 12 | 22 |
| Phase 4: US2 | 8 | 30 |
| Phase 5: US3 | 6 | 36 |
| Phase 6: Polish | 6 | 42 |

---

## Notes

- [P] tasks = different files or file sections, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- SC-003 requires <100ms unit tests - use mocks, avoid real filesystem I/O
- SC-006 requires 95%+ coverage - include edge cases in tests
