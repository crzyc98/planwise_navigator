# Feature Specification: Compare Page Table Redesign

**Feature Branch**: `014-compare-table-redesign`
**Created**: 2026-01-07
**Status**: Implemented
**Input**: User description: "the compare page is a little hard to follow, the data table at the bottom. you would have separate tables for each metric going down the page and then could we have row 1 be baseline and row 2 be the compare and the third row be the variance and the columns would be each of the simulation years from left to right like 2026, 2027 etc."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Metrics in Dedicated Tables (Priority: P1)

As a benefits analyst comparing retirement plan scenarios, I want each metric displayed in its own dedicated table so that I can focus on one metric at a time without visual clutter and easily scan across years for that specific metric.

**Why this priority**: This is the core request—reorganizing the layout from a single dense table into multiple focused tables. It directly addresses the "hard to follow" feedback.

**Independent Test**: Can be fully tested by loading the compare page with two scenarios and verifying that each metric (Participation Rate, Avg Deferral Rate, Employer Match, Employer Core, Total Employer Cost, Employer Cost Rate) appears in its own separate table.

**Acceptance Scenarios**:

1. **Given** two completed scenarios are selected for comparison, **When** I view the year-by-year breakdown section, **Then** I see 6 separate tables, one for each metric.

2. **Given** I am viewing the compare page, **When** I scroll down through the year-by-year section, **Then** each table is clearly labeled with its metric name as a header.

3. **Given** the page loads, **When** I scan the layout, **Then** the metric tables are stacked vertically (one below the other) for easy scrolling.

---

### User Story 2 - View Baseline and Comparison Rows with Variance (Priority: P1)

As a benefits analyst, I want each metric table to show the baseline scenario in row 1, the comparison scenario in row 2, and the variance in row 3 so that I can easily compare values and see the difference at a glance.

**Why this priority**: This row structure is essential for the new table design—it defines how data is presented within each metric table.

**Independent Test**: Can be fully tested by verifying that each metric table has exactly 3 rows labeled "Baseline", "Comparison", and "Variance" respectively.

**Acceptance Scenarios**:

1. **Given** a metric table is displayed, **When** I look at the rows, **Then** row 1 shows the baseline scenario values with a label indicating "Baseline".

2. **Given** a metric table is displayed, **When** I look at row 2, **Then** it shows the comparison scenario values with a label indicating the comparison scenario name.

3. **Given** a metric table is displayed, **When** I look at row 3, **Then** it shows the calculated variance (difference) between comparison and baseline with appropriate formatting (positive/negative indicators).

---

### User Story 3 - View Simulation Years as Columns (Priority: P1)

As a benefits analyst, I want the columns in each metric table to represent simulation years (2026, 2027, etc.) from left to right so that I can easily track how values change over time.

**Why this priority**: This column orientation is fundamental to the new table structure and enables year-over-year trend analysis.

**Independent Test**: Can be fully tested by verifying that column headers in each metric table show the simulation years in chronological order from left to right.

**Acceptance Scenarios**:

1. **Given** a simulation covers years 2025-2027, **When** I view any metric table, **Then** the columns are labeled 2025, 2026, 2027 from left to right.

2. **Given** a simulation covers years 2026-2030, **When** I view any metric table, **Then** I see 5 year columns in chronological order.

3. **Given** each metric table, **When** I compare them, **Then** all tables have the same year columns in the same order for consistent comparison.

---

### User Story 4 - Visual Variance Indicators (Priority: P2)

As a benefits analyst, I want the variance row to use color coding (red for cost increases, green for cost decreases) so that I can quickly identify favorable vs unfavorable differences.

**Why this priority**: While the core layout change is P1, visual indicators enhance usability and are a natural addition once the table structure is in place.

**Independent Test**: Can be fully tested by comparing scenarios with known differences and verifying color coding appears correctly in the variance row.

**Acceptance Scenarios**:

1. **Given** a cost metric where comparison is higher than baseline, **When** I view the variance row, **Then** the variance value is displayed in red (indicating increased cost).

2. **Given** a cost metric where comparison is lower than baseline, **When** I view the variance row, **Then** the variance value is displayed in green (indicating decreased cost).

3. **Given** a rate metric (like Participation Rate) where higher is better, **When** comparison exceeds baseline, **Then** the variance is displayed in green (positive change is good).

---

### Edge Cases

- What happens when a scenario has no data for a particular year? Display "-" in that cell.
- How does the system handle a single-year simulation? Display tables with only one year column.
- What happens when baseline and comparison values are identical? Show 0 or 0% in variance row with neutral styling (gray).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display each metric (Participation Rate, Avg Deferral Rate, Employer Match, Employer Core, Total Employer Cost, Employer Cost Rate) in its own separate table.
- **FR-002**: Each metric table MUST have exactly 3 rows: Baseline (row 1), Comparison (row 2), Variance (row 3).
- **FR-003**: Each metric table MUST have columns representing simulation years in chronological order (left to right).
- **FR-004**: The first column of each table MUST contain row labels ("Baseline", "[Comparison Scenario Name]", "Variance").
- **FR-005**: Variance values MUST be calculated as (Comparison - Baseline) for each year.
- **FR-006**: Cost metrics (Employer Match, Employer Core, Total Employer Cost, Employer Cost Rate) MUST display positive variance in red (cost increase) and negative variance in green (cost decrease).
- **FR-007**: Rate metrics (Participation Rate, Avg Deferral Rate) MUST display positive variance in green (improvement) and negative variance in red (decline).
- **FR-008**: Each metric table MUST include a header row with the metric name prominently displayed.
- **FR-009**: Tables MUST be stacked vertically in the following order: Participation Rate, Avg Deferral Rate, Employer Match, Employer Core, Total Employer Cost, Employer Cost Rate.
- **FR-010**: Values MUST be formatted appropriately: currency for dollar amounts, percentages for rates.

### Key Entities

- **Metric Table**: A self-contained table displaying one metric with Baseline/Comparison/Variance rows and year columns.
- **Year Column**: A column representing a single simulation year's data across all three rows.
- **Variance Row**: The calculated difference between comparison and baseline values with color-coded display.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can identify the variance for any metric in any year within 2 seconds of viewing the table (improved from current layout requiring mental calculation).
- **SC-002**: Users can compare baseline vs comparison values for a single metric across all years without scrolling horizontally within each table.
- **SC-003**: 90% of users report the new layout is "easier to follow" compared to the previous single-table format (user feedback metric).
- **SC-004**: Each metric table fits within the viewport width for standard desktop screens (1280px+), eliminating horizontal scroll within tables.

## Assumptions

- The current compare page already has all the necessary data (Baseline, Comparison values per year per metric).
- The existing variance calculation logic can be reused.
- The existing color-coding logic for variance indicators can be reused.
- Users primarily access this page on desktop screens; mobile optimization is not in scope for this change.
- The 6 metrics currently displayed (Participation Rate, Avg Deferral Rate, Employer Match, Employer Core, Total Employer Cost, Employer Cost Rate) are the complete set—no new metrics are being added.
