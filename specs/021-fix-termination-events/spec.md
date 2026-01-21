# Feature Specification: Fix Termination Event Data Quality

**Feature Branch**: `021-fix-termination-events`
**Created**: 2026-01-21
**Status**: Draft
**Input**: User description: "the termination dates that are used are the same for every employee. i ran a model and the 2026 simulation terminated everyone on 2026-09-15. this is not reflective of the real world. also, why are some employees detailed_status_code set to new hire active but they were not a new hire in the simulation year? they have no hire date in that year. also new hire terminations do not have a termination date and have an employment status as active"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Realistic Termination Date Distribution (Priority: P1)

As a plan analyst running workforce simulations, I need termination events to occur throughout the year with realistic distribution so that my workforce projections accurately reflect when employees leave and their prorated compensation calculations are correct.

**Why this priority**: Uniform termination dates create unrealistic workforce snapshots and cause all prorated compensation calculations to use the same employment period, distorting financial projections. This is the most visible and impactful bug.

**Independent Test**: Run a single-year simulation and verify that termination dates are distributed across the year rather than clustered on a single date.

**Acceptance Scenarios**:

1. **Given** a simulation year with 100+ terminations, **When** the simulation completes, **Then** termination dates should be distributed across all 12 months with no single date having more than 5% of all terminations.

2. **Given** the same employee and simulation parameters across multiple runs, **When** simulations are executed, **Then** each employee's termination date should be reproducible (deterministic) while still being distributed across the year.

3. **Given** a multi-year simulation (2025-2027), **When** termination events are generated, **Then** each year should have its own independent termination date distribution without year-to-year date correlation.

---

### User Story 2 - Accurate New Hire Status Classification (Priority: P1)

As a plan analyst reviewing workforce snapshots, I need the detailed_status_code to accurately reflect whether an employee is a new hire so that I can correctly segment workforce metrics and identify data quality issues.

**Why this priority**: Incorrect status codes corrupt workforce analytics and make it impossible to trust segmentation by employee type. This affects all downstream reporting.

**Independent Test**: Query the workforce snapshot for employees marked as "new_hire_active" and verify each has a hire event in that simulation year.

**Acceptance Scenarios**:

1. **Given** an employee hired in a prior year, **When** the workforce snapshot is generated for a subsequent year, **Then** their detailed_status_code should be "continuous_active" (if still employed) or "experienced_termination" (if terminated), never "new_hire_active".

2. **Given** a new hire event in simulation year 2026, **When** the workforce snapshot is generated, **Then** only employees with a hire event in 2026 should have detailed_status_code containing "new_hire".

3. **Given** an employee from the baseline census (no hire event in simulation years), **When** the workforce snapshot is generated, **Then** their detailed_status_code should be "continuous_active" or "experienced_termination".

---

### User Story 3 - New Hire Termination Data Completeness (Priority: P1)

As a plan analyst tracking workforce turnover, I need new hire terminations to have complete data (termination date and terminated status) so that I can accurately measure first-year turnover and calculate prorated benefits.

**Why this priority**: Missing termination data for new hires means turnover metrics are wrong and prorated contribution calculations are incorrect. This is a data integrity issue that breaks audit trails.

**Independent Test**: Query for employees with termination events who have the new_hire_termination event category and verify they have termination_date populated and employment_status = 'terminated'.

**Acceptance Scenarios**:

1. **Given** a new hire who receives a termination event, **When** the workforce snapshot is generated, **Then** their employment_status should be "terminated" and termination_date should be populated.

2. **Given** a new hire termination event in fct_yearly_events, **When** the workforce snapshot is built, **Then** the termination_date in the snapshot should match the effective_date from the termination event.

3. **Given** a new hire termination event, **When** querying the workforce snapshot, **Then** the detailed_status_code should be "new_hire_termination" (not "new_hire_active").

---

### Edge Cases

- **Late-year hires**: Employees hired in December with insufficient time for in-year termination should not be selected for new hire termination.
- **Leap years**: Termination date distribution should handle 366-day years correctly.
- **Employees with multiple events**: An employee can have hire, raise, promotion, AND termination in the same year - all events should be properly sequenced.
- **Baseline employees without hire events**: Employees from the initial census have no hire event; they should never be classified as new hires in any simulation year.
- **Year boundary**: An employee hired on 2025-12-31 should be a "new hire" in 2025 but "continuous_active" (or "experienced_termination") in 2026.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST generate termination dates that are distributed across all months of the simulation year, with no single calendar month containing more than 20% of terminations.

- **FR-002**: System MUST ensure termination dates are deterministic (reproducible with the same random seed) while achieving realistic distribution.

- **FR-003**: System MUST classify an employee as "new_hire_active" or "new_hire_termination" only if there is a hire event for that employee in the current simulation year.

- **FR-004**: System MUST classify employees from the baseline census (no hire event in simulation years) as "continuous_active" or "experienced_termination" based solely on their employment status.

- **FR-005**: System MUST populate the termination_date field for all employees who have a termination event, including new hire terminations.

- **FR-006**: System MUST set employment_status to "terminated" for all employees who have a termination event, including new hire terminations.

- **FR-007**: System MUST ensure the detailed_status_code "new_hire_termination" is applied only when both a hire event AND a termination event exist for the employee in the same simulation year.

- **FR-008**: System MUST maintain determinism: identical simulation parameters (seed, year, scenario) must produce identical termination dates and status codes.

### Key Entities

- **Termination Event**: Represents an employee's departure with effective_date, termination_reason, and employee metadata. Must have a date distributed throughout the year.
- **Workforce Snapshot**: Year-end point-in-time view of all employees with employment_status, termination_date, and detailed_status_code accurately reflecting their state.
- **Employee Events Consolidated**: Aggregated view of all events for an employee in a year, used to determine hire status and termination status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Termination date distribution passes chi-squared test for uniform distribution across months (p-value > 0.05) for simulations with 100+ terminations.

- **SC-002**: Zero employees in workforce snapshot have detailed_status_code = "new_hire_active" without a corresponding hire event in that simulation year.

- **SC-003**: 100% of employees with termination events have a non-null termination_date and employment_status = "terminated" in the workforce snapshot.

- **SC-004**: Zero employees have detailed_status_code = "new_hire_termination" while employment_status = "active".

- **SC-005**: Simulation with the same random seed produces identical termination dates across multiple runs (100% reproducibility).

- **SC-006**: Multi-year simulations (2025-2027) show independent termination date distributions per year with no cross-year date correlation.

## Assumptions

- The current hash-based approach for determinism is acceptable; we will modify the hash function inputs to achieve better distribution.
- Existing termination rate logic (expected_experienced_terminations, new_hire_termination_rate) is correct; only the date assignment needs fixing.
- The baseline census represents employees hired prior to all simulation years and should never be classified as new hires.
- Month-level distribution (within 20% per month) is sufficient; day-level uniformity is not required.
