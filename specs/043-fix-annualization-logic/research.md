# Research: Fix Census Compensation Annualization Logic

**Feature Branch**: `043-fix-annualization-logic`
**Date**: 2026-02-10

## R1: Data Contract for `employee_gross_compensation`

**Decision**: `employee_gross_compensation` represents an **annual salary rate**, not prorated partial-year earnings.

**Rationale**: The `stg_census_data.sql` comment at line 80 states: "The source column `employee_gross_compensation` is defined as an annual rate per the data contract." The existing schema test in `schema.yml` enforces `employee_annualized_compensation = employee_gross_compensation`, confirming this is the intended behavior.

**Alternatives considered**:
- Treating gross comp as plan-year prorated earnings and annualizing via `gross * (365 / days_active)` — rejected because the data contract explicitly defines it as an annual rate, and annualizing prorated values for 1-day employees would produce extreme distortion.

## R2: Nature of the HOTFIX

**Decision**: The "HOTFIX" is not a code workaround but a clarity/tech-debt issue. `stg_census_data.sql` line 116 sets `employee_annualized_compensation = employee_gross_compensation` (a passthrough), and `int_baseline_workforce.sql` line 25 uses this passthrough. The misleading naming and comments suggest annualization logic exists when it doesn't.

**Rationale**: Code inspection reveals:
- `computed_plan_year_compensation` (line 113) correctly prorates: `gross * (days_active / 365.0)`
- `employee_annualized_compensation` (line 116) is just `employee_gross_compensation` — a no-op passthrough
- The comment "Gross compensation is already an annual rate; no annualization needed" is correct but creates confusion about intent
- No actual "HOTFIX" comment exists in `int_baseline_workforce.sql` — the tech debt is the misleading field naming and the dead annualization logic pattern

**Alternatives considered**:
- Implementing true annualization (gross-up from plan-year to annual rate) — rejected because gross comp is already an annual rate per the data contract.

## R3: Downstream Impact Assessment

**Decision**: Changes are safe for full-year employees (majority case) but must be validated for partial-year employees across 52 downstream models.

**Rationale**: The downstream compensation chain flows through:
1. `int_employee_compensation_by_year` — authoritative source, reads `current_compensation` from baseline
2. `int_merit_events` — applies merit % to `employee_gross_compensation` (SENSITIVE)
3. `int_employee_contributions` — proration ratio uses `current_compensation` as denominator (CRITICAL)
4. `fct_workforce_snapshot` — carries state to Year N+1, creating compounding effect (CRITICAL)

Since `employee_annualized_compensation` already equals `employee_gross_compensation`, the fix is functionally a no-op for values. The risk is limited to ensuring no accidental value changes during refactoring.

## R4: Existing Test Coverage Gaps

**Decision**: Add new singular SQL tests in `dbt/tests/data_quality/` following the project's severity-classified pattern.

**Rationale**: Current coverage gaps:
- No test for `days_active_in_year` calculation correctness
- No test for boundary conditions (hire on 12/31, terminate on 1/1)
- No test for NULL handling in compensation/date fields
- No cross-model consistency test (staging → baseline → snapshot)
- Existing schema test `employee_annualized_compensation = employee_gross_compensation` validates the passthrough but not the proration math

**Alternatives considered**:
- Python-based pytest tests — rejected because all existing compensation tests use dbt singular SQL tests, and the validation runs against materialized tables.
- dbt generic tests only — rejected because severity-classified singular tests provide richer diagnostics.

## R5: Test Framework Pattern

**Decision**: Use singular SQL tests in `dbt/tests/data_quality/` with CRITICAL/ERROR/WARNING severity classification.

**Rationale**: Project conventions:
- Tests return 0 rows on PASS, >0 rows on FAIL
- Failures stored in `test_failures` schema via `+store_failures: true`
- Severity set to `warn` (non-blocking) with internal severity classification
- Year-aware filtering via `{{ var('simulation_year') }}`
- Output columns: `simulation_year`, `validation_rule`, `severity`, `employee_id`, `validation_message`

## R6: Leap Year Handling

**Decision**: The existing 365-day divisor is acceptable. The schema test allows up to `gross * (366.0 / 365.0)` for plan-year compensation, accommodating leap years.

**Rationale**: For plan-year proration, `days_active / 365.0` produces slightly over 1.0 for leap year full-year employees (366/365 ≈ 1.0027), which the schema test permits. This is an acceptable approximation for workforce simulation purposes.

**Alternatives considered**:
- Using actual days in plan year (`DATE_DIFF('day', plan_start, plan_end) + 1`) as divisor — viable but adds complexity for negligible accuracy improvement (<0.3%).
