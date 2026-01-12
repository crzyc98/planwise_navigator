# Feature Specification: Scenario Cost Comparison Redesign

**Feature Branch**: `018-scenario-comparison-redesign`
**Created**: 2026-01-12
**Status**: Draft
**Input**: User description: "Improve ScenarioCostComparison.tsx using design patterns from CostComparison.tsx as an example"

## Clarifications

### Session 2026-01-12

- Q: How should the system initialize selected scenarios and anchor on first load? → A: Auto-select scenario named "baseline" (if exists) + first other completed scenario; "baseline" becomes anchor. If no "baseline" exists, select first two completed scenarios with first as anchor.
- Q: What should happen to the existing ScenarioCostComparison.tsx after redesign? → A: Replace entirely - delete old component, new redesigned component takes over the existing route.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare Multiple Scenarios Side-by-Side (Priority: P1)

A plan analyst needs to compare retirement plan costs across multiple scenarios (baseline, high growth, conservative) to understand cost implications of different plan designs. They want to visually see how costs trend over the simulation period and quickly identify which scenarios are more cost-effective.

**Why this priority**: Multi-scenario comparison is the core purpose of the page. Without comparing scenarios, the page has no value.

**Independent Test**: Can be fully tested by selecting 3+ scenarios, viewing charts, and verifying cost trends are displayed correctly for each selected scenario.

**Acceptance Scenarios**:

1. **Given** a workspace with 4 completed scenarios, **When** I navigate to the cost comparison page, **Then** I see a sidebar listing all completed scenarios with checkboxes for selection.

2. **Given** 3 selected scenarios, **When** I view the cost trend chart, **Then** I see distinct color-coded lines/bars for each scenario with a legend identifying them.

3. **Given** a scenario is selected as "anchor" (baseline), **When** I view the comparison, **Then** the anchor scenario is visually distinguished (dark color, anchor icon) and all variance calculations reference it.

---

### User Story 2 - Switch Between Annual and Cumulative Cost Views (Priority: P1)

A financial planner needs to toggle between seeing year-by-year costs and cumulative costs over the plan horizon to answer different business questions (annual budget planning vs. total cost of ownership).

**Why this priority**: Both views are essential for different analytical purposes. Annual shows budget impact; cumulative shows total financial commitment.

**Independent Test**: Can be tested by toggling between Annual and Cumulative views and verifying chart data recalculates correctly.

**Acceptance Scenarios**:

1. **Given** the cost comparison page with selected scenarios, **When** I click "Annual Spend", **Then** the chart displays year-over-year costs as a bar chart.

2. **Given** the cost comparison page with selected scenarios, **When** I click "Cumulative Cost", **Then** the chart displays running totals as an area chart.

3. **Given** I am viewing cumulative costs, **When** I switch to annual view, **Then** the data table below the chart also updates to show annual values.

---

### User Story 3 - Set Anchor Baseline for Variance Calculations (Priority: P2)

A plan designer wants to designate one scenario as the "anchor" baseline so that all other scenarios show their cost difference (variance) relative to that anchor. They may change the anchor mid-analysis to see costs from different perspectives.

**Why this priority**: Variance calculations are essential for decision-making, but require at least one comparison scenario to be selected first.

**Independent Test**: Can be tested by changing the anchor scenario and verifying all variance values update correctly.

**Acceptance Scenarios**:

1. **Given** 3 selected scenarios with "Baseline" as anchor, **When** I click the anchor icon on "High Growth", **Then** "High Growth" becomes the new anchor and variance values recalculate.

2. **Given** a scenario is set as anchor, **When** I view the sidebar, **Then** that scenario shows an anchor icon and "Baseline Anchor" label.

3. **Given** scenarios A, B, C where A is anchor, **When** I view the Incremental Costs chart, **Then** I see lines for B-delta and C-delta relative to A, with a dashed zero baseline.

---

### User Story 4 - View Cost Breakdown in Data Table (Priority: P2)

An analyst needs to see exact dollar values for each year in a structured table format for detailed analysis and report preparation.

**Why this priority**: Tables provide precision that charts cannot. Essential for exporting to reports but secondary to visual comparison.

**Independent Test**: Can be tested by verifying table displays correct values for each scenario and year combination.

**Acceptance Scenarios**:

1. **Given** selected scenarios, **When** I scroll to the Multi-Year Cost Matrix, **Then** I see a table with rows per scenario and columns per year.

2. **Given** the cost matrix table, **When** I view a non-anchor scenario row, **Then** I see an "Incremental Variance" column showing the difference from anchor with color coding (green for savings, orange/red for cost increase).

3. **Given** the anchor scenario, **When** I view its row in the table, **Then** the Incremental Variance column shows "--" to indicate it's the reference point.

---

### User Story 5 - Search and Filter Scenarios (Priority: P3)

A workspace may have many scenarios. Users need to quickly find specific scenarios by name without scrolling through a long list.

**Why this priority**: Quality-of-life improvement that becomes important as scenario count grows, but not blocking for basic functionality.

**Independent Test**: Can be tested by typing a search term and verifying the scenario list filters correctly.

**Acceptance Scenarios**:

1. **Given** 10 scenarios in the sidebar, **When** I type "growth" in the search box, **Then** only scenarios containing "growth" (case-insensitive) are displayed.

2. **Given** a filtered scenario list, **When** I clear the search, **Then** all scenarios are displayed again.

---

### User Story 6 - Understand Cost Drivers and Methodology (Priority: P3)

Users need contextual information about what drives plan costs and how calculations are performed to trust and interpret the data correctly.

**Why this priority**: Educational/supportive content that helps users interpret results but doesn't block core functionality.

**Independent Test**: Can be tested by verifying methodology panels display correct information about cost drivers and assumptions.

**Acceptance Scenarios**:

1. **Given** the cost comparison page, **When** I scroll to the bottom, **Then** I see a "Cost Sensitivity Drivers" panel explaining key factors affecting plan costs.

2. **Given** the cost comparison page, **When** I scroll to the methodology section, **Then** I see a "Modeling Assumptions" panel listing core design, match logic, and total cost calculation basis.

---

### Edge Cases

- What happens when only one completed scenario exists? → Show a message guiding user to run more simulations.
- What happens when a scenario is deselected while it's the anchor? → Automatically assign anchor to the next selected scenario.
- What happens when all scenarios are deselected? → Show empty state prompting selection of at least one scenario.
- What happens when scenarios have different year ranges? → Display union of all years; show "-" for years where a scenario has no data.
- What happens when the API fails to load comparison data? → Show error state with retry button, preserve selected state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a sidebar panel listing all completed scenarios in the selected workspace with checkboxes for multi-select.
- **FR-001a**: On initial load, system MUST auto-select a scenario named "baseline" (case-insensitive) as anchor plus the first other completed scenario. If no "baseline" exists, select first two completed scenarios with the first as anchor.
- **FR-002**: System MUST allow users to select/deselect scenarios by clicking on them in the sidebar.
- **FR-003**: System MUST allow exactly one selected scenario to be designated as the "anchor" (baseline) for variance calculations.
- **FR-004**: System MUST display a toggle to switch between "Annual Spend" (bar chart) and "Cumulative Cost" (area chart) views.
- **FR-005**: System MUST display an Employer Cost Trends chart showing selected scenarios with distinct colors and a legend.
- **FR-006**: System MUST display an Incremental Costs chart showing variance lines for non-anchor scenarios relative to anchor.
- **FR-007**: System MUST display a Multi-Year Cost Matrix table with scenario rows, year columns, totals, and variance column.
- **FR-008**: System MUST color-code variance values (green for cost savings, orange/red for cost increases relative to anchor).
- **FR-009**: System MUST provide a search input to filter scenarios in the sidebar by name (case-insensitive).
- **FR-010**: System MUST display the anchor scenario's summary information (name, plan duration, total costs, core design, match design) in a header panel.
- **FR-011**: System MUST display methodology/assumptions panels explaining cost drivers and modeling approach.
- **FR-012**: System MUST fetch scenario data from the API when scenarios are selected (retain existing API integration).
- **FR-013**: System MUST preserve existing copy-to-clipboard functionality for tables.
- **FR-014**: System MUST show loading states while fetching data and error states if API calls fail.
- **FR-015**: System MUST allow users to download/export a report (preserve existing Download Report button functionality).

### Key Entities

- **Scenario**: A simulation configuration with unique ID, name, status, and associated cost data by year.
- **Year Summary**: Annual metrics including participation rate, deferral rate, employer match, employer core, total employer cost, and employer cost rate.
- **Anchor/Baseline**: The designated reference scenario against which all variance calculations are performed.
- **Variance**: The difference between a scenario's cost and the anchor's cost (both absolute value and percentage).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can select and compare up to 5 scenarios simultaneously on a single screen.
- **SC-002**: Users can switch between annual and cumulative views with visual feedback in under 1 second.
- **SC-003**: Users can change the anchor scenario and see updated variance calculations in under 2 seconds.
- **SC-004**: Users can identify the highest and lowest cost scenarios within 5 seconds of page load.
- **SC-005**: Users can find a specific scenario using search within 3 seconds, regardless of total scenario count.
- **SC-006**: 90% of users can correctly interpret which scenarios cost more/less than baseline without additional training.

## Assumptions

- The redesigned component will **replace** the existing `ScenarioCostComparison.tsx` entirely; the old component will be deleted and the new one will serve the same route.
- The existing API endpoints (`listWorkspaces`, `listScenarios`, `compareDCPlanAnalytics`) remain unchanged and support multi-scenario comparison.
- Scenario data includes year-by-year contribution summaries with all required metrics.
- The component will continue to operate within the PlanAlign Studio React application context.
- Chart color palette supports up to 6 distinct colors for scenario differentiation.
- Workspace selector functionality is preserved from the current implementation.
