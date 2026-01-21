# Feature Specification: Fix Mid-Year Termination Tenure Calculation

**Feature Branch**: `023-fix-midyear-tenure`
**Created**: 2026-01-21
**Status**: Draft
**Input**: User description: "the current_tenure in the workforce snapshot is WILDLY wrong for mid year terminations. i don't know if it is the polars event factory or the snapshot code, but you need to fix it."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accurate Tenure for Mid-Year Terminated Employees (Priority: P1)

As a workforce analyst, I need employees who are terminated mid-year to show their correct tenure (calculated from hire date to termination date) in the workforce snapshot, so that plan cost projections and eligibility calculations are accurate.

**Why this priority**: Incorrect tenure values cascade into retirement plan eligibility, vesting calculations, and employer match/core contribution calculations. This is a data integrity bug affecting financial accuracy.

**Independent Test**: Query `fct_workforce_snapshot` for terminated employees and verify their `current_tenure` matches the expected value calculated as `floor((termination_date - hire_date) / 365.25)`.

**Acceptance Scenarios**:

1. **Given** an existing employee hired on 2020-06-15 with termination on 2026-06-30, **When** the 2026 simulation runs, **Then** their `current_tenure` should be 6 years (not 7 from the +1 increment).

2. **Given** a new hire (NH_2026_001) hired on 2026-03-01 with termination on 2026-09-15, **When** the 2026 simulation runs, **Then** their `current_tenure` should be 0 years (6.5 months of service).

3. **Given** an employee terminated on 2026-01-15 (hired 2020-01-01), **When** the 2026 simulation runs, **Then** their `current_tenure` should be 6 years (calculated to termination date, not year-end).

---

### User Story 2 - Tenure Consistency Between SQL and Polars Modes (Priority: P2)

As a developer, I need both the SQL (dbt) pipeline and the Polars state pipeline to produce identical tenure values for terminated employees, so that mode selection doesn't affect data quality.

**Why this priority**: The system supports two execution modes (SQL via dbt and Polars for performance). Inconsistent tenure calculations would cause non-deterministic results.

**Independent Test**: Run the same simulation in both SQL and Polars modes and compare `current_tenure` values for all terminated employees.

**Acceptance Scenarios**:

1. **Given** a 2-year simulation (2025-2026) run in SQL mode, **When** the same simulation runs in Polars mode, **Then** all terminated employees have identical `current_tenure` values in both outputs.

2. **Given** any terminated employee in year N, **When** comparing SQL vs Polars output, **Then** the tenure values differ by at most 0 (exact match expected).

---

### Edge Cases

- What happens when an employee is hired and terminated on the same day? (Expected: 0 years tenure)
- What happens when termination_date is NULL for a terminated employee? (Expected: Use year-end date as fallback or flag as data quality issue)
- What happens when hire_date is after termination_date (data error)? (Expected: Return 0 years, flag as data quality issue)
- What happens for employees terminated on December 31st? (Expected: Full year calculation, same as active employee)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calculate terminated employee tenure as `floor((termination_date - hire_date) / 365.25)` years.
- **FR-002**: System MUST NOT apply the Year-over-Year +1 tenure increment to employees who are terminated mid-year before recalculating tenure.
- **FR-003**: System MUST calculate new hire tenure to termination date when the new hire is terminated in their first year (not hardcode 0).
- **FR-004**: SQL (dbt) pipeline and Polars state pipeline MUST produce identical tenure values for the same input data.
- **FR-005**: System MUST use the `calculate_tenure` macro consistently for all tenure calculations in SQL models.
- **FR-006**: System MUST return tenure of 0 when hire_date is NULL or when hire_date > termination_date.
- **FR-007**: System MUST recalculate tenure_band based on the corrected current_tenure value to ensure consistency between raw tenure and its categorical band.

### Key Entities

- **Workforce Snapshot** (`fct_workforce_snapshot`): Contains `current_tenure` field that must be corrected for mid-year terminations.
- **Termination Events** (`fct_yearly_events` with event_type='TERMINATION'): Contains `termination_date` used for tenure calculation.
- **Employee Base** (`int_active_employees_prev_year_snapshot`, `int_baseline_workforce`): Sources of initial tenure values that may have incorrect +1 increment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of terminated employees in the workforce snapshot have tenure values that match the formula `floor((termination_date - hire_date) / 365.25)`.
- **SC-002**: Zero variance in `current_tenure` values between SQL and Polars execution modes for the same simulation.
- **SC-003**: All existing tenure-related tests pass after the fix.
- **SC-004**: New regression tests specifically for mid-year termination tenure are added and pass.
- **SC-005**: 100% of employees have tenure_band values consistent with their current_tenure value (e.g., tenure=0 → band="< 2", tenure=6 → band="5-9").

## Assumptions

- The `termination_date` field is correctly populated for all terminated employees (populated from termination events).
- The `employee_hire_date` field is correctly populated for all employees.
- The existing `calculate_tenure` macro in dbt is correctly implemented and should be reused.
- Both SQL and Polars pipelines should converge to the same tenure calculation logic.

## Out of Scope

- Changes to how tenure is used in eligibility or vesting calculations (those are downstream consumers).
- Performance optimization of tenure calculations.

## Clarifications

### Session 2026-01-21

- Q: Should tenure band recalculation be included in scope (currently excluded)? → A: Yes, include tenure band recalculation - tenure_band must be derived from the corrected current_tenure value.
