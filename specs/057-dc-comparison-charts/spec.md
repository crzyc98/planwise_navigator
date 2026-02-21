# Feature Specification: DC Plan Comparison Charts

**Feature Branch**: `057-dc-comparison-charts`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Add DC plan comparison chart visualizations to ScenarioComparison page"
**Depends On**: Issue #147 — Backend must return DC plan year-by-year metrics in comparison response

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare Employer Cost Trends Across Scenarios (Priority: P1)

A benefits analyst has completed simulations for multiple plan design scenarios (e.g., baseline, enhanced match, reduced core). They navigate to the scenario comparison page and scroll to the new "DC Plan Comparison" section. They see a line chart showing employer cost as a percentage of total compensation for each scenario across all simulation years. Each scenario is drawn as a distinct colored line. By hovering over any data point, they see the exact employer cost rate for that year and scenario. This lets them quickly answer the question: "What does this plan design cost us over time?"

**Why this priority**: Employer cost rate is the single most important metric for plan sponsors evaluating plan design changes. It directly answers the core business question of affordability.

**Independent Test**: Can be fully tested by running two completed scenarios with different plan designs and verifying the employer cost rate line chart renders with one line per scenario, correct year labels, and accurate tooltip values.

**Acceptance Scenarios**:

1. **Given** two or more completed scenarios are selected for comparison, **When** the user views the DC Plan Comparison section, **Then** a line chart displays employer cost rate (%) over simulation years with one line per scenario in distinct colors.
2. **Given** a line chart is displayed, **When** the user hovers over a data point, **Then** a tooltip shows the scenario name, simulation year, and exact employer cost rate percentage.
3. **Given** scenarios have different simulation year ranges, **When** the chart renders, **Then** the x-axis spans the union of all years and lines only appear for years where data exists.

---

### User Story 2 - Track Participation and Deferral Rate Trends (Priority: P2)

The analyst wants to understand how employee engagement with the retirement plan differs across scenarios. Below the employer cost chart, they see two additional line charts: one for participation rate trends and one for average deferral rate trends. Each chart shows one line per scenario, using the same color assignments as the employer cost chart. This enables the analyst to correlate cost changes with employee behavior changes.

**Why this priority**: Participation and deferral rates are the primary drivers of employer cost. Understanding these trends helps explain why costs differ across scenarios.

**Independent Test**: Can be fully tested by comparing scenarios and verifying that participation rate and deferral rate line charts render with correct values matching the underlying simulation data.

**Acceptance Scenarios**:

1. **Given** two or more completed scenarios are selected, **When** the DC Plan Comparison section loads, **Then** a participation rate trend line chart and an average deferral rate trend line chart are displayed.
2. **Given** the participation rate chart is displayed, **When** the user reads the chart, **Then** the y-axis shows percentage values and each scenario line accurately reflects the year-by-year participation rate.
3. **Given** the deferral rate chart is displayed, **When** the user reads the chart, **Then** the y-axis shows percentage values and each scenario line accurately reflects the year-by-year average deferral rate.

---

### User Story 3 - Compare Contribution Breakdown by Category (Priority: P3)

The analyst wants to understand how total contributions break down into employee deferrals, employer match, and employer core contributions. A grouped bar chart shows these three categories side-by-side for each scenario, using the final simulation year's data. This reveals which component of cost differs most between scenarios.

**Why this priority**: Knowing the breakdown between match, core, and employee contributions helps plan sponsors understand which plan design levers are driving cost differences.

**Independent Test**: Can be fully tested by selecting two scenarios and verifying that a bar chart shows three grouped bars (employee, match, core) per scenario with correct dollar values.

**Acceptance Scenarios**:

1. **Given** two or more completed scenarios are selected, **When** the DC Plan Comparison section loads, **Then** a grouped bar chart displays employee contributions, employer match, and employer core for each scenario using the final simulation year.
2. **Given** the bar chart is displayed, **When** the user hovers over a bar segment, **Then** a tooltip shows the exact dollar amount and category label.
3. **Given** one scenario has no employer core contributions, **When** the chart renders, **Then** the core bar is absent for that scenario without breaking the layout.

---

### User Story 4 - Review Summary Table with Baseline Deltas (Priority: P4)

The analyst wants a tabular summary comparing key DC plan metrics across all scenarios with differences highlighted relative to the baseline. A summary table shows rows for participation rate, average deferral rate, employer cost rate, and total contributions. Each non-baseline scenario column includes a delta value and color coding: green for favorable deltas (lower cost or higher participation), red for unfavorable deltas.

**Why this priority**: A summary table provides at-a-glance comparison without requiring chart interpretation, making it easy to communicate findings to stakeholders.

**Independent Test**: Can be fully tested by selecting a baseline and one alternative scenario and verifying the table displays correct metric values, computed deltas, and appropriate color coding.

**Acceptance Scenarios**:

1. **Given** two or more completed scenarios are selected, **When** the DC Plan Comparison section loads, **Then** a summary table displays participation rate, average deferral rate, employer cost rate, and total contributions with one column per scenario.
2. **Given** the summary table is displayed, **When** the user reads a non-baseline scenario column, **Then** each metric shows the absolute value and a delta relative to the baseline scenario.
3. **Given** a delta represents lower employer cost, **When** the delta is displayed, **Then** it appears in green. **Given** a delta represents higher employer cost, **When** the delta is displayed, **Then** it appears in red.

---

### Edge Cases

- What happens when only one scenario is selected? The DC plan charts render with a single line/bar per chart and the summary table shows values without deltas.
- What happens when scenarios have different year ranges (e.g., 2025-2027 vs 2025-2030)? Charts span the union of all years; lines end where data ends for shorter scenarios.
- What happens when the backend DC plan comparison data is not yet available (dependency on #147)? The DC Plan section shows a loading spinner until data arrives, or a graceful empty state message if the endpoint returns no data.
- What happens when a scenario has zero enrolled participants? Participation rate shows 0%, deferral rate shows 0%, and contribution bars are empty — no errors or chart breakage.
- What happens when the user resizes the browser window? All charts reflow responsively to fit the available width.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a "DC Plan Comparison" section on the scenario comparison page when two or more scenarios are selected.
- **FR-002**: System MUST render an employer cost rate trend line chart with simulation year on the x-axis and employer cost as a percentage of compensation on the y-axis.
- **FR-003**: System MUST render a participation rate trend line chart with simulation year on the x-axis and participation rate percentage on the y-axis.
- **FR-004**: System MUST render an average deferral rate trend line chart with simulation year on the x-axis and average deferral rate percentage on the y-axis.
- **FR-005**: System MUST render a contribution breakdown grouped bar chart comparing employee contributions, employer match, and employer core contributions across scenarios.
- **FR-006**: System MUST display one line per scenario in each trend chart, using the existing scenario color scheme for consistency.
- **FR-007**: System MUST show interactive tooltips on all charts displaying exact values, scenario name, and year on hover.
- **FR-008**: System MUST render a summary comparison table with rows for participation rate, average deferral rate, employer cost rate, and total contributions, and columns for each scenario.
- **FR-009**: Summary table MUST display delta values (absolute and percentage) relative to the baseline scenario for each non-baseline column.
- **FR-010**: Summary table MUST color-code deltas: green for favorable changes, red for unfavorable changes.
- **FR-011**: System MUST show a loading state while DC plan comparison data is being fetched.
- **FR-012**: System MUST gracefully handle scenarios with different year ranges by spanning the union of all years.
- **FR-013**: System MUST gracefully handle scenarios with zero participants or missing DC plan data without errors.
- **FR-014**: The contribution breakdown chart MUST use the final simulation year's data by default.
- **FR-015**: All charts MUST be responsive and adapt to the available container width.

### Key Entities

- **Contribution Year Summary**: Per-scenario, per-year aggregate of participation rate, average deferral rate, employee contributions, employer match, employer core, total contributions, total compensation, and employer cost rate.
- **Scenario Comparison Summary**: Final-year snapshot of key metrics per scenario with computed deltas relative to a designated baseline scenario.

## Assumptions

- The backend DC plan comparison endpoint (Issue #147) returns year-by-year `ContributionYearSummary` data per scenario, including participation_rate, average_deferral_rate, employer_cost_rate, total_employee_contributions, total_employer_match, total_employer_core, and total_all_contributions.
- The first scenario in the comparison is treated as the baseline for delta calculations, consistent with the existing workforce comparison pattern.
- "Favorable" for employer cost rate means lower (green = cost savings). "Favorable" for participation rate means higher (green = more engagement).
- The existing Recharts library and color scheme (`COMPARISON_COLORS`) are reused without introducing new charting dependencies.
- The DC Plan Comparison section is added as a new collapsible section below the existing workforce comparison charts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can visually identify the lowest-cost plan design scenario within 10 seconds of viewing the DC Plan Comparison section.
- **SC-002**: All five visualization components (3 trend charts, 1 bar chart, 1 summary table) render correctly for comparisons of 2-6 scenarios.
- **SC-003**: Chart data matches the underlying simulation data with no discrepancies in displayed values.
- **SC-004**: The comparison page loads all DC plan visualizations within 3 seconds of scenario selection for typical simulation data (3-year range, 2-4 scenarios).
- **SC-005**: All charts and tables remain usable on screen widths from 768px to 1920px without horizontal scrolling or overlapping elements.
- **SC-006**: Users can determine the delta between any two scenarios for any metric (cost rate, participation, deferral) directly from the summary table without manual calculation.
