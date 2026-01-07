# Feature Specification: Employer Cost Ratio Metrics for Scenario Comparison

**Feature Branch**: `013-cost-comparison-metrics`
**Created**: 2026-01-07
**Status**: Implemented
**Input**: User description: "On the compare costs page where we can compare two scenarios, add the average employer contribution received (ER $ / compensation for each employee) and another with the total employer money / total salary. Goal is to compare the costs of the retirement plan under different scenarios, looking both at each year and over the full simulation period."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Average Employer Contribution Rate Per Employee (Priority: P1)

As a benefits analyst comparing two retirement plan scenarios, I want to see the average employer contribution rate per employee (total employer dollars divided by total compensation) so that I can understand the effective employer "spend rate" as a percentage of payroll for each scenario.

**Why this priority**: This is the primary metric the user requested. Understanding employer cost as a percentage of compensation is fundamental for budgeting and comparing plan designs—it normalizes the cost to be independent of workforce size changes.

**Independent Test**: Can be fully tested by running two scenarios with different plan designs and verifying the UI displays the employer contribution rate (ER$/Compensation) for each scenario in both the summary cards and year-by-year table.

**Acceptance Scenarios**:

1. **Given** two completed scenarios with different employer match formulas, **When** I select them for comparison, **Then** I see a metric card showing "Avg Employer Contribution Rate" displaying the total employer dollars / total compensation for each scenario with variance calculation.

2. **Given** a scenario with varying compensation growth over years, **When** I view the year-by-year breakdown, **Then** each year's row includes the employer contribution rate for that year (that year's employer cost / that year's total compensation).

3. **Given** two scenarios where the comparison scenario has a higher match rate, **When** I compare them, **Then** the variance indicator shows the increase in employer contribution rate (displayed appropriately since higher cost = red indicator).

---

### User Story 2 - View Total Employer Cost as Percentage of Total Payroll (Priority: P1)

As a finance executive reviewing retirement plan costs, I want to see the total employer contribution as a percentage of total payroll across the full simulation period so that I can understand the aggregate cost impact of different plan designs over multiple years.

**Why this priority**: This complements Story 1 by providing a full-period aggregate view. Many cost analyses require both annual and cumulative perspectives.

**Independent Test**: Can be fully tested by verifying the Grand Totals Summary section displays the employer cost / total compensation percentage alongside the existing dollar amounts for both scenarios.

**Acceptance Scenarios**:

1. **Given** two completed scenarios, **When** I view the Grand Totals Summary section, **Then** I see the total employer cost as a percentage of total payroll for each scenario (in addition to the existing dollar totals).

2. **Given** a multi-year simulation (2025-2027), **When** I view the comparison summary, **Then** the percentage reflects the sum of all employer costs divided by the sum of all compensation across all years.

---

### User Story 3 - Compare Employer Cost Metrics Across Individual Years (Priority: P2)

As a benefits analyst, I want to see the employer contribution rate for each individual year in the comparison table so that I can identify trends over time and understand how costs evolve as the workforce matures.

**Why this priority**: Year-over-year trends help identify if cost differences are temporary (e.g., due to new hire ramp-up) or permanent structural differences between plan designs.

**Independent Test**: Can be fully tested by verifying the year-by-year breakdown table includes a new row for employer contribution rate (%) for each year.

**Acceptance Scenarios**:

1. **Given** two scenarios with different auto-enrollment settings, **When** I view the year-by-year breakdown, **Then** I see a row for "Employer Cost Rate" showing (employer match + employer core) / total compensation for that year.

2. **Given** Year 1 has lower participation than Year 3 due to new hires ramping up, **When** I view the trend across years, **Then** I can see the employer cost rate increasing as participation matures.

---

### Edge Cases

- What happens when a scenario has zero total compensation for a year? Display "N/A" or 0.00% with appropriate handling to avoid division by zero.
- How does the system handle scenarios with zero employer contributions? Display 0.00% as the rate (valid scenario where no one is participating or earning match).
- What happens when compensation data is missing from the workforce snapshot? The metric should gracefully degrade (show "N/A" or exclude from calculations).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a summary metric card showing "Avg Employer Contribution Rate" calculated as (total employer match + total employer core) / total compensation for each scenario.
- **FR-002**: System MUST display the employer cost rate in the Grand Totals Summary section as a percentage alongside existing dollar amounts.
- **FR-003**: System MUST include a new row "Employer Cost Rate" in the year-by-year breakdown table showing the rate for each simulation year.
- **FR-004**: System MUST calculate variance between baseline and comparison scenarios for the employer cost rate metric.
- **FR-005**: System MUST treat the employer cost rate as a "cost" metric (positive variance = red indicator, negative = green indicator).
- **FR-006**: System MUST handle edge cases (zero compensation, missing data) gracefully without errors.
- **FR-007**: System MUST use consistent decimal precision (2 decimal places) for all percentage displays.

### Key Entities *(include if feature involves data)*

- **Total Compensation**: Sum of `prorated_annual_compensation` for all active employees in a given year/period.
- **Total Employer Cost**: Sum of `employer_match_amount` + `employer_core_amount` for all employees.
- **Employer Cost Rate**: Calculated metric = Total Employer Cost / Total Compensation * 100 (expressed as percentage).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view employer cost as a percentage of payroll for both summary and year-by-year views within 2 seconds of scenario selection.
- **SC-002**: All displayed percentages are accurate to within 0.01% of calculated values from the underlying data.
- **SC-003**: Users can identify which scenario has lower employer cost rate at a glance via visual indicators (color coding).
- **SC-004**: The feature reduces the need for manual Excel exports to calculate cost ratios by 80% (users can see the metric directly in the comparison page).

## Assumptions

- The `fct_workforce_snapshot` table contains `prorated_annual_compensation` field for each employee that can be summed to get total payroll (verified: field exists).
- The existing `employer_match_amount` and `employer_core_amount` fields are accurate and complete.
- Compensation data is populated for all active employees in all simulation years.
- The API will need to be extended to query and aggregate `prorated_annual_compensation` from the workforce snapshot (currently not returned by the analytics endpoint).
