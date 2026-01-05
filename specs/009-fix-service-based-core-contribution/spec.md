# Feature Specification: Fix Service-Based Core Contribution Calculation

**Feature Branch**: `009-fix-service-based-core-contribution`
**Created**: 2026-01-05
**Status**: Draft
**Input**: User description: "In our DC plan configuration using the user interface I am able to set different fixed core amounts based on the years of service for the employee. In the UI it is called graded by service. I just ran a test where the baseline is that 8% for everyone is the core but the scenario lowered that for the first 10 years of service to 6% (0 to 9 years gets 6%, 10 to infinity gets 8%) but it gave 8% to everyone."

## Problem Statement

The DC Plan configuration UI allows users to configure graded-by-service core contribution rates (different employer core contribution percentages based on employee years of service). However, when a scenario is configured with service-based tiers, the simulation ignores these tiers and applies the baseline rate to all employees regardless of their tenure.

**Example**: When configured with:
- Years 0-9: 6% core contribution
- Years 10+: 8% core contribution

All employees receive 8% instead of the service-tiered rates.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply Service-Based Core Rates (Priority: P1)

As a plan administrator, I want the simulation to apply the correct core contribution rate based on each employee's years of service so that I can accurately model tiered employer contribution structures.

**Why this priority**: This is the core bug fix. Without it, the graded-by-service feature is non-functional, making cost projections inaccurate for plans with service-based contribution tiers.

**Independent Test**: Can be fully tested by configuring a scenario with service-based core tiers and verifying that employees with different tenure levels receive different contribution rates.

**Acceptance Scenarios**:

1. **Given** a scenario configured with core contribution tiers (0-9 years: 6%, 10+ years: 8%), **When** the simulation runs, **Then** an employee with 5 years of service receives a 6% core contribution rate.

2. **Given** a scenario configured with core contribution tiers (0-9 years: 6%, 10+ years: 8%), **When** the simulation runs, **Then** an employee with 15 years of service receives an 8% core contribution rate.

3. **Given** a scenario configured with core contribution tiers (0-9 years: 6%, 10+ years: 8%), **When** the simulation runs, **Then** an employee with exactly 10 years of service receives an 8% core contribution rate.

4. **Given** a scenario with no service-based tiers (flat 8% for all), **When** the simulation runs, **Then** all employees receive the flat 8% rate regardless of tenure.

---

### User Story 2 - Verify Multi-Tier Service Schedules (Priority: P2)

As a plan administrator, I want to configure multiple service tiers (e.g., 0-2 years, 3-5 years, 6-10 years, 11+ years) and have each tier apply correctly so that I can model complex graded contribution structures.

**Why this priority**: Many real-world plans have 3+ service tiers. After fixing the basic 2-tier case, multi-tier support should work but needs verification.

**Independent Test**: Configure a 4-tier service schedule and verify each tier applies to employees in the appropriate tenure range.

**Acceptance Scenarios**:

1. **Given** a scenario with 4 service tiers (0-2y: 4%, 3-5y: 5%, 6-10y: 6%, 11+y: 8%), **When** the simulation runs, **Then** each employee receives the rate corresponding to their tenure bracket.

2. **Given** an employee who crosses a service tier boundary during the simulation year, **When** calculating their annual contribution, **Then** the system applies the appropriate rate based on their tenure at the contribution date.

---

### User Story 3 - Maintain Audit Trail for Service-Based Rates (Priority: P3)

As an auditor, I want to see which service tier and rate was applied to each employee's core contribution so that I can verify the calculation is correct.

**Why this priority**: Transparency is essential for compliance. This ensures users can trace why each employee received their specific rate.

**Independent Test**: Review contribution events and verify each includes the service tier applied.

**Acceptance Scenarios**:

1. **Given** a completed simulation with service-based tiers, **When** I review the contribution events, **Then** each contribution event shows the service tier that was applied.

2. **Given** a completed simulation with service-based tiers, **When** I compare an employee's tenure to their applied rate, **Then** they match the configured tier schedule.

---

### Edge Cases

- What happens when an employee has exactly 0 years of service (new hire)? They should receive the first tier rate.
- What happens when tenure is fractional (e.g., 9.5 years)? The integer year boundary should determine the tier (9.5 years = tier for 9 years).
- What happens when no service tiers are configured (graded-by-service disabled)? The flat rate should apply to all employees.
- What happens when an employee's tenure exceeds all defined tiers? The highest tier rate should apply.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST look up the configured service-based core contribution tiers when calculating employer core contributions.
- **FR-002**: System MUST match each employee's years of service to the appropriate tier based on the tier's service range.
- **FR-003**: System MUST apply the tier-specific rate rather than the baseline flat rate when service tiers are configured.
- **FR-004**: System MUST use integer years of service for tier matching (floor of tenure).
- **FR-005**: System MUST apply the highest tier rate for employees whose tenure exceeds all defined tier boundaries.
- **FR-006**: System MUST preserve existing behavior (flat rate for all) when graded-by-service is not configured or is disabled.
- **FR-007**: System MUST record the applied service tier in contribution events for audit purposes.

### Key Entities

- **Service Tier**: A configured rule specifying a minimum and maximum years of service and the core contribution rate that applies within that range.
- **Employee Tenure**: The number of complete years an employee has been with the organization, used to determine their applicable service tier.
- **Core Contribution Event**: A record of an employer core contribution, including the rate applied and the service tier used.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of employees in a simulation with service-based tiers receive the rate matching their tenure bracket.
- **SC-002**: Simulation results for a 2-tier scenario (0-9 years: 6%, 10+ years: 8%) show distinct contribution rates for employees above and below the 10-year threshold.
- **SC-003**: Existing simulations without graded-by-service configuration produce identical results before and after the fix (no regression).
- **SC-004**: Plan administrators can configure and run a service-based scenario in under 5 minutes using the existing UI.

## Assumptions

- The UI correctly saves service-based tier configuration to the underlying data store; the bug is in the simulation engine reading/applying these tiers.
- Years of service is calculated from the employee's hire date and is already available in the simulation.
- The service tier configuration uses a standard format with min/max service years and rate per tier.
- Tier boundaries follow the [min, max) convention (minimum inclusive, maximum exclusive), consistent with existing band definitions.

## Out of Scope

- Changes to the UI for configuring graded-by-service tiers (assumed to work correctly).
- Support for mid-year tier changes (employee contributions are calculated based on tenure at contribution date).
- Service tiers for match contributions (this fix addresses core contributions only).

## Clarifications

### Session 2026-01-05

- Q: Where in the codebase is the service-tier lookup logic expected to be fixed? → A: Unsure – investigation needed to locate the bug.

## Implementation Notes

- **Investigation Required**: The exact location of the bug (dbt SQL models vs. Polars pipeline vs. configuration loading) is unknown. The implementation plan must include a diagnostic phase to trace the service-tier configuration flow from UI storage through to contribution calculation.
