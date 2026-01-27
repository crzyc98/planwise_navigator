# Feature Specification: Vesting Analysis

**Feature Branch**: `025-vesting-analysis`
**Created**: 2026-01-21
**Status**: Draft
**Input**: Add a Vesting Analysis section to PlanAlign Studio that compares current vs proposed vesting schedules to project forfeiture differences for terminated employees in the final simulation year.

## Overview

The Vesting Analysis feature enables plan sponsors to compare different vesting schedules and project their impact on employer contribution forfeitures. This is a projection tool that applies vesting schedules to existing simulation data at query time, allowing users to evaluate "what-if" scenarios without re-running simulations.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare Vesting Schedules (Priority: P1)

As a plan sponsor, I want to compare my current vesting schedule against a proposed alternative so that I can understand how the change would affect forfeiture amounts for terminated employees.

**Why this priority**: This is the core value proposition of the feature - enabling informed decision-making about vesting schedule changes by showing projected financial impact.

**Independent Test**: Can be fully tested by selecting two vesting schedules and running an analysis on completed simulation data, delivering a comparison of forfeiture amounts under each schedule.

**Acceptance Scenarios**:

1. **Given** a completed simulation with terminated employees who have employer contributions, **When** I select a current schedule (e.g., 5-Year Graded) and a proposed schedule (e.g., 3-Year Cliff), **Then** I see summary statistics showing total forfeitures under each schedule and the variance between them.

2. **Given** a completed simulation, **When** I run a vesting analysis, **Then** I see the count of terminated employees analyzed and total employer contributions subject to vesting.

3. **Given** I have run a vesting analysis, **When** I view the results, **Then** I can see forfeitures broken down by tenure band (e.g., 0-2 years, 2-5 years, 5-10 years).

---

### User Story 2 - View Employee-Level Details (Priority: P2)

As a plan administrator, I want to drill down into individual employee vesting calculations so that I can understand how specific cases are affected by schedule changes.

**Why this priority**: Provides transparency and audit capability for specific employee situations, supporting compliance and detailed analysis needs.

**Independent Test**: Can be tested by running an analysis and viewing a sortable data table with per-employee forfeiture calculations.

**Acceptance Scenarios**:

1. **Given** a completed vesting analysis, **When** I view employee details, **Then** I see a table with employee ID, tenure, total employer contributions, vested amount under current schedule, vested amount under proposed schedule, and forfeiture amounts under each.

2. **Given** the employee details table, **When** I sort by a column (e.g., forfeiture variance), **Then** the table reorders accordingly to help identify highest-impact employees.

---

### User Story 3 - Configure Hours-Based Vesting Credit (Priority: P3)

As a plan sponsor with an hours-based vesting requirement, I want to include hours thresholds in my analysis so that employees who don't meet the annual hours requirement lose vesting credit for that year.

**Why this priority**: Supports plans that use hours-of-service requirements (common in manufacturing, retail, and part-time workforce scenarios), extending the feature to more plan types.

**Independent Test**: Can be tested by enabling hours-based vesting on a schedule and verifying that employees below the hours threshold have reduced vesting credit.

**Acceptance Scenarios**:

1. **Given** a vesting schedule with hours-based credit enabled (threshold: 1,000 hours), **When** an employee worked 800 hours in their tenure year, **Then** their vesting credit for that year is reduced by one year of service.

2. **Given** hours-based vesting is disabled, **When** I run the analysis, **Then** all employees receive full tenure credit regardless of hours worked.

---

### User Story 4 - Navigate to Vesting Analysis (Priority: P4)

As a PlanAlign Studio user, I want to easily find and access the Vesting Analysis feature from the main navigation so that I can quickly perform schedule comparisons.

**Why this priority**: Usability requirement that ensures the feature is discoverable and accessible within the existing application structure.

**Independent Test**: Can be tested by navigating to the analytics section and finding the Vesting Analysis link.

**Acceptance Scenarios**:

1. **Given** I am logged into PlanAlign Studio with a workspace open, **When** I look at the navigation menu, **Then** I see a "Vesting" link in the analytics section.

2. **Given** I click on the Vesting navigation link, **When** the page loads, **Then** I see the Vesting Analysis interface with schedule selection options.

---

### Edge Cases

- What happens when no terminated employees exist in the selected simulation year?
  - Display a message indicating no terminated employees with employer contributions are available for analysis.

- What happens when a terminated employee has zero employer contributions?
  - Exclude them from the analysis (no forfeiture impact regardless of vesting schedule).

- What happens when an employee's tenure exceeds the maximum vesting schedule duration (e.g., 10 years of service with a 5-year schedule)?
  - The employee is considered 100% vested for any tenure at or above the schedule maximum.

- How are partial years of tenure handled?
  - Vesting percentage is based on completed whole years of service (truncated, not rounded).

- What if the selected scenario has not completed simulation?
  - Display a message indicating the scenario must be completed before vesting analysis can be run.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide the following eight pre-defined vesting schedules:
  - Immediate (100% at hire)
  - 2-Year Cliff (0% until year 2, then 100%)
  - 3-Year Cliff (0% until year 3, then 100%)
  - 4-Year Cliff (0% until year 4, then 100%)
  - QACA 2-Year (0% until year 2, then 100%)
  - 3-Year Graded (33.33% per year from year 1-3)
  - 4-Year Graded (25% per year from year 1-4)
  - 5-Year Graded (20% per year from year 1-5)

- **FR-002**: System MUST allow users to select two vesting schedules for comparison (current and proposed).

- **FR-003**: System MUST calculate forfeiture amounts for each terminated employee based on their tenure and the selected vesting schedules.

- **FR-004**: System MUST display summary statistics including total forfeitures under each schedule, the variance between schedules, and count of terminated employees analyzed.

- **FR-005**: System MUST display forfeiture breakdowns by tenure band using the existing tenure band configuration.

- **FR-006**: System MUST display a data table with employee-level vesting details that supports column sorting.

- **FR-007**: System MUST support optional hours-based vesting credit with a configurable hours threshold (default: 1,000 hours).

- **FR-008**: System MUST analyze only terminated employees from the specified simulation year who have employer contributions greater than zero.

- **FR-009**: System MUST default to analyzing the final (most recent) simulation year when no year is specified.

- **FR-010**: System MUST be accessible via navigation from the PlanAlign Studio analytics section.

- **FR-011**: System MUST calculate vesting percentage using complete years of service (tenure truncated to whole years).

### Key Entities

- **Vesting Schedule**: A named schedule type with a mapping of years-of-service to vesting percentage (e.g., Year 0 = 0%, Year 1 = 20%, etc.), plus optional hours-based credit configuration.

- **Vesting Analysis Request**: A comparison configuration specifying current schedule, proposed schedule, optional simulation year, and hours threshold settings.

- **Vesting Analysis Result**: The output containing summary statistics (total forfeitures, variance, employee count), tenure band breakdowns, and employee-level detail records.

- **Employee Vesting Detail**: Individual employee record with ID, tenure, employer contributions, vested amounts under each schedule, and calculated forfeiture amounts.

## Assumptions

- The `fct_workforce_snapshot` data already contains all required fields: `employee_hire_date`, `current_tenure`, `tenure_band`, `termination_date`, `employment_status`, `employer_match_amount`, `employer_core_amount`, `total_employer_contributions`, and `annual_hours_worked`.

- Vesting analysis is a projection tool applied at query time - it does not modify simulation data or require simulation re-runs.

- Users will select from pre-defined vesting schedules; custom schedule creation is out of scope.

- Break-in-service rules (for rehired employees) are not considered in this analysis.

- The analysis considers only employer contributions (match + core); employee deferrals are always 100% vested and excluded.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete a vesting schedule comparison in under 30 seconds from page load to viewing results.

- **SC-002**: Analysis results accurately calculate forfeiture amounts matching the defined vesting schedule percentages within $0.01 precision.

- **SC-003**: 90% of users can successfully run their first vesting analysis without external guidance or documentation.

- **SC-004**: The feature processes scenarios with up to 10,000 terminated employees without noticeable delay (under 5 seconds).

- **SC-005**: Tenure band forfeiture totals sum exactly to the overall forfeiture total (no rounding discrepancies).

## Out of Scope

- Break-in-service tracking (rehire vesting rules)
- Account balance accumulation over multiple years
- Vesting events recorded during simulation (new event type)
- Custom vesting schedule editor UI
- Export of analysis results to file formats

## Clarifications

### Session 2026-01-21

- Q: Which vesting schedules should be included? → A: Eight schedules: Immediate, 2-Year Cliff, 3-Year Cliff, 4-Year Cliff, QACA 2-Year, 3-Year Graded, 4-Year Graded, 5-Year Graded. Excluded: 6-Year Graded.
