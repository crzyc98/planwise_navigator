# Implementation Plan: Disable Run Button During Active Simulation

**Branch**: `045-disable-run-during-sim` | **Date**: 2026-02-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/045-disable-run-during-sim/spec.md`

## Summary

Prevent duplicate simulation runs by disabling all Run buttons in PlanAlign Studio while a simulation is active. The approach extends the existing Layout context to share simulation running state across components, adds a lightweight backend endpoint for page-refresh recovery, and applies a consistent disabled+spinner UI pattern to all Run button locations.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend API), React 18 + Vite (frontend), react-router-dom (routing/context)
**Storage**: N/A (reads from in-memory `_active_runs` dict; no database changes)
**Testing**: Manual testing via PlanAlign Studio (frontend-focused UI feature)
**Target Platform**: Web browser (desktop), served by local FastAPI + Vite dev servers
**Project Type**: Web application (frontend + backend)
**Performance Goals**: Button state transition <500ms; page-refresh recovery <2s; re-enable <3s after completion
**Constraints**: Single-writer DuckDB lock means only one simulation can run at a time across all scenarios
**Scale/Scope**: 2-3 Run button locations, 1 new backend endpoint, 4-5 frontend files modified

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | **N/A** | No events created or modified. Feature is UI-only state management. |
| II. Modular Architecture | **PASS** | Extends existing Layout context (no new modules). New endpoint is a small addition to existing router. |
| III. Test-First Development | **PASS** | Feature is primarily a UI state change. Manual testing is appropriate for React component behavior. No Python logic complex enough to warrant unit tests. |
| IV. Enterprise Transparency | **N/A** | No simulation decisions or audit trail affected. |
| V. Type-Safe Configuration | **PASS** | New API types use Pydantic models (backend) and TypeScript interfaces (frontend). |
| VI. Performance & Scalability | **PASS** | New endpoint reads from in-memory dict (<50ms). No database queries added. Button transitions meet SC-002 (500ms) target. |

**Post-Phase 1 Re-check**: All gates still pass. No new dependencies, no database changes, no circular imports introduced.

## Project Structure

### Documentation (this feature)

```text
specs/045-disable-run-during-sim/
├── plan.md              # This file
├── research.md          # Phase 0: Research decisions
├── data-model.md        # Phase 1: State model and API response shapes
├── quickstart.md        # Phase 1: Developer quickstart guide
├── contracts/
│   └── api.md           # Phase 1: New endpoint contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_api/
├── routers/
│   └── simulations.py       # Add GET /api/simulations/active endpoint
└── main.py                  # Route registration (if needed)

planalign_studio/
├── components/
│   ├── Layout.tsx            # Extend LayoutContextType with simulation state + recovery
│   ├── SimulationControl.tsx # Use global state; disable main + history buttons
│   └── ScenariosPage.tsx     # Consume global state; disable Run buttons
└── services/
    └── api.ts                # Add getActiveSimulations() client function
```

**Structure Decision**: Web application structure. This feature touches both backend (1 new endpoint in existing router) and frontend (extend existing context, modify 3 components, add 1 API function). No new files created except the API contract documentation.

## Complexity Tracking

> No constitution violations. No complexity tracking needed.

## Implementation Approach

### Phase 1: Backend — New Active Simulations Endpoint

**File**: `planalign_api/routers/simulations.py`

Add a `GET /api/simulations/active` endpoint that returns all runs from `_active_runs` with status in ("pending", "queued", "running"). This is a simple read from the existing in-memory dict — no new storage or models needed beyond a response wrapper.

**Pydantic response model**: `ActiveSimulationsResponse` with a list of `ActiveRun` objects (subset of `SimulationRun` fields: run_id, scenario_id, status, progress, current_stage, started_at).

### Phase 2: Frontend — API Client

**File**: `planalign_studio/services/api.ts`

Add `getActiveSimulations()` function and TypeScript interfaces (`ActiveRun`, `ActiveSimulationsResponse`) matching the backend contract.

### Phase 3: Frontend — Global State in Layout Context

**File**: `planalign_studio/components/Layout.tsx`

Extend `LayoutContextType` with:
- `isSimulationRunning: boolean`
- `activeRunId: string | null`
- `runningScenarioId: string | null`
- `setSimulationRunning(runId: string, scenarioId: string): void`
- `clearSimulationRunning(): void`

On mount, call `getActiveSimulations()` to detect any active simulation (page-refresh recovery). If an active run is found, set the running state immediately.

### Phase 4: Frontend — SimulationControl Integration

**File**: `planalign_studio/components/SimulationControl.tsx`

- Replace local `activeRunId` / `runningScenarioId` state with global context values
- Main "Start Simulation" button: disable when `isSimulationRunning` (not just `isLoading`)
- Show spinner + "Running..." label when disabled due to active simulation
- History table Run buttons: disable all when `isSimulationRunning`
- On successful `startSimulation()` call: call `setSimulationRunning(runId, scenarioId)`
- On completion/failure detection (existing telemetry effect): call `clearSimulationRunning()`

### Phase 5: Frontend — ScenariosPage Integration

**File**: `planalign_studio/components/ScenariosPage.tsx`

- Consume `isSimulationRunning` and `runningScenarioId` from Layout context
- Disable all Run buttons when `isSimulationRunning`
- Show "Running..." with spinner on the specific running scenario's button
- Show "Busy" or disabled state on other scenarios' buttons

### Phase 6: Safety Timeout

**File**: `planalign_studio/components/Layout.tsx`

Add a 30-minute timeout that calls `clearSimulationRunning()` if no completion signal is received. The timeout resets whenever the WebSocket sends a heartbeat or telemetry update (monitored via a timestamp ref). This prevents permanent button lock-out if the backend crashes.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| State desync between Layout context and SimulationControl | Low | Medium | Both read from same context; completion clears state atomically |
| Backend crash leaves button permanently disabled | Low | High | 30-minute safety timeout auto-re-enables |
| Race condition: user clicks Run before context updates | Low | Low | Backend returns 409; frontend shows error and doesn't get stuck |
| Page refresh doesn't detect active run | Low | Medium | New `/api/simulations/active` endpoint + sessionStorage backup |
