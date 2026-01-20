# Feature Specification: Fix Current Tenure Calculation

**Feature Branch**: `020-fix-tenure-calculation`
**Created**: 2026-01-20
**Status**: Draft
**Input**: User description: "Audit and fix current_tenure calculation to use end of plan year (12/31 of simulation year) minus hire date, truncated not rounded"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accurate Tenure Calculation for All Employees (Priority: P1)

As a plan administrator, I need employee tenure to be calculated accurately as of December 31st of each simulation year so that tenure-based benefits (vesting, service-based contributions) are applied correctly.

**Why this priority**: Tenure directly impacts financial calculations including vesting schedules, service-based core contributions, and tenure band assignments. Incorrect tenure leads to incorrect cost projections.

**Independent Test**: Run a simulation for a single employee with a known hire date and verify their tenure matches the expected value (days from hire date to 12/31 of simulation year, divided by 365.25, truncated to integer).

**Acceptance Scenarios**:

1. **Given** an employee hired on 2020-06-15, **When** running simulation year 2025, **Then** tenure should be calculated as floor((2025-12-31 minus 2020-06-15) / 365.25) = 5 years
2. **Given** an employee hired on 2025-07-01, **When** running simulation year 2025, **Then** tenure should be floor((2025-12-31 minus 2025-07-01) / 365.25) = 0 years
3. **Given** an employee hired on 2021-01-01, **When** running simulation year 2025, **Then** tenure should be floor((2025-12-31 minus 2021-01-01) / 365.25) = 4 years (not 5)

---

### User Story 2 - Consistent Tenure Across SQL and Polars Pipelines (Priority: P1)

As a developer, I need both the SQL (dbt) and Polars pipelines to use the same tenure calculation formula so that results are consistent regardless of which execution mode is used.

**Why this priority**: The system supports two execution modes. Inconsistent calculations between modes would produce different results for the same inputs, undermining trust in the simulation.

**Independent Test**: Run the same scenario through both SQL and Polars modes and compare the tenure values for all employees - they must be identical.

**Acceptance Scenarios**:

1. **Given** the same census data and simulation year, **When** running in SQL mode vs Polars mode, **Then** all employees have identical tenure values
2. **Given** an employee's tenure calculated in Year N, **When** advancing to Year N+1, **Then** tenure increments by exactly 1 year in both modes

---

### User Story 3 - Tenure Band Assignment Uses Corrected Tenure (Priority: P2)

As a plan administrator, I need tenure bands to be assigned based on the corrected tenure calculation so that employees fall into the correct service tiers for benefits.

**Why this priority**: Tenure bands drive service-based contribution rates and other benefits. Using incorrect tenure would misclassify employees.

**Independent Test**: Verify an employee with calculated tenure of 4.9 years (truncated to 4) is assigned to the "2-4" band, not the "5-9" band.

**Acceptance Scenarios**:

1. **Given** an employee with calculated tenure of 1.9 years (truncated to 1), **When** assigning tenure band, **Then** employee is in "< 2" band
2. **Given** an employee with calculated tenure of 4.99 years (truncated to 4), **When** assigning tenure band, **Then** employee is in "2-4" band (not "5-9")

---

### Edge Cases

- What happens when hire date is after the simulation year end date (12/31)? Tenure should be 0.
- What happens when hire date is exactly 12/31 of the simulation year? Tenure should be 0.
- What happens when hire date is missing or null? System should handle gracefully with a default of 0 and log a warning.
- How does leap year handling work? Using 365.25 as divisor accounts for leap years.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calculate current_tenure as: `floor((simulation_year_end_date - hire_date) / 365.25)` where simulation_year_end_date is December 31st of the simulation year
- **FR-002**: System MUST use integer truncation (floor), not rounding, for the final tenure value
- **FR-003**: System MUST return 0 for tenure when hire_date is on or after simulation_year_end_date
- **FR-004**: System MUST use the same calculation formula in both SQL (dbt) and Polars execution modes
- **FR-005**: System MUST increment tenure by exactly 1 when advancing from simulation year N to year N+1 (after initial calculation)
- **FR-006**: System MUST handle null/missing hire dates by using a default tenure of 0 and logging a warning
- **FR-007**: System MUST recalculate tenure for new hires in the simulation year using their actual hire date (not increment from prior year)

### Key Entities

- **Employee**: Has hire_date (date), termination_date (date, nullable), current_tenure (integer years)
- **Simulation Year**: Defines the plan year end date (12/31/YYYY) used as reference for tenure calculation
- **Tenure Band**: Classification based on tenure value using [min, max) intervals

### Tenure Calculation Rules

- **Active employees**: Tenure calculated to December 31 of simulation year
- **Terminated employees**: Tenure calculated to termination date (not year end)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All employees in test scenarios have tenure values matching the expected formula: `floor((12/31/simulation_year - hire_date) / 365.25)`
- **SC-002**: SQL mode and Polars mode produce identical tenure values for the same input data (100% match)
- **SC-003**: Tenure band assignments are consistent with the [min, max) interval convention defined in config_tenure_bands.csv
- **SC-004**: No employees have negative tenure values in any simulation output
- **SC-005**: Multi-year simulations show tenure incrementing by exactly 1 year per simulation year for continuing employees

## Assumptions

- The plan year always ends on December 31st (calendar year plan)
- Using 365.25 as the divisor is acceptable for accounting for leap years
- Tenure is always expressed as whole years (integers), not fractional
- The truncation behavior (floor) is intentional and required for benefit calculations
- Existing tests may need updates to reflect the corrected calculation
