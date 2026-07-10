# Tasks: Fail Dbt Stage

**Input**: Design documents from `/specs/106-fail-dbt-stage/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/stage-outcome.md, quickstart.md

**Tests**: Regression tests are required by FR-008 and the project constitution's test-first workflow.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the focused test location and confirm the existing orchestration contracts before story work begins.

- [X] T001 Review existing `PipelineStageError` usage and stage-result handling in `planalign_orchestrator/pipeline_orchestrator.py`
- [X] T002 [P] Review `YearExecutor.execute_workflow_stage` success and failure result shape in `planalign_orchestrator/pipeline/year_executor.py`
- [X] T003 [P] Review existing orchestrator unit-test style and helper patterns in `tests/unit/orchestrator/test_year_executor.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the shared fast regression harness used by every user story.

**Critical**: No user story work can begin until this phase is complete.

- [X] T004 Create `tests/unit/orchestrator/test_pipeline_stage_failure.py` with imports, pytest markers, and minimal mocked `PipelineOrchestrator` construction helpers
- [X] T005 Add reusable `StageDefinition` fixture/helper for a required foundation stage in `tests/unit/orchestrator/test_pipeline_stage_failure.py`
- [X] T006 Add reusable mocked year-executor helper that returns configurable stage outcomes in `tests/unit/orchestrator/test_pipeline_stage_failure.py`

**Checkpoint**: Foundation ready. User-story tests can now be written against the same minimal orchestrator harness.

---

## Phase 3: User Story 1 - Stop Failed Simulation Stages (Priority: P1) MVP

**Goal**: A failed required workflow stage stops orchestration immediately and cannot be swallowed as completed work.

**Independent Test**: Mock a required stage outcome with `success: False`, call `_execute_stage_core`, and verify `PipelineStageError` is raised instead of returning normally.

### Tests for User Story 1

> Write these tests first and confirm they fail before implementation.

- [X] T007 [US1] Add failing regression test for `success: False` stage outcome raising `PipelineStageError` in `tests/unit/orchestrator/test_pipeline_stage_failure.py`
- [X] T008 [US1] Add failing regression test for missing stage outcome raising `PipelineStageError` in `tests/unit/orchestrator/test_pipeline_stage_failure.py`
- [X] T009 [US1] Add failing regression test for missing or non-boolean `success` value raising `PipelineStageError` in `tests/unit/orchestrator/test_pipeline_stage_failure.py`

### Implementation for User Story 1

- [X] T010 [US1] Capture the result returned by `year_executor.execute_workflow_stage` inside `_execute_stage_core` in `planalign_orchestrator/pipeline_orchestrator.py`
- [X] T011 [US1] Add fail-closed stage outcome validation in `_execute_stage_core` so only explicit `success is True` allows continuation in `planalign_orchestrator/pipeline_orchestrator.py`
- [X] T012 [US1] Run `pytest tests/unit/orchestrator/test_pipeline_stage_failure.py -q` and ensure the US1 tests pass

**Checkpoint**: User Story 1 is independently complete when failed, missing, and malformed outcomes stop orchestration.

---

## Phase 4: User Story 2 - Preserve Failure Context (Priority: P2)

**Goal**: Failure propagation includes the failed stage, simulation year, and error summary needed for support and audit diagnosis.

**Independent Test**: Mock a failed stage outcome with an error message and verify the raised failure text contains the stage name, year, and original error summary.

### Tests for User Story 2

> Write these tests first and confirm they fail before implementation.

- [X] T013 [US2] Add failing regression test asserting stage name, year, and executor error text appear in `PipelineStageError` for `success: False` in `tests/unit/orchestrator/test_pipeline_stage_failure.py`
- [X] T014 [US2] Add failing regression test asserting a generic error summary is used when a failed outcome has no `error` field in `tests/unit/orchestrator/test_pipeline_stage_failure.py`

### Implementation for User Story 2

- [X] T015 [US2] Build a clear failure message in `_execute_stage_core` using `stage.name.value`, `year`, and outcome `error` when present in `planalign_orchestrator/pipeline_orchestrator.py`
- [X] T016 [US2] Ensure invalid outcome failure messages identify the outcome as missing, malformed, or ambiguous in `planalign_orchestrator/pipeline_orchestrator.py`
- [X] T017 [US2] Run `pytest tests/unit/orchestrator/test_pipeline_stage_failure.py -q` and ensure the US2 context tests pass

**Checkpoint**: User Story 2 is independently complete when every stopped stage includes actionable failure context.

---

## Phase 5: User Story 3 - Reject Misleading Success Results (Priority: P3)

**Goal**: Successful result workflows cannot observe a failed required stage as completed, including through the monitored and legacy stage wrapper paths.

**Independent Test**: Call the wrapper path that delegates to `_execute_stage_core` with a failed stage outcome and verify the failure propagates out of the wrapper instead of returning normally.

### Tests for User Story 3

> Write these tests first and confirm they fail before implementation if wrapper propagation is incomplete.

- [X] T018 [US3] Add regression test that `_execute_stage_with_monitoring` propagates `PipelineStageError` from a failed stage result in `tests/unit/orchestrator/test_pipeline_stage_failure.py`
- [X] T019 [US3] Add regression test that `_execute_stage_with_legacy_memory` propagates `PipelineStageError` from a failed stage result in `tests/unit/orchestrator/test_pipeline_stage_failure.py`

### Implementation for User Story 3

- [X] T020 [US3] Verify `_execute_stage_with_monitoring` does not catch or downgrade `PipelineStageError` in `planalign_orchestrator/pipeline_orchestrator.py`
- [X] T021 [US3] Verify `_execute_stage_with_legacy_memory` does not catch or downgrade `PipelineStageError` in `planalign_orchestrator/pipeline_orchestrator.py`
- [X] T022 [US3] Run `pytest tests/unit/orchestrator/test_pipeline_stage_failure.py -q` and ensure wrapper propagation tests pass

**Checkpoint**: User Story 3 is independently complete when failed stage outcomes cannot be presented as successful through any stage execution wrapper.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate the feature slice and keep documentation aligned with the implementation.

- [X] T023 Run focused orchestrator regression command from `specs/106-fail-dbt-stage/quickstart.md`
- [X] T024 Run fast orchestrator slice `pytest tests/unit/orchestrator/test_pipeline_stage_failure.py tests/unit/orchestrator/test_year_executor.py -m fast -q`
- [X] T025 [P] Update `specs/106-fail-dbt-stage/quickstart.md` if the final validation command differs from the planned command
- [X] T026 [P] Review final diff for unintended schema, dbt model, API, or event payload changes in `planalign_orchestrator/pipeline_orchestrator.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion; blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion and is the MVP.
- **User Story 2 (Phase 4)**: Depends on User Story 1 because it enriches the raised failure path.
- **User Story 3 (Phase 5)**: Depends on User Story 1 because wrapper propagation requires core fail-fast behavior.
- **Polish (Phase 6)**: Depends on desired user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Required first; delivers the core stop-on-failure behavior.
- **User Story 2 (P2)**: Builds on US1 by tightening failure context.
- **User Story 3 (P3)**: Builds on US1 by proving the wrapper paths cannot mask the failure.

### Within Each User Story

- Tests must be written and fail before implementation.
- Core outcome validation must pass before context assertions.
- Wrapper propagation checks must run after core fail-fast behavior exists.

---

## Parallel Opportunities

- T002 and T003 can run in parallel during setup.
- T025 can run in parallel with final diff review T026 after validation commands are known.

## Parallel Example: Setup

```bash
Task: "Review YearExecutor.execute_workflow_stage success and failure result shape in planalign_orchestrator/pipeline/year_executor.py"
Task: "Review existing orchestrator unit-test style and helper patterns in tests/unit/orchestrator/test_year_executor.py"
```

## Parallel Example: Polish

```bash
Task: "Update specs/106-fail-dbt-stage/quickstart.md if the final validation command differs from the planned command"
Task: "Review final diff for unintended schema, dbt model, API, or event payload changes in planalign_orchestrator/pipeline_orchestrator.py"
```

## User Story Parallel Notes

- US1 tasks intentionally serialize because the tests and implementation touch the same test and production files.
- US2 tasks intentionally serialize because context assertions and message construction share the same test and production files.
- US3 tasks intentionally serialize because wrapper propagation tests share the same test file and validate the same production boundary.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Add US1 failing tests for unsuccessful, missing, and malformed outcomes.
3. Implement fail-closed result validation in `_execute_stage_core`.
4. Stop and validate with `pytest tests/unit/orchestrator/test_pipeline_stage_failure.py -q`.

### Incremental Delivery

1. Deliver US1 to stop swallowed failures.
2. Deliver US2 to ensure diagnosis context is preserved.
3. Deliver US3 to prove wrapper paths cannot reintroduce misleading success.
4. Run the quickstart validation commands before handoff.

### Notes

- Keep the production change localized to `planalign_orchestrator/pipeline_orchestrator.py`.
- Do not change event schemas, dbt model contracts, API payloads, or CLI arguments for this issue.
- Preserve existing observability and timing wrappers while making failures propagate.
