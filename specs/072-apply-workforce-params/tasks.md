# Tasks: Apply Workforce Parameters Across Scenarios

**Input**: Design documents from `/specs/072-apply-workforce-params/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. No test tasks generated.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project setup needed — all packages and directories already exist.

*(No tasks — existing project structure is sufficient)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic models and workforce parameter extraction logic shared by all user stories.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T001 Add `WorkforceParamsApplyRequest`, `ScenarioApplyOutcome`, and `WorkforceParamsApplyResult` Pydantic v2 models to `planalign_api/models/scenario.py`. Request model has `target_scenario_ids: list[str]` with min_length=1 validator. Result model has `source_scenario_id: str`, `results: list[ScenarioApplyOutcome]`, `total_applied: int`, `total_failed: int`. Outcome model has `scenario_id: str`, `scenario_name: Optional[str]`, `success: bool`, `error: Optional[str]`.
- [x] T002 Add `extract_workforce_params(config_overrides: Dict[str, Any]) -> Dict[str, Any]` helper function to `planalign_api/services/scenario_service.py`. This function extracts workforce-only keys from a config_overrides dict: entire `workforce` section, entire `compensation` section, entire `new_hire` section, `simulation.target_growth_rate` (single key from simulation), and top-level `promotion_hazard`, `age_bands`, `tenure_bands`. Returns a new dict containing only these keys. Must NOT include `dc_plan`, `simulation.{name,start_year,end_year,random_seed}`, `data_sources`, or `advanced`.
- [x] T003 [P] Add `applyWorkforceParams(workspaceId: string, sourceScenarioId: string, targetScenarioIds: string[])` function to `planalign_studio/services/api.ts`. Calls `POST /api/workspaces/${workspaceId}/scenarios/${sourceScenarioId}/apply-workforce-params` with body `{ target_scenario_ids: targetScenarioIds }`. Returns typed `WorkforceParamsApplyResult` interface (define the TypeScript interfaces for result/outcome inline or in the same file).

**Checkpoint**: Foundation ready — models, extraction logic, and API client are in place.

---

## Phase 3: User Story 1 — Apply Workforce Parameters to Selected Scenarios (Priority: P1) MVP

**Goal**: Analysts can push workforce assumptions from the current scenario to multiple target scenarios in one action, preserving DC plan parameters.

**Independent Test**: Open Scenario A config → click "Apply Workforce Params" → select Scenarios B and C → confirm → verify B and C have A's workforce params but original DC plan params.

### Implementation for User Story 1

- [x] T004 [US1] Add `apply_workforce_params(workspace_id: str, source_scenario_id: str, target_scenario_ids: list[str]) -> WorkforceParamsApplyResult` method to `ScenarioService` in `planalign_api/services/scenario_service.py`. Logic: (1) read source scenario config_overrides via `storage.get_scenario()`, (2) call `extract_workforce_params()` on source config, (3) for each target scenario: read its config_overrides, merge workforce params (replace `workforce`, `compensation`, `new_hire` sections entirely; set `simulation.target_growth_rate`; replace `promotion_hazard`, `age_bands`, `tenure_bands` at top level), call `storage.update_scenario()` with merged config_overrides, (4) collect per-scenario success/failure into `WorkforceParamsApplyResult`. Validate: source must exist (404 if not), target must not include source id (422).
- [x] T005 [US1] Add `POST /{workspace_id}/scenarios/{scenario_id}/apply-workforce-params` endpoint to `planalign_api/routers/scenarios.py`. Accepts `WorkforceParamsApplyRequest` body. Calls `scenario_service.apply_workforce_params()`. Returns `WorkforceParamsApplyResult`. Return 404 if workspace or source scenario not found. Return 422 if target list is empty or contains source scenario id.
- [x] T006 [US1] Create `planalign_studio/components/config/ApplyWorkforceParamsModal.tsx`. Props: `availableScenarios: Scenario[]`, `sourceScenarioId: string`, `onClose: () => void`, `workspaceId: string`. UI: modal overlay with title "Apply Workforce Params to Other Scenarios", list of scenarios with checkboxes (exclude source), "Select All" / "Deselect All" toggles, "Apply" button (disabled when none selected), "Cancel" button. On "Apply" click: call `applyWorkforceParams()` API, show inline success message with count, close modal after 1.5s delay. Style with existing Tailwind utility classes matching CopyScenarioModal patterns.
- [x] T007 [US1] Add "Apply Workforce Params" button to `planalign_studio/components/ConfigStudio.tsx` next to the existing "Copy from Scenario" button. On click: fetch scenarios via `listScenarios()`, filter out current scenario, open `ApplyWorkforceParamsModal`. Button disabled when workspace has only 1 scenario (FR-007). Use Lucide `Share2` or `Copy` icon for visual distinction from the existing copy button.

**Checkpoint**: User Story 1 is fully functional — analysts can apply workforce params across scenarios.

---

## Phase 4: User Story 2 — Pre-Apply Confirmation with Change Summary (Priority: P2)

**Goal**: Analysts see a summary of what will be overwritten before applying, with the ability to cancel.

**Independent Test**: Select target scenarios → click "Apply" → verify confirmation dialog shows target names and parameter categories → click "Cancel" → verify no changes made.

### Implementation for User Story 2

- [x] T008 [US2] Add confirmation step to `ApplyWorkforceParamsModal.tsx` in `planalign_studio/components/config/ApplyWorkforceParamsModal.tsx`. After user clicks "Apply", transition the modal to a confirmation view (same modal, different content — not a separate modal). Confirmation view shows: (1) list of selected target scenario names, (2) workforce parameter categories that will be overwritten (static list: "Compensation settings", "Workforce & turnover rates", "Growth targets", "New hire demographics", "Promotion hazard config", "Age & tenure bands"), (3) warning text "This will overwrite workforce parameters in N scenarios", (4) "Confirm" button (calls API), (5) "Back" button (returns to selection view). Implement as a `step` state: `'select' | 'confirm'`.

**Checkpoint**: Users can review and cancel before any changes are made.

---

## Phase 5: User Story 3 — Post-Apply Feedback (Priority: P3)

**Goal**: Clear success or error feedback after the apply operation completes.

**Independent Test**: Complete an apply operation → verify success notification shows count and scenario names. Simulate a partial failure → verify error notification identifies which scenarios succeeded and failed.

### Implementation for User Story 3

- [x] T009 [US3] Add result display step to `ApplyWorkforceParamsModal.tsx` in `planalign_studio/components/config/ApplyWorkforceParamsModal.tsx`. After API call completes, transition to a result view (third step: `'select' | 'confirm' | 'result'`). Result view shows: (1) green checkmark icon + "Workforce parameters applied to N scenarios" for full success, (2) per-scenario result list with green check or red X per scenario, (3) if `total_failed > 0`: amber warning banner listing failed scenarios with error messages, (4) "Done" button to close modal. Handle API call errors (network failure) with a generic error message and "Retry" / "Close" buttons.

**Checkpoint**: All user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases and refinements across all user stories.

- [x] T010 Handle edge case in `ApplyWorkforceParamsModal.tsx`: if source scenario has empty/default workforce params, the apply still proceeds (no special handling needed — defaults are valid values). Add a subtle info note in the confirmation step if all workforce sections in the source are empty: "Note: Source scenario uses default workforce parameters."
- [x] T011 Add backend unit test in `tests/test_apply_workforce_params.py`. Test cases: (1) `extract_workforce_params()` correctly extracts workforce keys and excludes DC plan keys, (2) `apply_workforce_params()` service method updates target scenarios preserving DC plan params, (3) endpoint returns 404 for missing source scenario, (4) endpoint returns 422 for empty target list or self-targeting, (5) partial failure returns correct per-scenario results. Use existing test fixtures from `tests/fixtures/`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Skipped — no setup needed
- **Foundational (Phase 2)**: T001 and T002 are sequential (T002 depends on models from T001). T003 is parallel with T001/T002 (different codebase layer).
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - US1 (Phase 3): Can start immediately after Phase 2
  - US2 (Phase 4): Depends on US1 (extends the modal component)
  - US3 (Phase 5): Depends on US2 (adds third step to the modal)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Phase 2 only. No dependencies on other stories.
- **User Story 2 (P2)**: Depends on US1 — extends the `ApplyWorkforceParamsModal` with a confirmation step.
- **User Story 3 (P3)**: Depends on US2 — extends the modal with a result step (step state transitions: select → confirm → result).

### Within Each User Story

- Backend before frontend (service method → endpoint → modal → button wiring)
- T004 before T005 (service before endpoint)
- T006 before T007 (modal component before button integration)
- T005 and T006 can run in parallel (backend endpoint and frontend component are independent files)

### Parallel Opportunities

- **Phase 2**: T003 (frontend API client) can run in parallel with T001+T002 (backend models + service)
- **Phase 3 (US1)**: T005 (backend endpoint) and T006 (frontend modal) can run in parallel after T004 completes
- **Phase 6**: T010 and T011 can run in parallel (different files)

---

## Parallel Example: User Story 1

```bash
# After Phase 2 completes, launch backend and frontend in parallel:
Task T004: "Implement apply_workforce_params() service method"
# Then in parallel:
Task T005: "Add POST endpoint to scenarios router"
Task T006: "Create ApplyWorkforceParamsModal component"
# Then:
Task T007: "Wire button in ConfigStudio.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001-T003)
2. Complete Phase 3: User Story 1 (T004-T007)
3. **STOP and VALIDATE**: Apply workforce params from Scenario A to B and C, verify DC plan params unchanged
4. Deploy/demo if ready

### Incremental Delivery

1. Phase 2 → Foundation ready
2. Add US1 (T004-T007) → Basic apply with immediate execution → MVP!
3. Add US2 (T008) → Confirmation step before apply → Safer UX
4. Add US3 (T009) → Detailed result feedback → Complete UX
5. Add Polish (T010-T011) → Edge cases + tests → Production-ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US2 and US3 extend the same modal component (ApplyWorkforceParamsModal.tsx) with additional step states
- The workforce parameter boundary is defined in `extract_workforce_params()` (T002) — this is the single source of truth
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
