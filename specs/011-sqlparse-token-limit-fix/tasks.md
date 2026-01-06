# Tasks: SQLParse Token Limit Fix

**Input**: Design documents from `/specs/011-sqlparse-token-limit-fix/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, quickstart.md

**Tests**: Tests ARE requested - Constitution Check mentions "Test-First Development" and plan.md specifies test files.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: This is a Python project with `planalign_orchestrator/`, `scripts/`, `tests/` at repository root
- Paths follow existing codebase structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the core sqlparse configuration module and install script

- [X] T001 [P] Create sqlparse configuration module in planalign_orchestrator/sqlparse_config.py
- [X] T002 [P] Create install script in scripts/install_sqlparse_fix.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Install .pth file and verify configuration works

**CRITICAL**: No user story verification can succeed until this phase is complete

- [X] T003 Run install script to create .pth file in venv site-packages
- [X] T004 Verify sqlparse MAX_GROUPING_TOKENS is set to 50000 in Python interpreter

**Checkpoint**: Foundation ready - sqlparse is configured for all Python processes in venv

---

## Phase 3: User Story 1 - Multi-Year Simulation (Priority: P1) MVP

**Goal**: Enable multi-year simulations (2025-2027) to complete without token limit errors

**Independent Test**: Run `planalign simulate 2025-2027 --verbose` and verify all three years complete successfully

### Tests for User Story 1

- [X] T005 [P] [US1] Create unit test for sqlparse configuration in tests/unit/test_sqlparse_config.py
- [X] T006 [P] [US1] Create integration test for subprocess dbt execution in tests/integration/test_sqlparse_subprocess.py

### Implementation for User Story 1

- [X] T007 [US1] Update planalign_orchestrator/__init__.py to import sqlparse_config module (defense-in-depth)
- [X] T008 [US1] Run tests to verify .pth file is loaded in dbt subprocess
- [X] T009 [US1] Run multi-year simulation test: planalign simulate 2025-2027 --verbose

**Checkpoint**: At this point, User Story 1 should be fully functional - multi-year simulations work

---

## Phase 4: User Story 2 - Direct dbt Commands (Priority: P2)

**Goal**: Enable direct dbt commands to work without token limit errors

**Independent Test**: Run `cd dbt && dbt run --select fct_workforce_snapshot --vars '{"simulation_year": 2026}' --threads 1`

### Implementation for User Story 2

- [X] T010 [US2] Verify dbt command works from dbt directory for Year 2026 simulation
- [X] T011 [US2] Verify dbt command works for Year 2027 (additional temporal complexity)

**Checkpoint**: At this point, both orchestrator AND direct dbt commands work

---

## Phase 5: User Story 3 - Batch Scenario Processing (Priority: P2)

**Goal**: Enable batch scenario processing to complete all years across multiple scenarios

**Independent Test**: Run `planalign batch --scenarios baseline` and verify all years complete

### Implementation for User Story 3

- [X] T012 [US3] Verify batch scenario processing works with single scenario (baseline)
- [ ] T013 [US3] (Optional) Verify batch processing works with multiple scenarios if available

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation updates and cleanup

- [X] T014 [P] Update CLAUDE.md troubleshooting section with sqlparse token limit fix
- [ ] T015 [P] Update pyproject.toml to include post-install reminder (optional)
- [X] T016 Run existing test suite to verify no regressions: pytest -m fast
- [X] T017 Run quickstart.md validation to verify fix instructions work

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user story verification
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - US1 can start after Foundational
  - US2 depends on US1 (same .pth file, but different verification)
  - US3 depends on US1 (batch processing uses same infrastructure)
- **Polish (Phase 6)**: Depends on all user stories being verified

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - Core fix verification
- **User Story 2 (P2)**: Can start after US1 - Verifies fix works for direct dbt commands
- **User Story 3 (P2)**: Can start after US1 - Verifies fix works for batch processing

### Within Each Phase

- T001 and T002 are parallel (different files)
- T005 and T006 are parallel (different test files)
- T010 and T011 are sequential (Year 2027 tests more complex scenario)

### Parallel Opportunities

**In Setup (Phase 1)**:
```bash
# These can run in parallel:
Task T001: "Create sqlparse configuration module in planalign_orchestrator/sqlparse_config.py"
Task T002: "Create install script in scripts/install_sqlparse_fix.py"
```

**In User Story 1 Tests**:
```bash
# These can run in parallel:
Task T005: "Create unit test in tests/unit/test_sqlparse_config.py"
Task T006: "Create integration test in tests/integration/test_sqlparse_subprocess.py"
```

**In Polish (Phase 6)**:
```bash
# These can run in parallel:
Task T014: "Update CLAUDE.md troubleshooting section"
Task T015: "Update pyproject.toml post-install reminder"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T004)
3. Complete Phase 3: User Story 1 (T005-T009)
4. **STOP and VALIDATE**: Run `planalign simulate 2025-2027 --verbose`
5. If successful, fix is complete for core use case

### Incremental Delivery

1. Complete Setup + Foundational  Foundation ready
2. Add User Story 1  Test with multi-year simulation  MVP complete
3. Add User Story 2  Test with direct dbt commands  Developer workflow verified
4. Add User Story 3  Test with batch processing  Full workflow verified
5. Add Polish  Documentation and cleanup

### Estimated Task Count

- **Total tasks**: 17
- **Phase 1 (Setup)**: 2 tasks
- **Phase 2 (Foundational)**: 2 tasks
- **Phase 3 (US1)**: 5 tasks
- **Phase 4 (US2)**: 2 tasks
- **Phase 5 (US3)**: 2 tasks
- **Phase 6 (Polish)**: 4 tasks

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (T005, T006)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- The fix is relatively small (2 new files) but verification is critical
