# Feature Specification: Fix Auto-Escalation Hire Date Filter

**Feature Branch**: `002-fix-auto-escalation-hire-filter`
**Created**: 2025-12-12
**Status**: Implemented
**Input**: User description: "Auto-escalation hire date cutoff filter is not being applied correctly - employees hired before the cutoff date are still being escalated"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Auto-Escalation for New Hires Only (Priority: P1)

A plan administrator configures auto-escalation to apply only to employees hired on or after January 1, 2026. When the simulation runs for years 2026-2030, only employees with hire dates on or after 2026-01-01 should receive deferral rate escalation events. Employees hired before this date (including existing census employees) should not have their deferral rates automatically escalated.

**Why this priority**: This is the core business requirement. Plan sponsors often want to offer auto-escalation as a benefit to new hires while keeping existing participants under their original plan terms. Incorrect filtering defeats the purpose of the hire date cutoff configuration.

**Independent Test**: Can be fully tested by configuring a scenario with `hire_date_cutoff: "2026-01-01"`, running a multi-year simulation, and verifying that only employees with hire dates >= 2026-01-01 receive escalation events. Delivers the ability to target auto-escalation to specific hire cohorts.

**Acceptance Scenarios**:

1. **Given** a scenario with `hire_date_cutoff: "2026-01-01"` and simulation years 2026-2030, **When** the simulation runs, **Then** employees hired on 2026-01-01 or later should receive escalation events, and employees hired before 2026-01-01 should NOT receive escalation events.

2. **Given** a scenario with `hire_date_cutoff: "2026-01-01"` and an employee hired on 2025-12-31, **When** the simulation generates escalation events for 2027, **Then** that employee should NOT have any deferral_escalation events.

3. **Given** a scenario with `hire_date_cutoff: "2026-01-01"` and an employee hired on 2026-01-01 (the exact cutoff date), **When** the simulation generates escalation events for 2027, **Then** that employee SHOULD have deferral_escalation events (assuming other eligibility criteria are met).

---

### User Story 2 - Auto-Escalation for All Employees (Priority: P2)

A plan administrator wants auto-escalation to apply to all employees regardless of hire date. They configure `hire_date_cutoff: "1900-01-01"` (or leave it unset). All enrolled employees should receive escalation events.

**Why this priority**: This validates that the default/broad configuration continues to work correctly while the targeted hire date filtering is implemented.

**Independent Test**: Can be fully tested by configuring a scenario with `hire_date_cutoff: "1900-01-01"`, running a simulation, and verifying all enrolled employees receive escalation events. Delivers backward compatibility for plans that want universal auto-escalation.

**Acceptance Scenarios**:

1. **Given** a scenario with `hire_date_cutoff: "1900-01-01"` (effectively all employees), **When** the simulation runs, **Then** all enrolled employees regardless of hire date should receive escalation events (subject to other eligibility criteria like enrollment status and rate cap).

---

### User Story 3 - Comparison of Escalation Counts Between Scenarios (Priority: P2)

A plan administrator runs two scenarios to compare costs: one with auto-escalation for all employees (cutoff 1900-01-01) and one with auto-escalation only for new hires (cutoff 2026-01-01). The escalation event counts should differ significantly, with the new-hires-only scenario having far fewer escalation events.

**Why this priority**: This validates the business value of the feature - the ability to model different auto-escalation policies and compare their impact.

**Independent Test**: Run both scenarios and compare the count of deferral_escalation events. The scenario with the future cutoff date should have measurably fewer escalation events than the all-employees scenario.

**Acceptance Scenarios**:

1. **Given** two scenarios with identical configurations except hire_date_cutoff ("1900-01-01" vs "2026-01-01") running simulation years 2026-2030, **When** both simulations complete, **Then** the scenario with cutoff "2026-01-01" should have significantly fewer deferral_escalation events than the scenario with cutoff "1900-01-01".

---

### Edge Cases

- **Exactly on cutoff date**: An employee hired on the exact cutoff date (e.g., 2026-01-01 when cutoff is 2026-01-01) should be eligible for escalation.
- **No cutoff configured**: When `hire_date_cutoff` is null/unset, all employees should be eligible (no hire date filtering applied).
- **Cutoff in the past**: When cutoff is set to a past date like "1900-01-01", effectively all employees should be eligible.
- **Cutoff in the future**: When cutoff is set to a far future date like "2999-01-01", effectively no employees should be eligible.
- **Census employees with pre-simulation hire dates**: Employees from the baseline census (hired before simulation start) should be correctly filtered based on their actual hire dates.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST only generate deferral_escalation events for employees whose hire date is on or after the configured `hire_date_cutoff` value.
- **FR-002**: System MUST use inclusive comparison (`>=`) for the hire date cutoff, not exclusive (`>`), so that employees hired ON the cutoff date are eligible.
- **FR-003**: System MUST apply the hire date filter consistently across both SQL and Polars event generation modes.
- **FR-004**: System MUST handle null/unset `hire_date_cutoff` by not applying any hire date filtering (all employees eligible).
- **FR-005**: System MUST correctly interpret the `deferral_auto_escalation.hire_date_cutoff` configuration from scenario YAML files.

### Key Entities

- **Deferral Escalation Event**: An event that increments an employee's deferral rate. Key attributes: employee_id, effective_date, previous_deferral_rate, new_deferral_rate.
- **Employee Hire Date**: The date an employee was hired, stored in the workforce/census data. Used as the filter criterion.
- **Hire Date Cutoff**: A configuration parameter that specifies the minimum hire date for auto-escalation eligibility.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a scenario is configured with `hire_date_cutoff: "2026-01-01"`, zero deferral_escalation events should be generated for employees with hire dates before 2026-01-01.
- **SC-002**: When a scenario is configured with `hire_date_cutoff: "2026-01-01"`, employees hired on exactly 2026-01-01 should receive escalation events (assuming other eligibility criteria are met).
- **SC-003**: The count of escalation events for a "new hires only" scenario (cutoff 2026-01-01) should be measurably lower than an "all eligible" scenario (cutoff 1900-01-01) when running identical multi-year simulations with the same workforce.
- **SC-004**: The fix should not change behavior when `hire_date_cutoff` is null or set to a past date like "1900-01-01" (backward compatibility).

## Assumptions

- The user has two scenarios configured: one with `hire_date_cutoff: "1900-01-01"` (all employees) and one with `hire_date_cutoff: "2026-01-01"` (new hires only).
- The simulation years are 2026-2030.
- The baseline census contains employees hired before 2026-01-01.
- The current behavior incorrectly escalates employees hired before the cutoff date because the comparison operator may be incorrect or the filter may not be applied consistently across all code paths.
