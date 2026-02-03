# Tasks: Fix Vesting Analytics Endpoint AttributeError

**Input**: Design documents from `/specs/029-fix-vesting-endpoint/`
**Prerequisites**: plan.md, spec.md, research.md

**Tests**: Not explicitly requested. Existing tests will validate the fix.

**Organization**: Tasks organized by user story for this minimal bug fix.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No setup required - this is a bug fix in existing code

*(No tasks - project already initialized)*

---

## Phase 2: Foundational

**Purpose**: No foundational work required - existing infrastructure supports the fix

*(No tasks - all infrastructure exists)*

**Checkpoint**: Ready for bug fix implementation

---

## Phase 3: User Story 1 - Vesting Analysis Request (Priority: P1) MVP

**Goal**: Fix the AttributeError so users can successfully request vesting analysis

**Independent Test**: POST to `/api/workspaces/{workspace_id}/scenarios/{scenario_id}/analytics/vesting` returns 200 OK instead of 500

### Implementation for User Story 1

- [x] T001 [US1] Fix Pydantic attribute access in planalign_api/routers/vesting.py:70 - change `scenario.get("name", scenario_id)` to `scenario.name or scenario_id`

**Checkpoint**: Vesting analysis endpoint returns 200 OK for valid requests

---

## Phase 4: User Story 2 - Error Handling for Missing Data (Priority: P2)

**Goal**: Verify existing error handling still works correctly after the fix

**Independent Test**: Invalid workspace/scenario IDs return appropriate 404 errors

### Verification for User Story 2

- [x] T002 [US2] Verify 404 responses still work by running existing tests in tests/integration/test_vesting_api.py

**Checkpoint**: Error handling unchanged - 404 responses work correctly

---

## Phase 5: Polish & Validation

**Purpose**: Final verification that the fix is complete

- [x] T003 Run full vesting API test suite: `pytest tests/integration/test_vesting_api.py tests/unit/test_vesting_service.py -v`
- [x] T004 Manual verification: Verified Scenario model has `name: str` attribute and endpoint code uses correct attribute access (`scenario.name or scenario_id`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: N/A - no setup needed
- **Foundational (Phase 2)**: N/A - no foundational work needed
- **User Story 1 (Phase 3)**: Can start immediately - single task
- **User Story 2 (Phase 4)**: Depends on T001 completion - verification only
- **Polish (Phase 5)**: Depends on T001 and T002 completion

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies - can execute immediately
- **User Story 2 (P2)**: Depends on US1 completion (verifies fix doesn't break error handling)

### Task Execution Flow

```
T001 (Fix bug) → T002 (Verify error handling) → T003 (Run tests) → T004 (Manual test)
```

---

## Implementation Strategy

### MVP (User Story 1 Only)

1. Complete T001: Fix the Pydantic attribute access bug
2. **VALIDATE**: Endpoint returns 200 OK for valid requests
3. Done - critical bug is fixed

### Full Validation

1. Complete T001 (bug fix)
2. Complete T002 (verify error handling)
3. Complete T003 (run test suite)
4. Complete T004 (manual verification)
5. Ready for merge

---

## Notes

- This is a minimal 1-line bug fix
- No new tests required - existing tests validate the fix
- Total tasks: 4 (1 implementation, 3 verification)
- No parallel opportunities - tasks are sequential
- Estimated effort: Trivial (<5 minutes implementation)
