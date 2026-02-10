# Feature Specification: Fix Census Compensation Annualization Logic

**Feature Branch**: `043-fix-annualization-logic`
**Created**: 2026-02-10
**Status**: Draft
**Input**: User description: "Fix annualization logic in stg_census_data.sql and remove HOTFIX from int_baseline_workforce.sql"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Correct Annualization in Staging Model (Priority: P1)

As a simulation analyst, when census data is loaded and staged, I need the `employee_annualized_compensation` field to represent the true full-year salary rate for every employee, regardless of their hire or termination timing within the plan year. Currently, `stg_census_data.sql` bypasses annualization by setting `employee_annualized_compensation` equal to raw `employee_gross_compensation` with a comment stating "no annualization needed." If the census gross compensation for partial-year employees actually represents prorated earnings rather than an annual rate, this passthrough produces incorrect downstream results.

**Why this priority**: The annualized compensation field is the foundation for all downstream compensation logic (baseline workforce, merit raises, contribution limits, HCE determination). An incorrect value here cascades through the entire simulation.

**Independent Test**: Load census data with known full-year and partial-year employees. Verify that `employee_annualized_compensation` correctly represents the full-year salary rate for all employees, and that `employee_plan_year_compensation` correctly reflects the prorated amount for the active portion of the plan year.

**Acceptance Scenarios**:

1. **Given** a full-year employee (hired 2020-03-15, no termination) with gross compensation of $100,000, **When** the staging model runs for plan year 2024, **Then** `employee_annualized_compensation` equals $100,000 and `employee_plan_year_compensation` equals $100,000.
2. **Given** a mid-year hire (hired 2024-07-01, no termination) with gross compensation of $50,000, **When** the staging model runs for plan year 2024, **Then** the annualization logic correctly distinguishes between the annual rate and the plan-year earnings based on the data contract definition of `employee_gross_compensation`.
3. **Given** a mid-year termination (hired 2020-01-01, terminated 2024-06-30) with gross compensation of $100,000, **When** the staging model runs, **Then** `employee_annualized_compensation` reflects the full-year salary rate and `employee_plan_year_compensation` reflects approximately half-year earnings.

---

### User Story 2 - Remove HOTFIX from Baseline Workforce Model (Priority: P1)

As a developer maintaining the simulation codebase, I need the compensation bypass pattern in `int_baseline_workforce.sql` removed so that the baseline model uses the properly corrected `employee_annualized_compensation` field from staging. The current pattern -- where the baseline model uses a staging field that simply passes through raw gross compensation -- constitutes tech debt that obscures the intent of the compensation pipeline and risks divergent logic as the codebase evolves.

**Why this priority**: A single source of truth for compensation annualization eliminates maintenance risk and makes the compensation flow traceable from census through simulation.

**Independent Test**: Run a single-year simulation and verify that `current_compensation` in `int_baseline_workforce` matches `employee_annualized_compensation` from `stg_census_data`, with no HOTFIX or bypass comments remaining in the code.

**Acceptance Scenarios**:

1. **Given** the corrected staging model, **When** `int_baseline_workforce` is rebuilt, **Then** `current_compensation` uses `employee_annualized_compensation` from staging and all HOTFIX-related comments are removed.
2. **Given** the updated baseline model, **When** a full simulation runs for 2025, **Then** downstream models produce results consistent with pre-fix behavior for full-year employees (no regression).

---

### User Story 3 - Validate Annualization with Automated Tests (Priority: P2)

As a data quality engineer, I need automated tests that verify annualization correctness for typical and edge-case census records, so that future changes to the staging or baseline models cannot silently reintroduce compensation bugs.

**Why this priority**: Tests provide a safety net against regression. Without them, compensation bugs could propagate undetected through multiple simulation cycles before being discovered.

**Independent Test**: Run the test suite against the staging and baseline models and verify all annualization-related tests pass for full-year employees, partial-year employees, and edge cases.

**Acceptance Scenarios**:

1. **Given** a test for full-year employee annualization, **When** the test suite runs, **Then** it confirms annualized compensation equals the expected full-year rate.
2. **Given** a test for partial-year employee annualization, **When** the test suite runs, **Then** it confirms the relationship between annualized and plan-year compensation is mathematically correct.
3. **Given** a test for edge cases (zero days active, NULL hire date, zero gross compensation), **When** the test suite runs, **Then** all edge-case tests pass without errors.

---

### Edge Cases

- What happens when an employee has exactly 1 day of activity in the plan year (hired December 31)? Annualization should produce a valid result without extreme distortion.
- How does the system handle employees with zero or NULL `employee_gross_compensation`? The annualization logic should handle these gracefully without division errors or incorrect results.
- What happens when `employee_hire_date` is NULL? The staging model should handle missing dates without failing.
- How are employees with termination dates before the plan year start handled? They should have zero days active and retain their gross compensation as the annualized value.
- What happens for employees hired after the plan year end? They should have zero days active within the plan year.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The staging model MUST compute `employee_annualized_compensation` as the true full-year equivalent salary rate, correctly derived from `employee_gross_compensation` and the data contract definition of that field.
- **FR-002**: The staging model MUST compute `employee_plan_year_compensation` as the actual compensation attributable to the active portion of the plan year (pro-rated by days active for partial-year employees).
- **FR-003**: The staging model MUST handle edge cases where `days_active_in_year` is zero by producing a valid `employee_annualized_compensation` without division-by-zero errors.
- **FR-004**: The staging model MUST handle NULL values in `employee_gross_compensation` and `employee_hire_date` gracefully, producing NULL or zero compensation as appropriate rather than failing.
- **FR-005**: The baseline workforce model MUST use `employee_annualized_compensation` from the staging model as its `current_compensation` field without any bypass or workaround logic.
- **FR-006**: The baseline workforce model MUST NOT contain any HOTFIX, bypass, or TODO comments related to annualization after the fix is applied.
- **FR-007**: Automated tests MUST validate annualization correctness for full-year employees, partial-year employees (mid-year hires and mid-year terminations), and edge cases (zero days active, NULL values, boundary dates).
- **FR-008**: Downstream models that depend on `current_compensation` from the baseline workforce MUST produce results consistent with their current behavior for full-year employees (no regression in compensation calculations, contribution limits, or HCE determinations).

### Key Entities

- **Census Employee Record**: Raw employee data from parquet, containing `employee_gross_compensation` (defined per data contract), `employee_hire_date`, and `employee_termination_date`.
- **Staged Census Record**: Cleaned and enriched output of `stg_census_data`, including `employee_annualized_compensation` (full-year equivalent rate) and `employee_plan_year_compensation` (pro-rated actual earnings for the plan year).
- **Baseline Workforce Record**: Simulation-ready employee record from `int_baseline_workforce`, where `current_compensation` is the primary salary field consumed by all downstream event generation models (termination, promotion, merit, enrollment, contributions).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For all full-year employees (hired before plan year start, no termination in plan year), annualized compensation equals gross compensation with zero variance.
- **SC-002**: For partial-year employees, the relationship between annualized compensation, plan-year compensation, and days active is mathematically consistent within rounding tolerance.
- **SC-003**: All HOTFIX, bypass, and TODO comments related to annualization are removed from the affected files (zero occurrences).
- **SC-004**: All existing tests continue to pass after the fix (zero test regressions).
- **SC-005**: New annualization-specific tests achieve 100% pass rate covering full-year, partial-year, and edge-case scenarios.
- **SC-006**: Downstream compensation models (workforce snapshot, compensation growth, employee contributions) produce results within expected tolerance compared to pre-fix output for a standard simulation run with full-year employees.

## Assumptions

- The source column `employee_gross_compensation` in the parquet census file represents an **annual salary rate** (not actual partial-year earnings), consistent with the existing data contract comment in `stg_census_data.sql` (line 80: "defined as an annual rate per the data contract").
- Plan year boundaries default to January 1 through December 31 and are configurable via `plan_year_start_date` and `plan_year_end_date` dbt variables.
- The `employee_annualized_compensation` field currently appears in 3 files: `stg_census_data.sql`, `int_baseline_workforce.sql`, and the staging schema. The fix scope is limited to these files plus new tests.
- The 52 downstream models that reference `current_compensation` will not require changes, as the corrected annualized value should match the current passthrough value for the majority case (full-year employees where gross compensation already equals the annual rate).

## Dependencies

- No external dependencies. This is a self-contained fix within the dbt staging and intermediate layers.
- Requires the existing census parquet data contract to be accurate (gross compensation = annual rate).

## Risks

- If any census data sources provide `employee_gross_compensation` as prorated partial-year earnings rather than an annual rate, the current passthrough behavior may actually be incorrect in a way that this fix needs to address. The data contract assumption must be validated before implementation.
- With 52 downstream models referencing `current_compensation`, any change to the annualized value for partial-year employees could cascade. Regression testing must cover downstream outputs, not just the staging model.
