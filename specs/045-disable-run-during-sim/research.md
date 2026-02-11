# Research: Disable Run Button During Active Simulation

**Branch**: `045-disable-run-during-sim` | **Date**: 2026-02-11

## R1: Cross-Component State Sharing Strategy

**Decision**: Extend existing `LayoutContextType` in `Layout.tsx` to include global simulation running state, rather than creating a new React Context.

**Rationale**: The `Layout` component already wraps all routes via `<Outlet context={...}>` and all child components already consume it via `useOutletContext()`. Adding simulation state here avoids introducing a new provider and keeps the state management pattern consistent with the rest of the app (no Redux/Zustand/Context API currently used).

**Alternatives considered**:
- **New SimulationContext provider**: Would require wrapping routes in an additional provider. Adds complexity for no benefit since Layout already provides context to all routes.
- **Zustand/Redux**: Overkill for a single boolean + run ID. The app has no global state library and adding one for this feature would be disproportionate.
- **sessionStorage only**: Could persist across refresh but doesn't provide reactivity. Would need polling to sync across components. Not a primary mechanism but useful as a supplementary persistence layer.

## R2: Backend Active Simulation Detection on Page Refresh

**Decision**: Add a new `GET /api/simulations/active` endpoint that returns all currently running simulations from `_active_runs`. Use this on page load to detect and recover running state.

**Rationale**: The existing endpoints don't support this:
- `GET /api/scenarios/{id}/run/status` requires knowing which scenario to check (per-scenario, not global).
- `GET /api/system/status` only returns a count (`active_simulations: int`), not run details.
- The frontend needs `run_id` to reconnect the WebSocket for telemetry.

**Alternatives considered**:
- **Poll each scenario's status individually**: Requires N API calls (one per scenario). Slow and wasteful.
- **Extend `GET /api/system/status`**: Could work but mixes concerns. System status is for health checks, not UI state recovery.
- **Store `run_id` in sessionStorage and call per-scenario status**: Works for single-tab recovery but doesn't help multi-tab or multi-user scenarios. Still needed as supplementary.

## R3: Safety Timeout Mechanism

**Decision**: Use a client-side `setTimeout` of 30 minutes that re-enables the Run button if no completion signal is received. The timeout resets on each WebSocket telemetry message (heartbeat counts).

**Rationale**: 30 minutes exceeds the maximum expected simulation duration. The timeout acts as a dead-man's switch for the edge case where the backend crashes and no completion/failure signal is sent. Resetting on heartbeats prevents premature re-enable during long-running simulations.

**Alternatives considered**:
- **Backend timeout with status cleanup**: Would require a background task to sweep stale runs. More robust but adds backend complexity for an edge case. Could be added later.
- **No timeout (manual reset only)**: The existing `POST /api/scenarios/{id}/run/reset` endpoint handles this, but it's a poor UX to require manual intervention.

## R4: ScenariosPage Button Behavior

**Decision**: The "Run" button on ScenariosPage (line 430) currently just navigates to `/simulate?scenario=${id}`. During an active simulation, it should be disabled and show "Running..." with a spinner — same pattern as the main button. All scenarios' Run buttons should be disabled (not just the running one) due to DuckDB's single-writer constraint.

**Rationale**: Navigation-based "Run" doesn't directly start a simulation, but it leads to the simulation page where the user would click Start. Disabling at the ScenariosPage level prevents confusion and communicates that the system is busy. The DuckDB single-writer lock means no scenario can run while another is active.

**Alternatives considered**:
- **Allow navigation but disable the Start button on SimulationControl**: Would confuse users who navigate there expecting to run.
- **Only disable the running scenario's button**: Misleading since other scenarios also can't run due to the database lock.

## R5: Existing Code That Already Partially Implements This

**Findings from codebase research**:

| Component | Current State | Gap |
|-----------|--------------|-----|
| SimulationControl main button (line 155) | Disabled when `!selectedScenarioId \|\| isLoading` | Not disabled when `activeRunId` is set (only disabled during initial load) |
| SimulationControl history table buttons (line 435) | Disabled when `scenario.status === 'running' && scenario.id === runningScenarioId` | Only checks the running scenario, not global "any simulation running" |
| ScenariosPage Run buttons (line 430) | Never disabled for simulation state | No simulation state awareness at all |
| BatchProcessing launch button (line 331) | Disabled when `isSubmitting` | No awareness of active single-scenario runs |
| WebSocket telemetry (websocket.ts) | Fully functional for real-time updates | Only used in SimulationControl |
| Backend duplicate prevention (simulations.py line 92-97) | Returns 409 if scenario already running | Only per-scenario, doesn't prevent starting a different scenario |

**Key insight**: `SimulationControl.tsx` already has `activeRunId` and `runningScenarioId` state (lines 22-23) and completion detection (lines 80-96). The main gap is that this state is **local to SimulationControl** and not shared with ScenariosPage or BatchProcessing.
