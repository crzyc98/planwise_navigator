# Feature Specification: Compare Variance Alignment & Copy Button

**Feature Branch**: `015-compare-variance-copy`
**Created**: 2026-01-08
**Status**: Draft
**Input**: User description: "on the compare page, the year by year breakdown section, the variance is in a different font and alignment is off, the font could be fine, but i want it to align with the other rows so that i can tell which year. also could you add a copy button? to each table? you know how you can copy and then paste from that copy into for instance a excel sheet"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Copy Table Data to Excel (Priority: P1)

A user viewing the Compare DC Plan Costs page wants to copy the year-by-year breakdown tables to paste into Excel for further analysis or reporting purposes.

**Why this priority**: Users frequently need to share comparison data with stakeholders or incorporate it into reports outside the application. Without copy functionality, users must manually re-type or screenshot data, which is error-prone and time-consuming.

**Independent Test**: Can be fully tested by clicking the copy button on any metric table and pasting into Excel/Google Sheets - the data should appear in a properly formatted grid with headers.

**Acceptance Scenarios**:

1. **Given** the user is viewing a year-by-year breakdown table with data for Participation Rate, **When** they click the copy button for that table, **Then** the table data is copied to clipboard in tab-separated format suitable for Excel.

2. **Given** the user has copied a table, **When** they paste into Excel, **Then** the data appears with columns matching the years and rows matching Baseline/Comparison/Variance values.

3. **Given** the user clicks the copy button, **When** the copy succeeds, **Then** visual feedback is shown (e.g., "Copied!" tooltip or icon change) confirming the action.

---

### User Story 2 - Variance Row Alignment Fix (Priority: P1)

A user analyzing year-by-year data wants the variance row to align properly with the year columns so they can quickly scan and compare values for each year.

**Why this priority**: The misaligned variance row makes it difficult to correlate variance values with their corresponding years, reducing the utility of the comparison view for quick analysis.

**Independent Test**: Can be verified visually by comparing the variance row cell positions with the Baseline and Comparison rows - all values for a given year should be vertically aligned in the same column.

**Acceptance Scenarios**:

1. **Given** a metric table with 3 years of data (2025, 2026, 2027), **When** viewing the table, **Then** the variance value for 2025 aligns directly under the Baseline and Comparison values for 2025.

2. **Given** a variance row with values, **When** comparing to other rows, **Then** the text alignment (right-aligned) matches the Baseline and Comparison rows.

3. **Given** a table with narrow viewport, **When** the table is horizontally scrolled, **Then** the variance row maintains alignment with other rows throughout the scroll.

---

### User Story 3 - Copy All Tables at Once (Priority: P3)

A user wants to copy all metric tables from the year-by-year breakdown section in a single action to streamline export workflows.

**Why this priority**: While individual table copy provides core functionality, power users analyzing multiple metrics would benefit from bulk export. This is an enhancement over the core copy feature.

**Independent Test**: Can be tested by clicking a "Copy All" button and pasting into Excel - all 6 metric tables should appear with clear separation between them.

**Acceptance Scenarios**:

1. **Given** the user is on the Compare page with 6 metric tables loaded, **When** they click the "Copy All Tables" button, **Then** all tables are copied to clipboard with clear headers separating each metric.

---

### Edge Cases

- What happens when a table has no data (e.g., only one scenario selected)? Copy button should be disabled or show appropriate feedback.
- What happens if clipboard access is denied by browser? Show error message explaining clipboard permission is required.
- How does copy work on mobile devices? Fall back to standard browser clipboard behavior; copy button may trigger share sheet on some devices.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a copy button for each metric table in the year-by-year breakdown section, positioned in the table header row next to the metric title.
- **FR-002**: System MUST copy table data in tab-separated values (TSV) format when copy button is clicked.
- **FR-003**: Copied data MUST include headers (Scenario, year columns) and all rows (Baseline, Comparison, Variance).
- **FR-004**: System MUST display visual feedback when copy succeeds (icon change, tooltip, or notification).
- **FR-005**: Variance row cells MUST be right-aligned to match the alignment of Baseline and Comparison row cells.
- **FR-006**: Variance row content MUST align within the same column boundaries as other rows for each year.
- **FR-007**: System MUST disable the copy button when table has no data loaded.
- **FR-008**: System SHOULD provide a "Copy All Tables" button to copy all 6 metric tables at once.
- **FR-009**: System MUST display an error message if clipboard access fails.

### Key Entities

- **MetricTable**: Component displaying a single metric's year-by-year breakdown with Baseline, Comparison, and Variance rows.
- **CopyableTable**: Wrapper or enhanced MetricTable with copy functionality.
- **ClipboardData**: Tab-separated string representation of table data suitable for spreadsheet applications.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can copy any metric table and successfully paste into Excel within 3 seconds (click to paste complete).
- **SC-002**: 100% of pasted data appears in correct cells when pasted into Excel (no misaligned columns or missing values).
- **SC-003**: Variance row values visually align with year columns - no horizontal offset visible when comparing to other rows.
- **SC-004**: Copy feedback appears within 500ms of button click.
- **SC-005**: Copy functionality works across all supported browsers (Chrome, Firefox, Safari, Edge latest versions).

## Assumptions

- Users have clipboard access enabled in their browser (most browsers allow this by default for user-initiated actions).
- Tab-separated format is universally compatible with Excel, Google Sheets, and similar spreadsheet applications.
- The current font in the variance row is acceptable; only alignment needs to be fixed.
- All 6 metric tables in the year-by-year breakdown section require copy functionality.

## Clarifications

### Session 2026-01-08

- Q: Where should the copy button be positioned on each metric table? → A: In the table header row, next to the metric title
