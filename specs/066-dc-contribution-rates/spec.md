# Feature Specification: Trended Contribution Percentage Rates for DC Plan Analytics

**Feature Branch**: `066-dc-contribution-rates`
**Created**: 2026-03-09
**Status**: Draft
**Input**: GitHub Issue #202 — "Add trended contribution percentage rates to DC Plan analytics page"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Year-over-Year Contribution Rate Trends (Priority: P1)

A plan administrator opens the DC Plan comparison page after running a multi-year simulation and sees a trended line chart showing employee contribution rate, employer match rate, employer core rate, and total contribution rate — all expressed as a percentage of total compensation — across all simulation years.

**Why this priority**: This is the core value of the feature. Without trended percentage rates, administrators must mentally compute rates from dollar amounts, making it difficult to spot trends or compare scenarios.

**Independent Test**: Can be fully tested by running a 3-year simulation, opening the DC Plan comparison page, and verifying the new "Contribution Rate Trends" chart renders with 4 series across all years.

**Acceptance Scenarios**:

1. **Given** a completed multi-year simulation (e.g., 2025-2027), **When** the user navigates to the DC Plan comparison page, **Then** a "Contribution Rate Trends" line chart is displayed with four series: Employee Contribution Rate (%), Employer Match Rate (%), Employer Core Rate (%), and Total Contribution Rate (%).
2. **Given** the contribution rates chart is displayed, **When** the user hovers over a data point, **Then** a tooltip shows the exact percentage value for that series and year.
3. **Given** a simulation where compensation grows but deferral rates stay constant, **When** the user views the chart, **Then** the employee contribution rate remains stable across years (validating the rate is relative to compensation, not an absolute dollar trend).

---

### User Story 2 - Backend Provides Contribution Rate Data (Priority: P1)

The analytics API returns contribution rate percentages alongside existing dollar-amount data so the frontend can render trend charts without client-side computation.

**Why this priority**: The frontend chart depends on the API providing these calculated rates. This is a prerequisite for Story 1.

**Independent Test**: Can be tested by calling the analytics API endpoint for a completed simulation and verifying the response includes the four new rate fields in the `contribution_by_year` array.

**Acceptance Scenarios**:

1. **Given** a completed simulation with contribution data, **When** the analytics API is called, **Then** the response includes employee_contribution_rate, match_contribution_rate, core_contribution_rate, and total_contribution_rate for each year.
2. **Given** a simulation year with zero total compensation (no active employees), **When** the analytics API computes rates, **Then** all rate fields are returned as 0.0 (no division-by-zero errors).
3. **Given** contribution data for a year, **When** rates are computed, **Then** total_contribution_rate equals the sum of the other three rates.

---

### User Story 3 - Contribution Rates in Summary Table (Priority: P2)

The summary comparison table on the DC Plan page includes the four contribution rate percentages for quick at-a-glance comparison between scenarios or years.

**Why this priority**: Adds convenience but is supplementary to the trend chart. Users can still see rates in the chart without this.

**Independent Test**: Can be tested by verifying the summary comparison table includes rows or columns for the four contribution rate percentages.

**Acceptance Scenarios**:

1. **Given** the DC Plan comparison page is displayed, **When** the user views the summary table, **Then** the table includes Total Contribution Rate (%), Employee Contribution Rate (%), Employer Match Rate (%), and Employer Core Rate (%) alongside existing metrics.

---

### Edge Cases

- What happens when total compensation is zero for a simulation year? Rates default to 0.0%.
- What happens when employer core contributions are not configured for a plan design? The core rate is 0.0% and the series still appears in the chart.
- What happens for a single-year simulation? The chart renders with one data point per series.
- What happens when all employees are terminated in a given year? Rates are 0.0% since there is no compensation base.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The analytics service MUST compute employee contribution rate as (total employee deferrals / total compensation) x 100 for each simulation year.
- **FR-002**: The analytics service MUST compute employer match contribution rate as (total employer match / total compensation) x 100 for each simulation year.
- **FR-003**: The analytics service MUST compute employer core contribution rate as (total employer core / total compensation) x 100 for each simulation year.
- **FR-004**: The analytics service MUST compute total contribution rate as the sum of employee, match, and core contribution rates for each simulation year.
- **FR-005**: The analytics API response MUST include the four new rate fields in each year's contribution summary data.
- **FR-006**: The DC Plan comparison page MUST display a "Contribution Rate Trends" line chart with four series (employee, match, core, total) across all simulation years.
- **FR-007**: The contribution rate chart MUST display values as percentages with consistent formatting (e.g., "6.5%").
- **FR-008**: The system MUST handle zero-compensation scenarios gracefully, returning 0.0% for all rates without errors.
- **FR-009**: The contribution rate trends chart MUST follow the same visual styling (colors, tooltips, legends) as existing trend charts on the DC Plan page.
- **FR-010**: The summary comparison table SHOULD include the four contribution rate percentages.

### Key Entities

- **ContributionYearSummary**: Represents aggregated contribution data for a single simulation year. Extended with four new rate fields (employee_contribution_rate, match_contribution_rate, core_contribution_rate, total_contribution_rate).
- **Workforce Snapshot**: Source data containing per-employee compensation and contribution amounts that are aggregated into rates.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can see contribution rate trends (employee, match, core, total) as percentages of compensation across all simulation years on the DC Plan page.
- **SC-002**: Contribution rate values are accurate to within 0.01 percentage points when verified against manual calculations from the underlying data.
- **SC-003**: The new chart renders within 2 seconds of page load, consistent with existing chart performance.
- **SC-004**: Zero-compensation edge cases produce 0.0% rates without any errors or broken UI elements.
- **SC-005**: The chart provides interactive tooltips showing exact percentage values for each data point.

## Assumptions

- The existing `fct_workforce_snapshot` data model already contains all required source fields (prorated_annual_compensation, prorated_annual_contributions, employer_match_amount, employer_core_amount) and no new database models are needed.
- The existing contribution_by_year array structure in the analytics API response can be extended with new fields without breaking existing consumers.
- The chart library already in use on the DC Plan page supports multi-series line charts (as evidenced by existing trend charts).
- Rate calculations are aggregate (plan-level totals) rather than per-employee averages.
