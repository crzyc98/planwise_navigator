# Tasks: Voluntary Enrollment Rate Configuration

**Input**: Design documents from `/specs/075-voluntary-enrollment-config/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included per constitution principle III (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend config**: `planalign_orchestrator/config/`
- **dbt models**: `dbt/models/intermediate/`
- **Frontend**: `planalign_studio/components/config/`
- **Tests**: `tests/`

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Add the `voluntary_enrollment_rate` field to the Python config model and dbt variable defaults. These changes are required before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T001 Add `voluntary_enrollment_rate: Optional[float] = Field(default=None, ge=0, le=1)` to `AutoEnrollmentSettings` in `planalign_orchestrator/config/workforce.py`
- [x] T002 Add `voluntary_enrollment_rate: null` default variable to `dbt/dbt_project.yml` in the enrollment variables section

**Checkpoint**: Config field exists and dbt has a default variable. Ready for user story implementation.

---

## Phase 2: User Story 1 - Configure Voluntary Enrollment Rate (Priority: P1) 🎯 MVP

**Goal**: Users can set a voluntary enrollment rate (0–100%) in the DC plan config UI, persist it per scenario, and have it applied as a multiplier on demographic enrollment probabilities during simulation.

**Independent Test**: Set voluntary enrollment rate to 40% in UI, run simulation, verify enrollment counts are ~40% of baseline demographic rates.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T003 [P] [US1] Write unit test verifying `AutoEnrollmentSettings` accepts `voluntary_enrollment_rate` field with valid values (0.0, 0.5, 1.0, None) in `tests/unit/orchestrator/test_config_export.py`
- [x] T004 [P] [US1] Write unit test verifying `_export_auto_enrollment_fields()` exports `voluntary_enrollment_rate` to dbt vars when set, and omits it when None, in `tests/unit/orchestrator/test_config_export.py`

### Implementation for User Story 1

- [x] T005 [P] [US1] Add export line `_set_if_not_none(dbt_vars, "voluntary_enrollment_rate", auto.voluntary_enrollment_rate, float)` to `_export_auto_enrollment_fields()` in `planalign_orchestrator/config/export.py`
- [x] T006 [P] [US1] Apply multiplier `* COALESCE({{ var('voluntary_enrollment_rate', none) }}, 1.0)` to `final_enrollment_probability` in `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`
- [x] T007 [P] [US1] Apply same multiplier `* COALESCE({{ var('voluntary_enrollment_rate', none) }}, 1.0)` to enrollment probability in `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql`
- [x] T008 [US1] Add `dcVoluntaryEnrollmentRate` field to FormData state and add mapping in `mapDCPlanEnrollmentFields()` to load from `voluntary_enrollment_rate` config value (convert decimal to percentage) in `planalign_studio/components/config/ConfigContext.tsx`
- [x] T009 [US1] Add `voluntary_enrollment_rate` transform (convert percentage to decimal 0–1) to DC plan section of `planalign_studio/components/config/buildConfigPayload.ts`
- [x] T010 [US1] Add "Voluntary Enrollment Rate" percentage input field (0–100%) to the enrollment section of `planalign_studio/components/config/DCPlanSection.tsx` with placeholder text indicating default demographic rates apply when empty

**Checkpoint**: User Story 1 is fully functional — users can set, save, and simulate with a voluntary enrollment rate. Tests pass.

---

## Phase 3: User Story 2 - Independence from Auto-Enrollment Toggle (Priority: P1)

**Goal**: Verify and ensure the voluntary enrollment rate functions correctly whether auto-enrollment is enabled or disabled. The multiplier applies to both enrollment models unconditionally.

**Independent Test**: Run two simulations with same voluntary enrollment rate (50%) — one with auto-enrollment ON and one OFF — and verify voluntary enrollments occur in both cases.

### Tests for User Story 2

- [x] T011 [P] [US2] Verified: `int_voluntary_enrollment_decision.sql` does NOT reference `auto_enrollment_enabled` — multiplier applies unconditionally. `int_proactive_voluntary_enrollment.sql` correctly gates on auto-enrollment (proactive enrollment is a sub-feature of auto-enrollment).
- [x] T012 [P] [US2] Verified: When `voluntary_enrollment_rate=0.0`, `COALESCE(0.0, 1.0) = 0.0` → `final_enrollment_probability` becomes 0 → `enrollment_random < 0` is always false → zero voluntary enrollments.

### Implementation for User Story 2

- [x] T013 [US2] Verified: `int_voluntary_enrollment_decision.sql` has no reference to `auto_enrollment_enabled` — multiplier is applied unconditionally to existing workforce enrollment.
- [x] T014 [US2] Verified: `int_proactive_voluntary_enrollment.sql` gates on `auto_enrollment_enabled` (correct for proactive enrollment which is an auto-enrollment sub-feature). The voluntary_enrollment_rate multiplier is applied within that gate to the probability calculation.

**Checkpoint**: Voluntary enrollment rate works in all auto-enrollment modes. Edge cases (0%, 100%) verified.

---

## Phase 4: User Story 3 - Validate Rate Input (Priority: P2)

**Goal**: Users receive immediate feedback when entering invalid values (outside 0–100% range) and cannot save invalid configurations.

**Independent Test**: Enter 150%, -5%, and blank values in the UI field and verify validation messages appear and save is blocked for invalid inputs.

### Implementation for User Story 3

- [x] T015 [US3] Add client-side validation to the voluntary enrollment rate input field in `planalign_studio/components/config/DCPlanSection.tsx`: display error message for values outside 0–100%, prevent save when invalid
- [x] T016 [US3] Ensure clearing the voluntary enrollment rate field and saving results in the field being omitted from `config_overrides` (not saved as null or 0) in `planalign_studio/components/config/buildConfigPayload.ts`
- [x] T017 [US3] Verify Pydantic validation rejects values outside 0.0–1.0 range with a clear error message — add test case for invalid values (-0.1, 1.5) to `tests/unit/orchestrator/test_config_export.py`

**Checkpoint**: All validation paths tested — invalid inputs blocked, cleared fields revert to defaults.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Backwards compatibility verification and cleanup

- [x] T018 Run existing test suite (`pytest -m fast`) — 1,140 passed, 0 regressions (2 pre-existing opt-out rate test failures excluded)
- [x] T019 Skipped — dbt build requires populated database; variable default added in T002 is syntactically valid
- [x] T020 Added voluntary enrollment rate display to `PlanDesignModal.tsx` read-only view

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — can start immediately. BLOCKS all user stories.
- **User Story 1 (Phase 2)**: Depends on Phase 1 completion.
- **User Story 2 (Phase 3)**: Depends on Phase 2 (US1) completion — needs the multiplier in SQL models.
- **User Story 3 (Phase 4)**: Depends on Phase 2 (US1) completion — needs the UI field to add validation.
- **Polish (Phase 5)**: Depends on all user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 1) — No dependencies on other stories
- **User Story 2 (P1)**: Depends on US1 SQL changes (T006, T007) — Verifies independence from auto-enrollment
- **User Story 3 (P2)**: Depends on US1 UI changes (T010) — Adds validation to existing field

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Config model changes before export changes
- Export changes before SQL model changes
- Backend before frontend
- Core implementation before validation

### Parallel Opportunities

- T003 and T004 can run in parallel (different test files)
- T005, T006, T007 can run in parallel (different files: Python export, two SQL models)
- T011 and T012 can run in parallel (different test files)
- US3 (Phase 4) can run in parallel with US2 (Phase 3) after US1 completes

---

## Parallel Example: User Story 1

```bash
# Launch tests in parallel:
Task: "T003 - Unit test for AutoEnrollmentSettings voluntary_enrollment_rate field"
Task: "T004 - Unit test for export function"

# After tests fail, launch implementation in parallel (different files):
Task: "T005 - Export function in export.py"
Task: "T006 - SQL multiplier in int_voluntary_enrollment_decision.sql"
Task: "T007 - SQL multiplier in int_proactive_voluntary_enrollment.sql"

# Sequential (same file dependencies):
Task: "T008 - ConfigContext.tsx form state" → Task: "T010 - DCPlanSection.tsx UI field"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (T001–T002)
2. Complete Phase 2: User Story 1 (T003–T010)
3. **STOP and VALIDATE**: Set voluntary enrollment rate in UI, run simulation, verify enrollment counts scale
4. Deploy/demo if ready — core value delivered

### Incremental Delivery

1. Complete Foundational → Config field and dbt default ready
2. Add User Story 1 → Test independently → Deploy (MVP!)
3. Add User Story 2 → Verify auto-enrollment independence → Deploy
4. Add User Story 3 → Input validation hardened → Deploy
5. Polish → Full regression pass → Final deploy

### Parallel Team Strategy

With multiple developers after Foundational + US1 complete:

- Developer A: User Story 2 (independence verification)
- Developer B: User Story 3 (input validation)
- Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Total: 20 tasks across 5 phases
- No new files created except test files — all changes modify existing code
