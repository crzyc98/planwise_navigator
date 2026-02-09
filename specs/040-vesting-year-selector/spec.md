# Feature Specification: Vesting Year Selector

**Feature Branch**: `040-vesting-year-selector`
**Created**: 2026-02-09
**Status**: Draft
**Input**: User description: "on the vesting page can we have an option to change the vesting year you use to analyze"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Select Analysis Year Before Running Vesting Analysis (Priority: P1)

As a plan administrator on the Vesting Analysis page, I want to choose which simulation year to analyze so that I can compare vesting forfeitures across different points in the simulation timeline rather than only seeing results for the final year.

**Why this priority**: This is the core feature request. Currently, the vesting analysis always uses the final simulation year, which limits the user's ability to understand how vesting outcomes evolve over time. Enabling year selection unlocks the primary analytical value.

**Independent Test**: Can be fully tested by selecting a year from a dropdown and clicking "Analyze" to see vesting results specific to that year.

**Acceptance Scenarios**:

1. **Given** a completed multi-year simulation (e.g., 2025-2027), **When** I navigate to the Vesting Analysis page and select a scenario, **Then** I see a year selector populated with all available simulation years (2025, 2026, 2027) with the final year pre-selected as the default.
2. **Given** the year selector is visible and shows available years, **When** I select a different year (e.g., 2025) and click "Analyze", **Then** the analysis results reflect terminated employees and forfeiture calculations for that specific year.
3. **Given** I have already run an analysis for year 2027, **When** I change the year to 2025 and click "Analyze" again, **Then** the results update to show the 2025 analysis, replacing the previous results.

---

### User Story 2 - Available Years Populated from Scenario Data (Priority: P2)

As a plan administrator, I want the year selector to only show years that exist in my simulation data so that I cannot select an invalid year that would produce no results.

**Why this priority**: Prevents user confusion and errors by constraining choices to valid options. Without this, users could select years outside the simulation range and get empty or error results.

**Independent Test**: Can be tested by running analyses for scenarios with different year ranges and verifying the dropdown options match the available data.

**Acceptance Scenarios**:

1. **Given** a scenario that simulated years 2025-2027, **When** the scenario is selected, **Then** the year selector shows exactly three options: 2025, 2026, and 2027.
2. **Given** a scenario that simulated only year 2025, **When** the scenario is selected, **Then** the year selector shows only one option (2025) and it is automatically selected.
3. **Given** no scenario is selected yet, **When** I view the Vesting Analysis page, **Then** the year selector is disabled or hidden until a scenario is chosen.

---

### User Story 3 - Analysis Year Displayed in Results (Priority: P3)

As a plan administrator viewing vesting analysis results, I want the selected analysis year to be clearly displayed in the results so that I can confirm which year's data I am reviewing.

**Why this priority**: Reinforces user confidence in the displayed data and prevents confusion when switching between years. The results banner already shows the analysis year; this story ensures it updates correctly with user selection.

**Independent Test**: Can be tested by selecting different years, running analyses, and confirming the year label in the results banner matches the selection.

**Acceptance Scenarios**:

1. **Given** I selected year 2026 and ran the analysis, **When** I view the results, **Then** the scenario info banner shows "Analysis Year: 2026".
2. **Given** I previously analyzed year 2027 and then switch to year 2025, **When** the new analysis completes, **Then** the banner updates to show "Analysis Year: 2025".

---

### Edge Cases

- What happens when a scenario has only one simulation year? The year selector shows a single option that is automatically selected, and the selector remains visible but effectively read-only.
- What happens when the user changes the scenario after selecting a year? The year selector resets to the final year of the newly selected scenario, and any previously displayed results are cleared.
- What happens if the selected year has no terminated employees? The analysis completes normally with zero forfeitures displayed and appropriate messaging (e.g., "No terminated employees found for this year").

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Vesting Analysis page MUST display a year selection control alongside the existing scenario and schedule selectors.
- **FR-002**: The year selector MUST be populated with all simulation years available in the selected scenario's data.
- **FR-003**: The year selector MUST default to the final (most recent) simulation year when a scenario is selected.
- **FR-004**: The year selector MUST be disabled or hidden when no scenario is selected.
- **FR-005**: When the user selects a year and triggers analysis, the system MUST pass the selected year to the vesting analysis calculation.
- **FR-006**: When the user changes the selected scenario, the year selector MUST reset to the final year of the new scenario and clear any previous results.
- **FR-007**: The analysis results MUST display the selected year in the results summary so the user can confirm which year was analyzed.
- **FR-008**: The available years MUST be retrieved from the scenario's actual simulation data to prevent selection of invalid years.

### Key Entities

- **Simulation Year**: An integer representing a year within the simulation range (e.g., 2025, 2026, 2027). Each scenario contains one or more simulation years.
- **Vesting Analysis Request**: The set of parameters sent to perform an analysis, now including the selected simulation year alongside the current and proposed vesting schedules.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can select any available simulation year and receive vesting analysis results specific to that year within the same interaction time as today's analysis.
- **SC-002**: The year selector accurately reflects 100% of simulation years present in the selected scenario's data with no invalid options.
- **SC-003**: Users can switch between years and re-analyze without navigating away from the page or re-selecting other parameters (scenario, schedules).
- **SC-004**: The default year selection (final year) preserves the current behavior for users who do not need to change the year, ensuring zero disruption to existing workflows.

## Assumptions

- The backend already accepts an optional `simulation_year` parameter in the vesting analysis request. This feature primarily requires frontend changes to expose year selection and a lightweight way to retrieve available years for a given scenario.
- Available simulation years can be determined from existing scenario data stored in the database (e.g., distinct years from the workforce snapshot table).
- The vesting analysis calculation logic does not need to change; it already supports filtering by a specific year.
