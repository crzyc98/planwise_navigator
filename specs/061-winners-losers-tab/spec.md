# Feature Specification: Winners & Losers Comparison Tab

**Feature Branch**: `061-winners-losers-tab`
**Created**: 2026-03-03
**Status**: Draft
**Input**: User description: "Add a Winners & Losers tab to PlanAlign Studio where users pick two plan scenarios, choose a dimension (age band, tenure band), and see counts of winners and losers. Include a heatmap of winners vs losers by age and tenure."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare Two Plans by Age Band (Priority: P1)

A plan administrator wants to quickly see which age groups benefit and which lose out when switching from the baseline plan to an alternative plan design. They navigate to the "Winners & Losers" tab, which defaults to the baseline scenario as Plan A. They pick a second scenario as Plan B. The tab immediately shows a bar chart of winner and loser counts broken down by age band, making it obvious which demographic groups are better or worse off.

**Why this priority**: This is the core value of the feature — quickly surfacing demographic impact of plan design changes. Without this, the tab has no purpose.

**Independent Test**: Can be fully tested by selecting two scenarios with different plan designs and verifying that winner/loser counts appear grouped by age band.

**Acceptance Scenarios**:

1. **Given** a workspace with at least two completed scenarios, **When** the user navigates to the Winners & Losers tab, **Then** Plan A defaults to the baseline scenario (if one exists) and Plan B defaults to the next available scenario.
2. **Given** two scenarios are selected, **When** the tab loads, **Then** a bar chart displays winner and loser counts for each age band.
3. **Given** the age band view is displayed, **When** the user hovers over a bar, **Then** a tooltip shows the exact count and percentage of winners/losers in that band.

---

### User Story 2 - Compare Two Plans by Tenure Band (Priority: P1)

A plan administrator wants to understand tenure-based impact of plan changes. After viewing the age band breakdown, they scroll down (or the view is stacked below the age chart) to see the same winner/loser analysis by tenure band, without needing to change any settings.

**Why this priority**: Tenure-based analysis is equally critical for understanding plan impact on long-tenured vs. new employees. It is displayed alongside the age band view by default.

**Independent Test**: Can be tested by verifying that tenure band winner/loser counts appear below the age band chart for any two selected scenarios.

**Acceptance Scenarios**:

1. **Given** two scenarios are selected, **When** the tab loads, **Then** a bar chart of winner and loser counts by tenure band is displayed below the age band chart.
2. **Given** tenure bands are configured in the workspace, **When** the chart renders, **Then** it uses the workspace's configured tenure band labels.

---

### User Story 3 - View Age x Tenure Heatmap (Priority: P2)

A plan administrator wants to drill deeper into the intersection of age and tenure to identify specific pockets of employees who are disproportionately affected. Below the two bar charts, a heatmap grid appears with age bands on one axis and tenure bands on the other. Each cell is colored to indicate whether that group has net winners (green shading) or net losers (red shading), with intensity reflecting the magnitude.

**Why this priority**: The heatmap adds a second layer of insight that helps pinpoint specific demographic intersections. It builds on the P1 stories but is not required for basic analysis.

**Independent Test**: Can be tested by verifying the heatmap renders a grid of age bands vs. tenure bands with color-coded cells after selecting two scenarios.

**Acceptance Scenarios**:

1. **Given** two scenarios are selected, **When** the tab loads, **Then** a heatmap grid is displayed below the bar charts with age bands on one axis and tenure bands on the other.
2. **Given** a heatmap cell represents 5 employees with 3 winners and 2 losers, **When** the cell renders, **Then** it shows a green shade (net positive) with a tooltip showing "3 Winners / 2 Losers (5 total)".
3. **Given** a heatmap cell represents a group with 0 employees, **When** the cell renders, **Then** it appears as a neutral/gray cell with a tooltip indicating "No employees in this group".

---

### User Story 4 - Change Plan Selections (Priority: P2)

A plan administrator wants to compare different pairs of scenarios, not just the default baseline vs. alternative. They change Plan A or Plan B using dropdown selectors, and all charts and the heatmap update to reflect the new comparison.

**Why this priority**: Flexibility to compare any two plans makes the feature useful beyond the default baseline comparison.

**Independent Test**: Can be tested by changing Plan A and Plan B dropdowns and verifying all visualizations update.

**Acceptance Scenarios**:

1. **Given** the tab is loaded with default selections, **When** the user changes Plan B to a different scenario, **Then** all charts and the heatmap update to compare Plan A vs. the newly selected Plan B.
2. **Given** both Plan A and Plan B are set to the same scenario, **When** the comparison runs, **Then** all employees show as neutral (zero difference) — no winners or losers.

---

### Edge Cases

- What happens when a workspace has fewer than two completed scenarios? The tab displays a message: "At least two completed scenarios are required to compare winners and losers."
- What happens when employees exist in Plan A but not in Plan B (e.g., different hiring outcomes)? Only employees present in both scenarios are compared. A summary note shows how many employees were excluded from comparison.
- What happens when an age/tenure band has zero employees? The band still appears in the chart/heatmap but is visually indicated as empty.
- What happens when the workspace has no configured bands? The system uses the default band configuration from the seed data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a "Winners & Losers" tab in the Analytics section of PlanAlign Studio.
- **FR-002**: System MUST provide two plan scenario selectors (Plan A and Plan B) at the top of the tab.
- **FR-003**: Plan A MUST default to the baseline scenario if one exists; otherwise, it defaults to the first available scenario.
- **FR-004**: Plan B MUST default to the first available scenario that is not the same as Plan A.
- **FR-005**: System MUST classify each employee as a "winner" (better off under Plan B than Plan A), "loser" (worse off under Plan B than Plan A), or "neutral" (no meaningful change) based on comparing their outcomes across the two selected scenarios.
- **FR-006**: System MUST display a bar chart showing winner and loser counts grouped by age band.
- **FR-007**: System MUST display a bar chart showing winner and loser counts grouped by tenure band.
- **FR-008**: System MUST display a heatmap grid with age bands on one axis and tenure bands on the other, with cells colored by net winner/loser status.
- **FR-009**: All charts and the heatmap MUST include interactive tooltips showing exact counts and percentages.
- **FR-010**: System MUST only compare employees who are present (active) in both selected scenarios.
- **FR-011**: System MUST display a summary banner showing total winners, total losers, and total neutral employees across both plans.
- **FR-012**: System MUST persist the user's plan selections within the session (using browser storage) so returning to the tab retains selections.
- **FR-013**: Winner/loser determination MUST be based on total employer contribution value (employer match + any employer core contributions) for each employee.

### Key Entities

- **Plan Comparison Pair**: Two selected scenarios being compared, with one designated as the reference (Plan A) and one as the alternative (Plan B).
- **Employee Outcome**: The per-employee classification (winner, loser, neutral) derived by comparing a specific metric across Plan A and Plan B.
- **Band Group Result**: Aggregated winner/loser/neutral counts for a specific age band, tenure band, or age-tenure combination.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can identify which demographic groups are most impacted by a plan change within 30 seconds of opening the tab.
- **SC-002**: The tab loads and renders all three visualizations (age chart, tenure chart, heatmap) within 3 seconds for scenarios with up to 10,000 employees.
- **SC-003**: Winner/loser counts across all age bands sum to the same total as across all tenure bands and match the summary banner total.
- **SC-004**: Users can switch between any two scenarios and see updated results without navigating away from the tab.

## Assumptions

- The comparison is done at a single point in time (the final simulation year of the scenario).
- An employee is matched across scenarios by `employee_id`. Only employees with matching IDs in both scenarios are included in the comparison.
- Band configurations (age and tenure) are read from the workspace's current band settings; both scenarios use the same band definitions for grouping.
- "Neutral" employees are those with zero difference in the comparison metric between Plan A and Plan B (within a reasonable rounding threshold).
- The heatmap uses a diverging color scale: green for net winners, red for net losers, gray for empty cells.
