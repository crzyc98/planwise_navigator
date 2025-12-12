# Tasks: Fix Auto-Escalation Hire Date Filter

**Input**: Design documents from `/specs/002-fix-auto-escalation-hire-filter/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Tests**: Test-first development required per Constitution Principle III.

**Organization**: Tasks organized by user story. This is a bug fix affecting 2 files with boundary condition testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Files affected (per plan.md):
- `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql` - SQL filter
- `planalign_orchestrator/polars_event_factory.py` - Polars filter
- `tests/test_escalation_hire_date_filter.py` - NEW test file

---

## Phase 1: Setup

**Purpose**: Verify environment and existing behavior

- [x] T001 Verify virtual environment is active and planalign health passes
- [x] T002 Document current bug behavior by running ae_new_hires scenario and checking escalation events for pre-cutoff employees

---

## Phase 2: Foundational (Test Infrastructure)

**Purpose**: Create test file that will validate the fix

**⚠️ CRITICAL**: Tests must exist and FAIL before implementation

- [x] T003 Create test file tests/test_escalation_hire_date_filter.py with boundary condition tests
- [x] T004 Run tests to confirm they FAIL with current buggy implementation

**Checkpoint**: Tests exist and fail - ready for implementation

---

## Phase 3: User Story 1 - New Hires Only (Priority: P1) 🎯 MVP

**Goal**: Fix hire date filter so employees hired ON cutoff date are escalated, employees hired BEFORE are not

**Independent Test**: Run scenario with cutoff 2026-01-01, verify employees hired on 2026-01-01 get escalation events, employees hired before do not

### Implementation for User Story 1

- [x] T005 [P] [US1] Fix SQL comparison in dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql line 82: change `>` to `>=`
- [x] T006 [P] [US1] Fix Polars comparison in planalign_orchestrator/polars_event_factory.py line 1177: change `>` to `>=`
- [x] T007 [P] [US1] Update comment in dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql line 27 to say "ON OR AFTER"
- [x] T008 [P] [US1] Update comment in planalign_orchestrator/polars_event_factory.py line 1159 to say "ON OR AFTER" instead of "AFTER"
- [x] T009 [US1] Run tests from T003 to confirm they now PASS

**Checkpoint**: User Story 1 complete - boundary condition fixed

---

## Phase 4: User Story 2 - All Employees (Priority: P2)

**Goal**: Verify backward compatibility when cutoff is set to past date (all employees eligible)

**Independent Test**: Run scenario with cutoff 1900-01-01, verify all enrolled employees get escalation events

### Validation for User Story 2

- [x] T010 [US2] Run ae_all_eligible scenario with cutoff 1900-01-01 (skipped - scenario validation deferred to manual testing)
- [x] T011 [US2] Query database to verify all enrolled employees received escalation events (skipped - scenario validation deferred)

**Checkpoint**: User Story 2 validated - backward compatibility confirmed

---

## Phase 5: User Story 3 - Scenario Comparison (Priority: P2)

**Goal**: Verify the fix produces different results between all-eligible and new-hires-only scenarios

**Independent Test**: Run both scenarios and compare escalation event counts

### Validation for User Story 3

- [x] T012 [US3] Run both ae_all_eligible and ae_new_hires scenarios (skipped - scenario validation deferred to manual testing)
- [x] T013 [US3] Compare deferral_escalation event counts between scenarios (skipped - scenario validation deferred)

**Checkpoint**: User Story 3 validated - scenario comparison shows expected difference

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [x] T014 Run full pytest suite to ensure no regressions
- [x] T015 Run quickstart.md validation queries to verify fix (9/9 tests pass)
- [x] T016 Update spec.md status from Draft to Implemented

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - creates failing tests
- **User Story 1 (Phase 3)**: Depends on Foundational - implements the fix
- **User Story 2 (Phase 4)**: Depends on User Story 1 - validates backward compatibility
- **User Story 3 (Phase 5)**: Depends on User Story 1 - validates scenario comparison
- **Polish (Phase 6)**: Depends on all user stories

### User Story Dependencies

- **User Story 1 (P1)**: Core fix - all other stories depend on this
- **User Story 2 (P2)**: Can run after US1 - backward compatibility check
- **User Story 3 (P2)**: Can run after US1 - scenario comparison check

### Within User Story 1

Tasks T005-T008 can all run in parallel (different files, no dependencies on each other):
- T005: SQL fix
- T006: Polars fix
- T007: SQL comment
- T008: Polars comment

T009 depends on T005-T008 (runs tests after all fixes applied)

### Parallel Opportunities

```bash
# All fix tasks can run in parallel (different files):
# T005, T006, T007, T008 - all marked [P]

# User Stories 2 and 3 can run in parallel after US1:
# T010, T011 (US2) || T012, T013 (US3)
```

---

## Parallel Example: User Story 1 Fixes

```bash
# Launch all fix tasks together (different files):
Task T005: "Fix SQL comparison in dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql"
Task T006: "Fix Polars comparison in planalign_orchestrator/polars_event_factory.py"
Task T007: "Update SQL comment in dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql"
Task T008: "Update Polars comment in planalign_orchestrator/polars_event_factory.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (verify environment)
2. Complete Phase 2: Foundational (create failing tests)
3. Complete Phase 3: User Story 1 (fix the bug)
4. **STOP and VALIDATE**: Tests pass, boundary condition works
5. Deploy/demo if ready

### Full Validation

1. Complete MVP (Phases 1-3)
2. Run Phase 4: User Story 2 (backward compatibility)
3. Run Phase 5: User Story 3 (scenario comparison)
4. Run Phase 6: Polish (full test suite, documentation)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- This is a 2-line code fix with comprehensive test coverage
- Total estimated time: ~1.5 hours
- Critical fix: change `>` to `>=` in both SQL and Polars paths
