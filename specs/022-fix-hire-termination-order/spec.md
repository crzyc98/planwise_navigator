# Feature Specification: Fix Hire Date Before Termination Date Ordering

**Feature Branch**: `022-fix-hire-termination-order`
**Created**: 2026-01-21
**Status**: Draft
**Input**: User description: "there is a bug in the implementation of this spec, i am seeing employees with hire dates after their termination date. the hire event should happen first and then termination dates can only happen after they are hired."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Termination Dates Follow Hire Dates (Priority: P1)

As a workforce analyst, I need termination events to always occur after an employee's hire date so that the simulation produces logically consistent workforce data that accurately reflects real employment timelines.

**Why this priority**: This is a critical data integrity issue. Employees cannot be terminated before they are hired - this violates fundamental business logic and produces invalid simulation results that cannot be used for analysis.

**Independent Test**: Query the database for any employees where termination_date < hire_date. The result should be zero records.

**Acceptance Scenarios**:

1. **Given** an employee with hire_date of 2026-03-15, **When** a termination event is generated for that employee in 2026, **Then** the termination effective_date must be >= 2026-03-15

2. **Given** an employee hired mid-year (e.g., June 1), **When** the termination date is calculated using the hash-based distribution, **Then** the termination date is constrained to be between hire_date and December 31 of that year

3. **Given** an employee hired late in the year (e.g., December 1), **When** they are selected for termination, **Then** their termination date falls between their hire_date and December 31

---

### User Story 2 - New Hire Termination Date Consistency (Priority: P1)

As a workforce analyst, I need new hire terminations to have termination dates that logically follow their hire dates so that tenure calculations and proration are accurate.

**Why this priority**: New hire terminations are a specific subset affected by this bug. Their termination dates must occur after their hire dates for correct tenure calculation and contribution proration.

**Independent Test**: Query fct_workforce_snapshot for detailed_status_code = 'new_hire_termination' and verify all have termination_date > hire_date.

**Acceptance Scenarios**:

1. **Given** a new hire who started on 2026-04-01 and is selected for termination, **When** their termination event is generated, **Then** the termination_date is after 2026-04-01

2. **Given** a new hire with employee_hire_date in the current simulation year, **When** they have a termination event, **Then** termination_date - hire_date >= 0 days

---

### User Story 3 - Polars Pipeline Parity (Priority: P2)

As a developer, I need the Polars pipeline to enforce the same hire-before-termination constraint as the SQL pipeline so that both execution modes produce consistent, valid results.

**Why this priority**: The system supports both SQL (dbt) and Polars execution modes. Both must enforce the same business rules to ensure reproducibility regardless of execution mode.

**Independent Test**: Run simulation in both SQL and Polars modes and compare employee records - both should have zero employees with termination_date < hire_date.

**Acceptance Scenarios**:

1. **Given** simulation running in Polars mode, **When** termination events are generated, **Then** all termination dates are >= the employee's hire date

---

### User Story 4 - Tenure At Termination Accuracy (Priority: P1)

As a workforce analyst, I need terminated employees to show tenure calculated to their termination date (not year-end) so that tenure values accurately reflect actual time employed.

**Why this priority**: Tenure is used for vesting calculations, benefit proration, and analytics. Showing year-end tenure for terminated employees overstates their service and produces incorrect downstream calculations.

**Independent Test**: Query fct_workforce_snapshot for terminated employees and verify current_tenure = floor((termination_date - hire_date) / 365.25).

**Acceptance Scenarios**:

1. **Given** an employee hired 2024-08-01 and terminated 2026-01-10, **When** their record appears in fct_workforce_snapshot, **Then** current_tenure = 1 (not 2)

2. **Given** an employee hired 2023-03-15 and terminated 2026-09-20, **When** their record appears in fct_workforce_snapshot, **Then** current_tenure = 3 (floor of 3.52 years)

3. **Given** an employee hired 2025-06-01 and terminated 2025-11-30, **When** their record appears in fct_workforce_snapshot, **Then** current_tenure = 0 (less than 1 full year)

---

### Edge Cases

- **Employee hired on December 31**: Should not be selected for termination in that year (insufficient time), or if selected, termination_date equals hire_date (same-day termination)
- **Employee with NULL hire_date**: Should not be selected for termination (cannot calculate valid termination date)
- **Hash collision producing date before hire**: The hash-based date must be constrained/adjusted to be on or after hire_date
- **Terminated employee tenure calculation**: Must use termination_date as the end date, not December 31 of the simulation year

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST ensure termination effective_date >= employee_hire_date for all termination events
- **FR-002**: System MUST constrain hash-based termination date calculation to produce dates between hire_date and year_end (December 31)
- **FR-003**: System MUST exclude employees from termination selection if their hire_date would not allow a valid termination date within the simulation year
- **FR-004**: System MUST apply the same hire-before-termination constraint in both SQL (dbt) and Polars execution modes
- **FR-005**: System MUST include a data quality test that validates no termination_date < hire_date exists
- **FR-006**: System MUST maintain deterministic date generation while respecting the hire_date constraint
- **FR-007**: System MUST calculate terminated employee tenure using termination_date as the end date (not year-end December 31)
- **FR-008**: System MUST include a data quality test that validates terminated employees have tenure = floor((termination_date - hire_date) / 365.25)

### Key Entities

- **Termination Event**: Workforce event recording an employee's departure; effective_date must be >= employee's hire_date
- **Employee Hire Date**: The date an employee joined the organization; serves as the lower bound for any termination date
- **Simulation Year**: The calendar year being simulated; termination dates must fall within this year AND after hire_date

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero employees in fct_workforce_snapshot have termination_date < employee_hire_date
- **SC-002**: Zero termination events in fct_yearly_events have effective_date < the employee's hire_date
- **SC-003**: Data quality test for termination-after-hire passes with zero violations
- **SC-004**: Both SQL and Polars pipelines produce identical results for the hire/termination date ordering constraint
- **SC-005**: Tenure calculations for terminated employees produce non-negative values (tenure >= 0)
- **SC-006**: Tenure is calculated using the Anniversary Year Method (days from hire_date to termination_date / 365.25), ensuring each employee's tenure is measured from their individual hire date anniversary
- **SC-007**: For employee hired 2024-08-01 and terminated 2026-01-10, current_tenure = 1 (specific regression test)
- **SC-008**: Data quality test for tenure-at-termination accuracy passes with zero violations

## Clarifications

### Session 2026-01-21

- Q: Should tenure for terminated employees be calculated to termination date or year-end? → A: Termination date (user provided example: hire 2024-08-01, term 2026-01-10 should = 1 year, not 2)

## Assumptions

- The hash-based termination date generation can be modified to use hire_date as the lower bound instead of January 1
- Employees hired very late in the year (e.g., last few days) may have effectively zero termination probability for that year
- This fix applies to the generate_termination_date macro created in 021-fix-termination-events
- The `calculate_tenure` macro supports the Anniversary Year Method but requires the correct end date to be passed (termination_date for terminated employees, year-end for active employees)
- fct_workforce_snapshot may need modification to pass termination_date to tenure calculation for terminated employees
