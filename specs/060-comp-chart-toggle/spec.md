# Feature Specification: Compensation Chart Toggle (Average/Total) with CAGR

**Feature Branch**: `060-comp-chart-toggle`
**Created**: 2026-03-03
**Status**: Draft
**Input**: User description: "on the analytics page there is an average compensation all employees chart, can you make a toggle so we can switch it from average to total and show the cagr in the title?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Toggle Between Average and Total Compensation (Priority: P1)

As an analyst viewing the Analytics Dashboard, I want to toggle the "Average Compensation - All Employees" chart between showing average compensation and total compensation so I can quickly compare per-employee trends vs. aggregate payroll costs without navigating to a different view.

**Why this priority**: This is the core feature request — without the toggle, no new insight is delivered.

**Independent Test**: Can be fully tested by clicking the toggle on the compensation chart and verifying the chart switches between average and total values with correct formatting.

**Acceptance Scenarios**:

1. **Given** the Analytics Dashboard is loaded with simulation results, **When** I view the compensation chart, **Then** it defaults to showing "Average Compensation" with the toggle indicating "Average" is selected.
2. **Given** the chart is showing average compensation, **When** I click the toggle to switch to "Total", **Then** the chart updates to display total compensation values for each simulation year.
3. **Given** the chart is showing total compensation, **When** I click the toggle to switch back to "Average", **Then** the chart reverts to displaying average compensation values.
4. **Given** I switch the toggle, **When** the chart updates, **Then** the Y-axis scale, formatting, and tooltip values adjust to reflect the selected metric (e.g., "$125K" for average vs. "$12.5M" for total).

---

### User Story 2 - Display CAGR in Chart Title (Priority: P1)

As an analyst, I want the compensation chart title to include the Compound Annual Growth Rate (CAGR) so I can immediately understand the growth trend without needing to calculate it manually or look elsewhere on the page.

**Why this priority**: Equally important as the toggle — the CAGR display provides immediate analytical context and was explicitly requested.

**Independent Test**: Can be fully tested by loading the Analytics Dashboard and verifying the chart title includes the CAGR percentage for the displayed metric.

**Acceptance Scenarios**:

1. **Given** the chart is showing average compensation data spanning multiple years, **When** I view the chart title, **Then** it includes the CAGR percentage (e.g., "Average Compensation - All Employees ($K) — CAGR: 3.2%").
2. **Given** the chart is showing total compensation, **When** I view the chart title, **Then** the CAGR updates to reflect the total compensation growth rate (e.g., "Total Compensation - All Employees ($M) — CAGR: 5.1%").
3. **Given** only one year of simulation data exists, **When** I view the chart title, **Then** the CAGR is not displayed since a growth rate requires at least two data points.

---

### Edge Cases

- What happens when there is only one simulation year? CAGR cannot be calculated — display the chart without a CAGR value.
- What happens when total compensation values are very large? Y-axis and tooltip formatting should scale appropriately (e.g., use "$M" for millions instead of "$K" for thousands).
- What happens when average compensation is $0 for a starting year? CAGR calculation would be undefined — display "N/A" for CAGR.
- What happens when the page is refreshed or re-navigated to? The toggle should reset to its default state (average compensation).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a toggle control on the "Average Compensation - All Employees" chart that allows switching between "Average" and "Total" views.
- **FR-002**: When "Average" is selected, the chart MUST display the average compensation per employee per simulation year (current behavior).
- **FR-003**: When "Total" is selected, the chart MUST display the total (aggregate) compensation across all employees per simulation year.
- **FR-004**: The chart title MUST dynamically include the CAGR percentage for whichever metric is currently displayed.
- **FR-005**: The CAGR MUST be calculated as the compound annual growth rate from the first simulation year to the last simulation year of the displayed data.
- **FR-006**: The Y-axis labels, tooltip values, and unit indicators MUST update to reflect the appropriate scale for the selected metric (thousands for average, millions for total if applicable).
- **FR-007**: The toggle MUST default to "Average" when the Analytics Dashboard is first loaded.
- **FR-008**: When simulation data contains fewer than two years, the CAGR MUST NOT be displayed in the title.

### Key Entities

- **Workforce Progression**: Per-year data containing headcount, average compensation, and total compensation — sourced from the existing simulation results.
- **CAGR Metric**: A derived value calculated from the first and last year's compensation values using the standard CAGR formula: ((end_value / start_value)^(1/years) - 1) x 100.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can switch between average and total compensation views with a single click, and the chart updates instantly.
- **SC-002**: The CAGR value displayed in the chart title matches a manual calculation from the underlying data (within 0.1% rounding tolerance).
- **SC-003**: All chart elements (title, Y-axis, tooltips, legend) consistently reflect the currently selected metric at all times.
- **SC-004**: The feature works correctly for simulations spanning 1 year (no CAGR shown) through 10+ years.

## Assumptions

- The workforce progression data already contains headcount and average compensation, so total compensation can be derived on the frontend as headcount x average compensation without requiring backend changes.
- The existing `cagr_metrics` array in the simulation results may already contain relevant CAGR data; if not, CAGR can be calculated on the frontend from the chart data.
- The toggle will be a simple two-option control (segmented button or similar) placed near the chart title, consistent with the existing UI style.
