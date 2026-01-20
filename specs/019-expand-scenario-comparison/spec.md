# Feature Specification: Expand Scenario Comparison Limit

**Feature Branch**: `019-expand-scenario-comparison`
**Created**: 2026-01-20
**Status**: Draft
**Input**: User description: "On the compare costs page, allow selecting up to 6 total scenarios including the anchor, instead of the current limit of 3 total"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare Six Scenarios Side-by-Side (Priority: P1)

As a benefits analyst, I want to compare up to 6 scenarios simultaneously on the Compare Costs page so that I can evaluate more plan design variations in a single view without switching between multiple comparison sessions.

**Why this priority**: This is the core request - enabling 6-scenario comparison directly addresses the user's need to analyze more scenarios at once, which is essential for comprehensive plan design analysis.

**Independent Test**: Can be fully tested by selecting 6 different completed scenarios and verifying all 6 appear in the comparison charts and table, delivering immediate value for multi-scenario analysis.

**Acceptance Scenarios**:

1. **Given** 6 or more completed scenarios exist in the workspace, **When** the user selects 6 scenarios via the scenario selector, **Then** all 6 scenarios appear in the cost comparison charts and variance table.

2. **Given** the user has 5 scenarios selected, **When** they attempt to select a 6th scenario, **Then** the 6th scenario is added successfully and displayed in the comparison view.

3. **Given** the user has 6 scenarios selected, **When** viewing the scenario selector, **Then** unchecked scenario checkboxes are disabled with a tooltip indicating the maximum of 6 has been reached.

---

### User Story 2 - Visual Clarity with Six Scenarios (Priority: P2)

As a benefits analyst reviewing cost comparisons, I want the charts and tables to remain readable and usable when displaying 6 scenarios so that I can effectively interpret the data without visual clutter.

**Why this priority**: While the core functionality (P1) enables selecting 6 scenarios, this ensures the data remains interpretable - critical for the feature to be genuinely useful.

**Independent Test**: Can be tested by selecting 6 scenarios with varying cost values and verifying that chart legends, bars/lines, and table columns are all distinguishable and readable.

**Acceptance Scenarios**:

1. **Given** 6 scenarios are selected, **When** the comparison view renders, **Then** each scenario has a distinct color in charts that is visually distinguishable from the other 5.

2. **Given** 6 scenarios are selected with long names, **When** viewing the comparison table, **Then** scenario names are displayed without truncation issues that prevent identification.

3. **Given** 6 scenarios are selected, **When** viewing the variance chart (delta from anchor), **Then** all 6 variance values are clearly visible and distinguishable.

---

### User Story 3 - Copy Full Comparison Data (Priority: P3)

As a benefits analyst, I want to copy the complete 6-scenario comparison data to my clipboard so that I can paste it into Excel or other tools for further analysis or reporting.

**Why this priority**: This extends existing copy functionality to support the expanded scenario count, ensuring analysts can export their full comparison for external analysis.

**Independent Test**: Can be tested by selecting 6 scenarios, clicking the copy button, and pasting into a spreadsheet to verify all 6 scenarios' data is present.

**Acceptance Scenarios**:

1. **Given** 6 scenarios are selected in the comparison view, **When** the user clicks the copy-to-clipboard button, **Then** the clipboard contains tab-separated data for all 6 scenarios across all years.

---

### Edge Cases

- What happens when a user has exactly 6 scenarios and tries to add a 7th? Unchecked scenario checkboxes are disabled with a tooltip indicating the maximum of 6 has been reached.
- What happens when comparing 6 scenarios with significantly different cost magnitudes? Charts should auto-scale appropriately to show all data points.
- What happens when viewing on a smaller screen width? The UI should remain functional, potentially with horizontal scrolling for the table.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to select up to 6 scenarios (including the anchor) for comparison on the Compare Costs page.
- **FR-002**: System MUST prevent selection of more than 6 scenarios by disabling unchecked scenario checkboxes when 6 are selected, with a tooltip explaining the limit.
- **FR-003**: System MUST display all 6 selected scenarios in the cost trend charts (bar chart and area chart views).
- **FR-004**: System MUST display all 6 selected scenarios in the variance/delta chart.
- **FR-005**: System MUST display all 6 selected scenarios in the multi-year cost comparison table.
- **FR-006**: System MUST provide 6 visually distinct colors for scenario differentiation in charts.
- **FR-007**: System MUST include all 6 scenarios' data when copying comparison data to clipboard.
- **FR-008**: System MUST maintain the existing anchor/baseline functionality with 6 scenarios (any of the 6 can be set as anchor).

### Key Entities

- **Scenario Selection**: The set of scenario IDs chosen for comparison (max 6).
- **Anchor Scenario**: The single scenario designated as the baseline for variance calculations (must be one of the selected scenarios).
- **Comparison Data**: The aggregated cost metrics for all selected scenarios across simulation years.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can select and compare exactly 6 scenarios simultaneously on the Compare Costs page.
- **SC-002**: All 6 scenarios are visible and distinguishable in comparison charts without overlap or visual confusion.
- **SC-003**: Users can complete a 6-scenario comparison analysis (select scenarios, review charts, copy data) without errors or missing data.
- **SC-004**: The comparison page loads and renders within acceptable time when 6 scenarios are selected (consistent with current performance).

## Clarifications

### Session 2026-01-20

- Q: How should the system provide feedback when the 6-scenario limit is reached? → A: Disable unchecked scenario checkboxes when 6 are selected, with tooltip explaining the limit.

## Assumptions

- The current implementation supports 5 scenarios (code shows `prev.length < 5`), not 3 as mentioned in the request. This spec increases the limit to 6.
- The existing color palette and chart library can support 6 distinct, accessible colors.
- The backend API (`compareDCPlanAnalytics`) can handle 6 scenario IDs without modification.
- Screen real estate is sufficient for 6 columns in the comparison table on typical analyst workstations.
