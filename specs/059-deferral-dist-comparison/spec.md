# Feature Specification: Deferral Rate Distribution Comparison

**Feature Branch**: `059-deferral-dist-comparison`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Add the ability to compare deferral rate distributions across scenarios"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare Deferral Distributions Across Scenarios (Priority: P1)

As an actuary, I want to see a grouped bar chart comparing deferral rate distributions across two or more scenarios so I can understand how plan design changes (auto-enrollment rates, match formulas, escalation policies) shift employee deferral behavior.

**Why this priority**: This is the core feature. Without the comparison chart, no other functionality has value. Actuaries need a visual side-by-side to quickly spot distribution shifts (e.g., "auto-enrollment pushes 15% more employees into the 6% bucket").

**Independent Test**: Can be fully tested by running two scenarios with different plan designs, navigating to the scenario comparison page, and verifying the grouped bar chart shows both distributions with correct bucket counts and percentages.

**Acceptance Scenarios**:

1. **Given** two completed scenarios with different auto-enrollment rates, **When** I view the scenario comparison page, **Then** I see a grouped bar chart with deferral rate buckets (0% through 10%+) on the X-axis and one bar per scenario per bucket, color-coded to match the scenario legend.
2. **Given** three completed scenarios, **When** I view the deferral distribution chart, **Then** all three scenarios appear as grouped bars with distinct colors consistent with the existing scenario color scheme.
3. **Given** a scenario where no employees are enrolled, **When** I view the distribution chart, **Then** that scenario shows zero-count bars across all buckets (not missing bars or errors).

---

### User Story 2 - View Distribution for a Specific Simulation Year (Priority: P2)

As an actuary, I want to select a specific simulation year to view the deferral distribution so I can track how the distribution evolves over the simulation horizon, not just the final year.

**Why this priority**: Actuaries often need to understand the trajectory of deferral behavior, not just the endpoint. Auto-escalation policies may take 3-5 years to fully shift distributions, and year-by-year analysis reveals this progression.

**Independent Test**: Can be tested by running a multi-year simulation, navigating to the comparison page, selecting different years from the year selector, and verifying the chart updates with the correct year's distribution data.

**Acceptance Scenarios**:

1. **Given** a multi-year simulation (2025-2027), **When** I open the deferral distribution chart, **Then** it defaults to the final simulation year's data.
2. **Given** the chart is showing the final year, **When** I select a different year from the year selector, **Then** the chart updates to show the distribution for the selected year.
3. **Given** a single-year simulation, **When** I view the chart, **Then** the year selector shows only one option and the chart displays that year's data.

---

### Edge Cases

- What happens when a scenario has zero enrolled employees in a given year? The chart should show that scenario with all-zero bars and a note indicating no enrolled employees.
- What happens when scenarios have different simulation year ranges? The year selector should only show years common to all selected scenarios.
- What happens when all employees in a scenario have the same deferral rate? The chart should show one tall bar in that bucket and zero bars elsewhere.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide deferral rate distribution data per scenario in the comparison response, bucketed into: 0%, 1%, 2%, 3%, 4%, 5%, 6%, 7%, 8%, 9%, 10%+.
- **FR-002**: System MUST include both a raw employee count and a percentage (of enrolled employees) for each bucket per scenario.
- **FR-003**: System MUST support querying the distribution for any simulation year, defaulting to the final year when no year is specified.
- **FR-004**: System MUST display a grouped bar chart with deferral rate buckets on the X-axis, percentage of enrolled employees on the Y-axis, and one bar per scenario per bucket.
- **FR-005**: Chart bars MUST use the same color scheme as other scenario comparison charts (consistent scenario-to-color mapping).
- **FR-006**: System MUST reuse the existing deferral distribution bucketing logic already implemented in the single-scenario analytics page.
- **FR-007**: Chart MUST display a tooltip on hover showing the bucket label, scenario name, employee count, and percentage.
- **FR-008**: The deferral distribution chart MUST appear within the existing DC Plan comparison section on the scenario comparison page.

### Key Entities

- **DeferralDistributionBucket**: A single bucket in the distribution containing a rate label (e.g., "6%"), employee count, and percentage of enrolled employees in that bucket.
- **DeferralDistributionComparison**: Per-scenario distribution containing scenario identifier, scenario display name, and the list of distribution buckets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Actuaries can visually compare deferral rate distributions across 2-6 scenarios in a single grouped bar chart view.
- **SC-002**: Distribution data is available for any simulation year, with the default view showing the final year.
- **SC-003**: The chart renders within 2 seconds of page load or year selection change.
- **SC-004**: All distribution bucket percentages sum to 100% (within rounding tolerance) per scenario, ensuring data integrity.

## Assumptions

- The existing deferral distribution bucketing logic (using `current_deferral_rate` from the workforce snapshot) is the correct source of truth and will be reused for the comparison view.
- Only enrolled employees are included in the distribution, consistent with the single-scenario analytics page.
- The feature follows the same visual patterns established by the DC Plan comparison charts (feature 057), including color scheme, tooltip formatting, and placement within the DC Plan collapsible section.
- Maximum of 6 scenarios can be compared simultaneously, consistent with the existing comparison page limit.

## Clarifications

### Session 2026-02-21

- Q: Should the Y-axis display percentage or raw count? → A: Percentage of enrolled employees (normalizes across different-sized workforces). Raw counts are available in the tooltip (FR-007).
