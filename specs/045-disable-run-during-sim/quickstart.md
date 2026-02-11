# Quickstart: Disable Run Button During Active Simulation

**Branch**: `045-disable-run-during-sim` | **Date**: 2026-02-11

## What This Feature Does

Prevents users from triggering duplicate simulation runs by disabling all Run buttons in PlanAlign Studio while a simulation is active. Shows a spinner with "Running..." label as visual feedback. Re-enables buttons on completion or failure.

## Files to Modify

### Backend (1 new endpoint)
- `planalign_api/routers/simulations.py` — Add `GET /api/simulations/active` endpoint
- `planalign_api/main.py` — Register the new route (if not already on the simulations router)

### Frontend (4 files)
- `planalign_studio/services/api.ts` — Add `getActiveSimulations()` API client function
- `planalign_studio/components/Layout.tsx` — Extend `LayoutContextType` with simulation running state; add recovery-on-load logic
- `planalign_studio/components/SimulationControl.tsx` — Consume global state instead of local state; disable main button and history table buttons
- `planalign_studio/components/ScenariosPage.tsx` — Consume global state; disable Run buttons when simulation active

## Key Design Decisions

1. **State lives in Layout context** — no new state library, extends existing `useOutletContext()` pattern
2. **New backend endpoint** — `GET /api/simulations/active` enables page-refresh recovery
3. **All Run buttons disabled** — DuckDB single-writer means no scenario can run while another is active
4. **30-minute safety timeout** — dead-man's switch re-enables buttons if backend stops responding

## How to Test

1. Start PlanAlign Studio: `planalign studio`
2. Open a workspace with at least one scenario
3. Click "Start Simulation" — button should immediately show spinner + "Running..."
4. Navigate to Scenarios page — all Run buttons should be greyed out
5. Refresh the browser — buttons should re-detect the active simulation and stay disabled
6. Wait for simulation to complete — all buttons should re-enable

## Dependencies

- No new packages required
- Uses existing WebSocket infrastructure for completion detection
- Uses existing `_active_runs` in-memory store for the new endpoint
