# Feature Specification: Fix Tenure Eligibility Enforcement for Employer Contributions

**Feature Branch**: `047-fix-tenure-eligibility`
**Created**: 2026-02-11
**Status**: Draft
**Input**: Bug report: Employees with tenure < configured minimum still receive employer match and core contributions

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tenure-Based Eligibility Correctly Excludes Ineligible Employees (Priority: P1)

A plan administrator configures a 2-year minimum tenure requirement for both employer match and employer core contributions via PlanAlign Studio. After running a simulation, the administrator expects that employees with fewer than 2 years of service receive $0 in employer match and $0 in employer core contributions in the workforce snapshot output.

**Why this priority**: This is the core bug. Without this fix, the simulation produces financially incorrect results that misstate employer contribution liabilities, defeating the purpose of the eligibility configuration.

**Independent Test**: Can be fully tested by configuring `minimum_tenure_years: 2` for both match and core, running a single-year simulation, and verifying that employees with `current_tenure < 2` have $0 employer match and $0 employer core contributions in `fct_workforce_snapshot`.

**Acceptance Scenarios**:

1. **Given** employer match eligibility is configured with `minimum_tenure_years: 2` and `allow_new_hires: false`, **When** a simulation is run for year 2025, **Then** employees with `current_tenure < 2` have `eligible_for_match = FALSE` in `int_employer_eligibility` and $0 employer match in `fct_workforce_snapshot`.
2. **Given** employer core eligibility is configured with `minimum_tenure_years: 2` and `allow_new_hires: false`, **When** a simulation is run for year 2025, **Then** employees with `current_tenure < 2` have `eligible_for_core = FALSE` in `int_employer_eligibility` and $0 employer core contributions in `fct_workforce_snapshot`.
3. **Given** both match and core eligibility require 2-year minimum tenure with `allow_new_hires: false`, **When** an employee has exactly 2.0 years of tenure, **Then** that employee IS eligible for both match and core contributions (boundary: `>=` check).

---

### User Story 2 - `allow_new_hires` Defaults to `false` When Tenure Requirement Is Non-Zero (Priority: P1)

When a plan administrator sets `minimum_tenure_years` to a value greater than 0 but does not explicitly configure `allow_new_hires`, the system should default `allow_new_hires` to `false` to prevent contradictory behavior where a tenure requirement is set but immediately bypassed for new hires.

**Why this priority**: This is the root cause of the bug for tenure-0 employees. The current default of `allow_new_hires: true` silently overrides any configured tenure requirement for all new hires, producing counterintuitive results.

**Independent Test**: Can be tested by configuring `minimum_tenure_years: 2` without setting `allow_new_hires`, running a simulation, and verifying new hires (tenure 0) are excluded from contributions.

**Acceptance Scenarios**:

1. **Given** `minimum_tenure_years: 2` is configured for match and `allow_new_hires` is NOT explicitly set, **When** the dbt model resolves the `allow_new_hires` default, **Then** it defaults to `false` (since tenure requirement > 0).
2. **Given** `minimum_tenure_years: 0` is configured for match and `allow_new_hires` is NOT explicitly set, **When** the dbt model resolves the `allow_new_hires` default, **Then** it defaults to `true` (backward-compatible behavior when no tenure requirement exists).
3. **Given** `minimum_tenure_years: 2` is configured AND `allow_new_hires: true` is EXPLICITLY set, **When** the simulation runs, **Then** new hires ARE eligible (explicit override respected), and this combination produces a configuration warning.

---

### User Story 3 - Configuration Validation Warning for Contradictory Settings (Priority: P2)

When a plan administrator configures `minimum_tenure_years > 0` alongside `allow_new_hires: true`, the system should emit a clear warning that the tenure requirement is effectively bypassed for all new hires, since this combination is likely unintentional.

**Why this priority**: This prevents future confusion and helps administrators catch configuration mistakes before running simulations.

**Independent Test**: Can be tested by setting contradictory config values and verifying a warning appears in the simulation output or Studio UI.

**Acceptance Scenarios**:

1. **Given** match eligibility has `minimum_tenure_years: 2` AND `allow_new_hires: true`, **When** the simulation starts, **Then** a warning is logged: "Match eligibility: allow_new_hires is true but minimum_tenure_years is 2. New hires will bypass the tenure requirement."
2. **Given** core eligibility has `minimum_tenure_years: 3` AND `allow_new_hires: true`, **When** the simulation starts, **Then** a similar warning is logged for core contributions.
3. **Given** match eligibility has `minimum_tenure_years: 0` AND `allow_new_hires: true`, **When** the simulation starts, **Then** NO warning is logged (this combination is non-contradictory).

---

### Edge Cases

- What happens when `minimum_tenure_years: 1` and an employee has exactly 1.0 year of tenure? They should be eligible (`>=` check).
- What happens when `allow_new_hires: true` is explicitly set with `minimum_tenure_years: 0`? No behavioral change from current -- all new hires eligible.
- What happens when `apply_eligibility: false` (backward-compat mode) for match? The tenure fix should not affect backward-compat mode, which uses the simple active + 1000 hours rule.
- What happens when config is provided via Studio UI (`dc_plan.match_min_tenure_years`) vs YAML (`employer_match.eligibility.minimum_tenure_years`)? Both paths should produce the same behavior.
- What happens in multi-year simulations? An employee hired in Year 1 with `minimum_tenure_years: 2` should become eligible in Year 3 (when their tenure reaches 2.0).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST exclude employees from employer match contributions when their `current_tenure` is less than the configured `minimum_tenure_years` and `allow_new_hires` is `false`.
- **FR-002**: System MUST exclude employees from employer core contributions when their `current_tenure` is less than the configured `minimum_tenure_years` and `allow_new_hires` is `false`.
- **FR-003**: System MUST default `allow_new_hires` to `false` when `minimum_tenure_years > 0` and `allow_new_hires` is not explicitly specified by the user.
- **FR-004**: System MUST default `allow_new_hires` to `true` when `minimum_tenure_years = 0` and `allow_new_hires` is not explicitly specified (preserving backward compatibility).
- **FR-005**: System MUST emit a configuration warning when `allow_new_hires: true` is explicitly set alongside `minimum_tenure_years > 0`.
- **FR-006**: System MUST NOT alter eligibility behavior when `apply_eligibility: false` (backward-compatibility mode for match).
- **FR-007**: System MUST propagate `allow_new_hires` values correctly from both the YAML config path (`employer_match.eligibility`) and the Studio UI path (`dc_plan.match_allow_new_hires`).
- **FR-008**: System MUST report the effective `allow_new_hires` value in eligibility metadata columns for audit purposes.

### Key Entities

- **Employer Eligibility Record**: Determines per-employee, per-year eligibility for match and core contributions. Key attributes: `employee_id`, `simulation_year`, `current_tenure`, `eligible_for_match`, `eligible_for_core`, `match_eligibility_reason`, `match_allow_new_hires` (metadata).
- **Eligibility Configuration**: Nested config controlling tenure, hours, and employment status requirements. Key attributes: `minimum_tenure_years`, `allow_new_hires`, `require_active_at_year_end`, `minimum_hours_annual`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of employees with tenure below the configured minimum and `allow_new_hires: false` show $0 employer match and $0 employer core contributions in `fct_workforce_snapshot`.
- **SC-002**: Existing simulations with `minimum_tenure_years: 0` (the default) produce identical results to pre-fix behavior (no regression).
- **SC-003**: Configuration warnings are emitted within the first 5 seconds of simulation startup when contradictory settings are detected.
- **SC-004**: All existing dbt tests and Python tests pass without modification (except tests that explicitly test the old default behavior, if any).

## Assumptions

- The `current_tenure` field in `int_employee_compensation_by_year` accurately represents years of service at the start of the simulation year. This is relied upon by the eligibility model.
- The `allow_new_hires` flag is intended as a convenience bypass for immediate eligibility plans (tenure = 0). It is not intended to override non-zero tenure requirements unless explicitly opted in.
- Backward-compatibility mode (`apply_eligibility: false`) should remain completely unchanged, as it uses a separate code path.
- The Studio UI already sends `match_allow_new_hires` and `core_allow_new_hires` fields; the fix involves changing defaults in the dbt model and config export layer, not adding new UI fields.
