# Feature Specification: Disable Run Button During Active Simulation

**Feature Branch**: `045-disable-run-during-sim`
**Created**: 2026-02-11
**Status**: Draft
**Input**: User description: "Disable Run button during active simulation to prevent duplicate or conflicting runs"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prevent Duplicate Simulation Runs (Priority: P1)

As a plan administrator running a simulation in PlanAlign Studio, I need the Run button to be disabled while a simulation is in progress so that I cannot accidentally trigger duplicate runs that would cause database lock conflicts or corrupt results.

**Why this priority**: This is the core safety mechanism. Database lock conflicts from concurrent DuckDB writes can cause data corruption or simulation failures. Preventing duplicate runs is the primary value delivered by this feature.

**Independent Test**: Can be fully tested by starting a simulation and verifying the Run button becomes unclickable and visually disabled, then verifying it re-enables after completion.

**Acceptance Scenarios**:

1. **Given** a simulation is not running, **When** I view the simulation controls, **Then** the Run button is enabled and clickable.
2. **Given** I click the Run button to start a simulation, **When** the simulation begins executing, **Then** the Run button immediately becomes disabled and visually greyed out.
3. **Given** a simulation is running, **When** I attempt to click the disabled Run button, **Then** nothing happens and no simulation start request is made.

---

### User Story 2 - Visual Feedback During Simulation (Priority: P2)

As a plan administrator, I need clear visual indication that a simulation is in progress so I understand why the Run button is disabled and know the system is working.

**Why this priority**: Without visual feedback, a disabled button with no explanation creates confusion. Users need to understand the system state to trust it. This builds on P1 by adding clarity.

**Independent Test**: Can be tested by starting a simulation and verifying that the button text changes to a running indicator (e.g., spinner with "Running..." label) and that this indicator persists until the simulation completes.

**Acceptance Scenarios**:

1. **Given** a simulation is running, **When** I look at the Run button area, **Then** I see a spinner animation and the label "Running..." instead of the normal "Start Simulation" / "Run" text.
2. **Given** a simulation completes successfully, **When** the completion is detected, **Then** the button returns to its normal enabled state with original label text.
3. **Given** a simulation fails with an error, **When** the failure is detected, **Then** the button returns to its normal enabled state with original label text.

---

### User Story 3 - Consistent Disable Across All Run Entry Points (Priority: P2)

As a plan administrator, I need all Run buttons throughout the application to be disabled during an active simulation, not just the primary button, so there is no way to accidentally trigger a duplicate run from any page.

**Why this priority**: The application has Run buttons in multiple locations (Simulation Control Center and Scenarios page). If only one is disabled, users could still trigger duplicate runs from another location. This is essential for complete protection.

**Independent Test**: Can be tested by starting a simulation from the Simulation Control Center, then navigating to the Scenarios page and verifying that Run buttons there are also disabled.

**Acceptance Scenarios**:

1. **Given** a simulation is running (started from any location), **When** I navigate to the Scenarios page, **Then** the Run button for the running scenario is disabled with a running indicator.
2. **Given** a simulation is running for Scenario A, **When** I view other scenarios, **Then** Run buttons for other scenarios are also disabled (since only one simulation can run at a time due to single-writer database constraints).

---

### Edge Cases

- What happens if the browser is refreshed while a simulation is running? The application should detect the active simulation on page load and show the button as disabled.
- What happens if the WebSocket connection drops during a simulation? The button should remain disabled and attempt to reconnect; it should not re-enable prematurely.
- What happens if the backend crashes mid-simulation? The button should eventually re-enable (via timeout or status polling fallback) so the user is not permanently locked out.
- What happens if two users have the application open simultaneously? Both users should see the button as disabled when either user starts a simulation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST disable all Run/Start Simulation buttons immediately when a simulation begins executing.
- **FR-002**: The system MUST re-enable all Run/Start Simulation buttons when a simulation completes (whether successful or failed).
- **FR-003**: The system MUST display a visual running indicator (spinner and "Running..." label) on the Run button while a simulation is active.
- **FR-004**: The system MUST prevent any simulation start requests from being made while the button is disabled (client-side guard).
- **FR-005**: The system MUST detect active simulations on page load/refresh and show the button in its disabled state if a simulation is already running.
- **FR-006**: The system MUST apply the disabled state consistently across all Run button instances in the application (Simulation Control Center and Scenarios page).
- **FR-007**: The system MUST include a safety timeout that re-enables the button if no completion signal is received within a reasonable period, preventing permanent lock-out.

### Key Entities

- **Simulation Run State**: Represents whether a simulation is currently active, including the scenario being simulated and the current progress. Used to determine button enabled/disabled state across the application.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users cannot trigger more than one simultaneous simulation run through the UI under any interaction pattern.
- **SC-002**: The Run button transitions to a disabled/running state within 500ms of the user clicking it.
- **SC-003**: The Run button returns to an enabled state within 3 seconds of simulation completion (success or failure).
- **SC-004**: After a page refresh during an active simulation, the Run button displays in its disabled state within 2 seconds of page load.
- **SC-005**: All Run button instances across every page in the application reflect the same enabled/disabled state at all times.

## Assumptions

- The application uses DuckDB which only supports a single writer, making concurrent simulation runs fundamentally incompatible at the database level.
- The backend already validates against duplicate runs (returning an error if a simulation is already active for the workspace), so this feature adds a client-side prevention layer for better user experience.
- WebSocket-based telemetry is the primary mechanism for detecting simulation completion; a polling fallback or timeout is an acceptable secondary mechanism.
- The safety timeout for re-enabling the button (FR-007) should default to 30 minutes, which exceeds the maximum expected simulation duration.
