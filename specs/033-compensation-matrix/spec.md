# Feature Specification: Multi-Year Compensation Matrix

**Feature Branch**: `033-compensation-matrix`
**Created**: 2026-02-03
**Status**: Draft
**Input**: User description: "on the compare cost page, at the bottom we have a multi-year cost matrix, could we add a similar table below that with the total compensation per year, it will be good to show the compensation the actual compensation earned for each simulation year for each scenario selected."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Annual Compensation by Scenario (Priority: P1)

A financial analyst comparing workforce scenarios wants to see the total compensation earned by employees for each simulation year across all selected scenarios, displayed in the same format as the existing cost matrix.

**Why this priority**: This is the core value of the feature - providing compensation visibility alongside employer costs enables holistic workforce cost analysis.

**Independent Test**: Can be fully tested by selecting 2+ scenarios on the compare cost page, scrolling to the bottom, and verifying the compensation matrix displays total compensation values for each year and scenario.

**Acceptance Scenarios**:

1. **Given** a user has selected 2 or more scenarios on the compare cost page, **When** the page loads completely, **Then** a "Multi-Year Compensation Matrix" table appears below the existing "Multi-Year Cost Matrix" table showing total compensation for each year and each selected scenario.

2. **Given** a user is viewing the compensation matrix, **When** they compare values across scenarios, **Then** each scenario displays the total compensation for each simulation year in currency format, with a total column showing the sum across all years.

3. **Given** a user has set an anchor scenario, **When** they view the compensation matrix, **Then** the anchor scenario row is visually highlighted (matching the cost matrix styling) and non-anchor scenarios display a variance column showing the difference from the anchor.

---

### User Story 2 - Copy Compensation Data (Priority: P2)

A financial analyst wants to copy the compensation matrix data to their clipboard for use in external reports or presentations.

**Why this priority**: Enables data portability and integration with other reporting tools, following the existing pattern for the cost matrix.

**Independent Test**: Can be tested by clicking the copy button on the compensation matrix header and pasting into a spreadsheet to verify the data is correctly formatted.

**Acceptance Scenarios**:

1. **Given** a user is viewing the compensation matrix, **When** they click the copy button in the table header, **Then** the compensation data is copied to the clipboard in a tab-separated format suitable for pasting into spreadsheets.

2. **Given** a user has copied the compensation data, **When** the copy action completes, **Then** the copy button displays a visual confirmation (checkmark icon) for a brief period before reverting to the copy icon.

---

### Edge Cases

- What happens when a scenario has no compensation data for a specific year? Display a dash (-) in that cell.
- How does the system handle scenarios with different simulation year ranges? Display data only for years where data exists; show dash for missing years.
- What happens when only one scenario is selected? The variance column shows "--" since there is no comparison baseline.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a "Multi-Year Compensation Matrix" table below the existing "Multi-Year Cost Matrix" on the compare cost page.
- **FR-002**: System MUST show total compensation for each simulation year for each selected scenario in the matrix.
- **FR-003**: System MUST display compensation values in currency format (matching the cost matrix formatting).
- **FR-004**: System MUST calculate and display a "Total" column showing the sum of compensation across all years for each scenario.
- **FR-005**: System MUST highlight the anchor scenario row with distinct visual styling (blue background, matching cost matrix).
- **FR-006**: System MUST display a "Variance" column showing the compensation difference between each scenario and the anchor scenario.
- **FR-007**: System MUST apply conditional formatting to variance values (positive variance in orange, negative variance in green, matching cost matrix behavior).
- **FR-008**: System MUST provide a copy-to-clipboard button that copies the compensation matrix data in a spreadsheet-compatible format.
- **FR-009**: System MUST display a visual confirmation when data is successfully copied to clipboard.
- **FR-010**: System MUST display a dash (-) for any year where compensation data is not available.
- **FR-011**: System MUST maintain consistent row ordering between the cost matrix and compensation matrix (scenarios appear in the same order).

### Key Entities

- **Compensation Matrix**: A data grid displaying total compensation by year for each selected scenario, with totals and variance calculations.
- **Scenario Compensation Data**: The total compensation value for a specific scenario and simulation year, sourced from the `total_compensation` field in the existing API response.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view total compensation for all selected scenarios (up to 6) and all simulation years in a single table without scrolling horizontally for typical 3-5 year simulations.
- **SC-002**: The compensation matrix displays data within the same page load time as the existing cost matrix (no additional API calls required since compensation data is already included in the response).
- **SC-003**: Users can copy compensation data to clipboard and paste into spreadsheet applications with correct column alignment.
- **SC-004**: Visual consistency is maintained between cost matrix and compensation matrix (same fonts, colors, spacing, and interaction patterns).
- **SC-005**: Variance calculations match the anchor scenario comparison pattern used in the cost matrix.

## Assumptions

- The `total_compensation` field in the existing API response already contains the correct annual compensation totals from the backend.
- No additional backend API changes are required since compensation data is already returned in the existing comparison endpoint response.
- The table will follow the exact same visual design patterns as the existing Multi-Year Cost Matrix (fonts, colors, spacing, responsive behavior).
- Currency formatting will use the existing formatting helper function.
- The compensation matrix will appear immediately below the cost matrix, before the methodology footer section.
