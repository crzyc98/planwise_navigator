# Feature Specification: Fix Census Compensation Annualization Logic

**Feature Branch**: `037-fix-annualization-logic`
**Created**: 2026-02-07
**Status**: Draft
**Input**: User description: "Fix annualization logic in stg_census_data.sql and remove HOTFIX from int_baseline_workforce.sql"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Correct Annualized Compensation for Full-Year Employees (Priority: P1)

As a simulation analyst, when I load census data for employees who were active for the full plan year, I need their annualized compensation to equal their gross compensation so that downstream models (baseline workforce, compensation growth, workforce snapshots) use accurate annual salary figures.

**Why this priority**: Full-year employees are the vast majority of the census population. Incorrect annualization here would cascade through all compensation-dependent models and produce systematically wrong results.

**Independent Test**: Load a census file with employees who were hired before the plan year start and have no termination date. Verify that `employee_annualized_compensation` equals `employee_gross_compensation` for each.

**Acceptance Scenarios**:

1. **Given** a census employee hired on 2020-03-15 with no termination date and gross compensation of $100,000, **When** the staging model runs for plan year 2024, **Then** `employee_annualized_compensation` equals $100,000.
2. **Given** a census employee hired on 2024-01-01 (plan year start) with no termination date and gross compensation of $80,000, **When** the staging model runs, **Then** `employee_annualized_compensation` equals $80,000.

---

### User Story 2 - Correct Annualized Compensation for Partial-Year Employees (Priority: P1)

As a simulation analyst, when I load census data for employees who were only active for part of the plan year (mid-year hires or mid-year terminations), I need their annualized compensation to correctly represent the full-year equivalent salary rate, so that compensation comparisons and projections are accurate.

**Why this priority**: Partial-year employees' compensation must be annualized to enable apples-to-apples comparisons and correct downstream calculations for merit raises, contribution limits, and HCE determination.

**Independent Test**: Load a census file with a mid-year hire (e.g., hired July 1). Verify that `employee_annualized_compensation` reflects the full-year equivalent salary rate, not the pro-rated partial-year amount.

**Acceptance Scenarios**:

1. **Given** a census employee hired on 2024-07-01 with no termination date and gross compensation of $100,000 (representing their annual salary rate), **When** the staging model runs for plan year 2024, **Then** `employee_annualized_compensation` equals $100,000 (the annual rate is already the annualized value).
2. **Given** a census employee hired on 2024-01-01 and terminated on 2024-06-30 with gross compensation of $100,000 (annual rate), **When** the staging model runs, **Then** `employee_annualized_compensation` equals $100,000 and `employee_plan_year_compensation` reflects the pro-rated amount (~$49,589).
3. **Given** a census employee with no overlap with the plan year (hired after plan year end), **When** the staging model runs, **Then** `employee_annualized_compensation` retains the gross compensation value as a fallback.

---

### User Story 3 - Remove HOTFIX and Use Corrected Annualized Field (Priority: P1)

As a developer maintaining the simulation codebase, I need the HOTFIX workaround in `int_baseline_workforce.sql` removed so that the baseline workforce model uses the properly corrected `employee_annualized_compensation` from staging, eliminating tech debt and ensuring a single source of truth for compensation logic.

**Why this priority**: The HOTFIX bypasses the staging model's annualization output and introduces a parallel compensation path. This tech debt risks divergent logic as the codebase evolves and makes the intent of the compensation pipeline unclear.

**Independent Test**: Run the full simulation for a single year and verify that `current_compensation` in `int_baseline_workforce` matches `employee_annualized_compensation` from `stg_census_data`.

**Acceptance Scenarios**:

1. **Given** the updated `stg_census_data` with corrected annualization, **When** `int_baseline_workforce` is rebuilt, **Then** the HOTFIX comment and TODO are no longer present in the SQL.
2. **Given** the updated baseline model, **When** a full simulation runs for year 2025, **Then** all downstream compensation models produce results consistent with pre-fix behavior for full-year employees (no regression).

---

### User Story 4 - Validate Annualization with Automated Tests (Priority: P2)

As a data quality engineer, I need automated tests that verify annualization correctness for typical and edge-case census records, so that future changes to the staging model cannot silently reintroduce the bug.

**Why this priority**: Tests provide a safety net against regression. Without them, compensation bugs could go undetected through multiple simulation cycles.

**Independent Test**: Run the test suite against the staging and baseline models and verify all annualization-related tests pass.

**Acceptance Scenarios**:

1. **Given** a test for annualization correctness, **When** the test suite runs against a census with full-year employees, **Then** the test passes confirming annualized compensation equals gross compensation.
2. **Given** a test for partial-year annualization, **When** the test suite runs against a census with mid-year hires, **Then** the test passes confirming the gross-up calculation is correct.
3. **Given** a test for edge cases (zero days active, hire date after plan year end), **When** the test suite runs, **Then** all edge-case tests pass.

---

### Edge Cases

- What happens when an employee has exactly 1 day of activity in the plan year? The annualization should still produce a valid full-year equivalent without extreme distortion.
- How does the system handle employees hired on the last day of the plan year (December 31)? They should have 1 day active and their annualized compensation should equal their gross compensation (since gross represents an annual rate).
- What happens when `employee_gross_compensation` is zero or NULL? The annualization should handle these gracefully without division errors.
- What happens when `employee_hire_date` is NULL? The staging model should handle missing dates without failing.
- How are employees with termination dates before the plan year start handled? They should have zero days active and retain their gross compensation as the annualized value.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The staging model MUST compute `employee_annualized_compensation` as the full-year equivalent salary rate. Since `employee_gross_compensation` already represents an annual rate per the data contract, `employee_annualized_compensation` should equal `employee_gross_compensation` for all employees (regardless of partial-year status).
- **FR-002**: The staging model MUST compute `employee_plan_year_compensation` as the actual compensation attributable to the active portion of the plan year (pro-rated by days active for partial-year employees).
- **FR-003**: The staging model MUST handle edge cases where `days_active_in_year` is zero by retaining `employee_gross_compensation` as the annualized compensation (no division by zero).
- **FR-004**: The baseline workforce model MUST use `employee_annualized_compensation` from the staging model as its `current_compensation` field, replacing the current HOTFIX that uses `employee_gross_compensation` directly.
- **FR-005**: The baseline workforce model MUST NOT contain any HOTFIX comments or TODO markers related to annualization after the fix is applied.
- **FR-006**: Automated tests MUST validate that annualized compensation is correct for full-year employees, partial-year employees, and edge cases (zero days active, NULL values).
- **FR-007**: Downstream models that depend on `current_compensation` from the baseline workforce MUST produce results consistent with their current behavior for full-year employees (no regression).

### Key Entities

- **Census Employee Record**: The raw employee data loaded from parquet files, containing `employee_gross_compensation` (annual salary rate), `employee_hire_date`, and `employee_termination_date`.
- **Staged Census Record**: The cleaned and enriched output of `stg_census_data`, including `employee_annualized_compensation` (full-year equivalent rate) and `employee_plan_year_compensation` (pro-rated actual earnings).
- **Baseline Workforce Record**: The simulation-ready employee record from `int_baseline_workforce`, where `current_compensation` is the primary salary field used by all downstream event generation models.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For all full-year employees (hired before plan year start, no termination in plan year), annualized compensation equals gross compensation with zero variance.
- **SC-002**: For partial-year employees, the relationship `plan_year_compensation = annualized_compensation * days_active / 365` holds true (within rounding tolerance).
- **SC-003**: All HOTFIX and TODO comments related to annualization are removed from the codebase (zero occurrences in the affected files).
- **SC-004**: All existing tests continue to pass after the fix (zero regressions in the test suite).
- **SC-005**: New annualization-specific tests achieve 100% pass rate covering full-year, partial-year, and edge-case scenarios.
- **SC-006**: Downstream compensation models (workforce snapshot, compensation growth) produce results within expected tolerance for a standard simulation run.

## Assumptions

- The source column `employee_gross_compensation` in the parquet census file represents an **annual salary rate** (not actual partial-year earnings). This is consistent with the existing contract comment in `stg_census_data.sql` (line 80: "defined as an annual amount").
- The current annualization formula (lines 117-120) is algebraically a no-op for non-zero cases: `(gross * days/365) * 365/days = gross`. The HOTFIX was needed because the formula, while mathematically equivalent, was confusing and the intermediate `computed_plan_year_compensation` was incorrectly being used in some contexts.
- Plan year boundaries default to January 1 through December 31 and are configurable via `plan_year_start_date` and `plan_year_end_date` variables.
- The `annualize_partial_year_compensation` variable mentioned in a code comment was never implemented as an actual conditional toggle. Since gross compensation already represents an annual rate, this toggle is unnecessary and will not be implemented.
