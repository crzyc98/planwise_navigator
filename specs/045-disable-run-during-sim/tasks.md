# Tasks: Disable Run Button During Active Simulation

**Input**: Design documents from `/specs/045-disable-run-during-sim/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not requested in feature specification. Manual testing only per quickstart.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `planalign_api/` (FastAPI)
- **Frontend**: `planalign_studio/` (React/Vite)

---

## Phase 1: Setup

**Purpose**: No project initialization needed — all files already exist. Skip to Phase 2.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend endpoint + frontend API client + global state infrastructure. MUST be complete before any user story work.

- [X] T001 [P] Add Pydantic response models `ActiveRun` and `ActiveSimulationsResponse` and implement `GET /api/simulations/active` endpoint that filters `_active_runs` for status in ("pending", "queued", "running") in `planalign_api/routers/simulations.py`
- [X] T002 [P] Add `ActiveRun` and `ActiveSimulationsResponse` TypeScript interfaces and `getActiveSimulations()` API client function in `planalign_studio/services/api.ts`
- [X] T003 Extend `LayoutContextType` with `isSimulationRunning`, `activeRunId`, `runningScenarioId`, `setSimulationRunning(runId, scenarioId)`, and `clearSimulationRunning()` in `planalign_studio/components/Layout.tsx`. Add state variables and provide them via the existing `<Outlet context={...}>`. On component mount, call `getActiveSimulations()` to detect active simulations and set running state for page-refresh recovery (depends on T001, T002)

**Checkpoint**: Global simulation state infrastructure is ready. All components can now consume `isSimulationRunning` from Layout context.

---

## Phase 3: User Story 1 — Prevent Duplicate Simulation Runs (Priority: P1) MVP

**Goal**: Disable the Run button in SimulationControl when a simulation is running and re-enable it on completion or failure. No duplicate simulation starts possible via the primary UI.

**Independent Test**: Start a simulation → verify Run button becomes unclickable and greyed out → wait for completion → verify button re-enables.

### Implementation for User Story 1

- [X] T004 [US1] In `planalign_studio/components/SimulationControl.tsx`, consume `isSimulationRunning`, `activeRunId`, `runningScenarioId`, `setSimulationRunning`, and `clearSimulationRunning` from Layout context via `useOutletContext()`. Remove local `activeRunId` and `runningScenarioId` useState declarations and replace all references with the context values
- [X] T005 [US1] In `planalign_studio/components/SimulationControl.tsx`, update the `handleStart()` function to call `setSimulationRunning(run.id, selectedScenarioId)` after successful `startSimulation()` API call (replacing local `setActiveRunId`/`setRunningScenarioId`)
- [X] T006 [US1] In `planalign_studio/components/SimulationControl.tsx`, update the completion detection `useEffect` (currently watching `telemetry?.current_stage`) to call `clearSimulationRunning()` when simulation completes or fails (replacing local state clearing)
- [X] T007 [US1] In `planalign_studio/components/SimulationControl.tsx`, update the main "Start Simulation" button's `disabled` prop to include `isSimulationRunning` (i.e., `disabled={!selectedScenarioId || isLoading || isSimulationRunning}`) and update its className conditional to match
- [X] T008 [US1] In `planalign_studio/components/SimulationControl.tsx`, update all scenario history table "Run" buttons to be disabled when `isSimulationRunning` is true (not just when the specific scenario is running)

**Checkpoint**: User Story 1 complete. The main SimulationControl Run button and history table buttons are disabled during active simulations and re-enable on completion/failure. Duplicate runs are prevented from the primary simulation UI.

---

## Phase 4: User Story 2 — Visual Feedback During Simulation (Priority: P2)

**Goal**: Show a spinner animation and "Running..." label on disabled Run buttons so users understand why the button is disabled and that the system is working.

**Independent Test**: Start a simulation → verify the button shows a spinner icon + "Running..." text → wait for completion → verify button returns to original icon + label.

### Implementation for User Story 2

- [X] T009 [US2] In `planalign_studio/components/SimulationControl.tsx`, update the main "Start Simulation" button to conditionally render a `Loader2` spinner icon (with `animate-spin` class) and "Running..." label when `isSimulationRunning` is true, instead of the `Play` icon and "Start Simulation" text
- [X] T010 [US2] In `planalign_studio/components/SimulationControl.tsx`, update history table "Run" buttons to show `Loader2` spinner + "Running..." when `isSimulationRunning` is true, replacing the `Play` icon and "Run" text

**Checkpoint**: User Story 2 complete. All buttons in SimulationControl show clear visual feedback (spinner + "Running...") during active simulations.

---

## Phase 5: User Story 3 — Consistent Disable Across All Run Entry Points (Priority: P2)

**Goal**: Disable Run buttons on the Scenarios page during an active simulation, ensuring there is no entry point in the application where a user could trigger a duplicate run.

**Independent Test**: Start a simulation from Simulation Control Center → navigate to Scenarios page → verify all Run buttons are greyed out and disabled → wait for completion → verify buttons re-enable.

### Implementation for User Story 3

- [X] T011 [US3] In `planalign_studio/components/ScenariosPage.tsx`, import the Layout context type and consume `isSimulationRunning` and `runningScenarioId` from `useOutletContext()`. Update the `LayoutContext` interface used in this file to include the new simulation state fields
- [X] T012 [US3] In `planalign_studio/components/ScenariosPage.tsx`, update the scenario card "Run" button (currently at ~line 430) to: (a) add `disabled={isSimulationRunning}` prop, (b) conditionally show `Loader2` spinner + "Running..." for the running scenario and "Busy" for other scenarios when `isSimulationRunning`, (c) apply greyed-out styling (`bg-gray-300 cursor-not-allowed`) when disabled instead of the green active style

**Checkpoint**: User Story 3 complete. All Run buttons across every page in the application (SimulationControl + ScenariosPage) reflect the same enabled/disabled state at all times.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling and robustness improvements that affect multiple user stories.

- [X] T013 In `planalign_studio/components/Layout.tsx`, add a 30-minute safety timeout using `useEffect` + `useRef` that calls `clearSimulationRunning()` if no completion signal is received. The timeout should reset whenever the running state was last confirmed active (track via a `lastHeartbeatRef` timestamp updated by SimulationControl when telemetry is received)
- [X] T014 In `planalign_studio/components/SimulationControl.tsx`, add a `useEffect` that updates the Layout context's heartbeat timestamp ref whenever new WebSocket telemetry is received, keeping the safety timeout from firing during long-running simulations
- [ ] T015 Manually validate all acceptance scenarios from spec.md by running `planalign studio`, starting a simulation, and verifying: (a) buttons disable immediately, (b) spinner + "Running..." appears, (c) ScenariosPage buttons also disabled, (d) buttons re-enable on completion, (e) page refresh preserves disabled state

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — can start immediately
  - T001 and T002 can run in parallel (different codebases: Python vs TypeScript)
  - T003 depends on T001 + T002 (needs API client to call on mount)
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion (needs global context)
- **User Story 2 (Phase 4)**: Depends on Phase 3 (extends the same button modifications)
- **User Story 3 (Phase 5)**: Depends on Phase 2 completion (needs global context). Can run in parallel with Phase 3/4 since it modifies a different file (ScenariosPage.tsx vs SimulationControl.tsx)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Foundational (Phase 2). Core disable/re-enable in SimulationControl.
- **User Story 2 (P2)**: Depends on User Story 1 (extends the button disabled state with visual feedback in the same file).
- **User Story 3 (P2)**: Depends on Foundational (Phase 2). Independent from US1/US2 — different file (ScenariosPage.tsx).

### Parallel Opportunities

- T001 + T002: Different codebases (backend Python, frontend TypeScript)
- Phase 3 (US1) + Phase 5 (US3) after Phase 2: Different component files (SimulationControl.tsx vs ScenariosPage.tsx)

---

## Parallel Example: Foundational Phase

```bash
# These can run simultaneously (different files):
Task T001: "Add GET /api/simulations/active endpoint in planalign_api/routers/simulations.py"
Task T002: "Add getActiveSimulations() client in planalign_studio/services/api.ts"

# Then sequentially:
Task T003: "Extend Layout context (depends on T001 + T002)"
```

## Parallel Example: User Stories After Foundational

```bash
# After Phase 2 completes, US1 and US3 can run in parallel:
Task T004-T008: "SimulationControl button disable/re-enable (US1)"
Task T011-T012: "ScenariosPage button disable (US3)"

# Then US2 extends US1's work:
Task T009-T010: "Add spinner/Running... to SimulationControl buttons (US2)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001-T003)
2. Complete Phase 3: User Story 1 (T004-T008)
3. **STOP and VALIDATE**: Start a simulation, verify Run button disables and re-enables
4. This alone prevents duplicate runs — the core safety requirement

### Incremental Delivery

1. Foundational (T001-T003) → Infrastructure ready
2. User Story 1 (T004-T008) → Disable/re-enable works → **MVP!**
3. User Story 2 (T009-T010) → Visual feedback added → Better UX
4. User Story 3 (T011-T012) → ScenariosPage covered → Complete protection
5. Polish (T013-T015) → Safety timeout + validation → Production-ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- No test tasks generated (not requested in spec)
- Total: 15 tasks across 5 phases
- Files modified: 4 existing files (simulations.py, api.ts, Layout.tsx, SimulationControl.tsx) + 1 existing file (ScenariosPage.tsx)
- No new files created
