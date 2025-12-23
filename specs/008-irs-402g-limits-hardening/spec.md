# Feature Specification: IRS 402(g) Limits Hardening

**Feature Branch**: `008-irs-402g-limits-hardening`
**Created**: 2025-12-23
**Status**: Draft
**Input**: User description: "Harden IRS 402(g) contribution limit enforcement with comprehensive edge case testing. Preserved behavior: no employee contribution exceeds $23,500 (base 2024) or $31,000 (with catch-up), irs_limit_applied flag set correctly on capped contributions. Improved constraints: property-based tests asserting max(contribution) <= applicable_limit for ALL employees in ALL scenarios, catch-up age threshold (50) moved to configurable seed instead of hardcoded, future IRS limits (2025, 2026+) addable via seed file without code changes. Seed file: dbt/seeds/config_irs_limits.csv with columns (year, base_limit, catchup_limit, catchup_age). This enables multi-year forward projections and plan year flexibility."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - IRS Limit Compliance Guarantee (Priority: P1)

A compliance officer needs assurance that no 401(k) contributions in any simulation scenario can ever exceed IRS 402(g) limits. When simulations run across multiple years and scenarios, every contribution must be capped at the applicable limit based on the employee's age and the plan year's IRS limits.

**Why this priority**: IRS compliance is non-negotiable. Violations could result in plan disqualification, corrective distributions, and regulatory penalties. This is the core value of the feature.

**Independent Test**: Can be fully tested by running a simulation with high-income employees (compensation > $500K) at 100% deferral rates and verifying no contribution exceeds the applicable IRS limit. Delivers guaranteed regulatory compliance.

**Acceptance Scenarios**:

1. **Given** an employee under age 50 with annual compensation of $500,000 and 100% deferral rate, **When** contributions are calculated for plan year 2025, **Then** the contribution is capped at $23,500 (the 2025 base limit) and `irs_limit_applied` flag is set to TRUE.

2. **Given** an employee age 55 with annual compensation of $500,000 and 100% deferral rate, **When** contributions are calculated for plan year 2025, **Then** the contribution is capped at $31,000 (the 2025 catch-up limit) and `irs_limit_applied` flag is set to TRUE.

3. **Given** a batch of 10,000 employees across all age ranges and compensation levels, **When** contributions are calculated for simulation years 2025-2030, **Then** no employee's contribution exceeds their applicable IRS limit in any year.

---

### User Story 2 - Configurable IRS Limits via Seed File (Priority: P2)

A plan administrator needs to update IRS contribution limits for future plan years without requiring code changes. When the IRS announces new limits for 2027, the administrator should be able to add a row to a configuration file and re-run simulations with the new limits immediately.

**Why this priority**: IRS adjusts limits annually for inflation. Self-service configuration eliminates developer dependency and enables rapid response to regulatory changes.

**Independent Test**: Can be fully tested by adding a new year row to the seed file, running dbt seed, and verifying simulations use the new limits without any code modifications.

**Acceptance Scenarios**:

1. **Given** the IRS announces 2028 base limit of $24,500, **When** an administrator adds a row (2028, 24500, 32500, 50) to the limits seed file and runs dbt seed, **Then** simulations for 2028 automatically enforce the new $24,500 base limit.

2. **Given** no limit exists in the seed file for plan year 2040, **When** contributions are calculated for 2040, **Then** the system uses the nearest available year's limits as a fallback (with appropriate logging).

3. **Given** the seed file contains limits for years 2025-2035, **When** the limits are loaded, **Then** all columns (year, base_limit, catchup_limit, catchup_age) are properly parsed and available to contribution calculations.

---

### User Story 3 - Configurable Catch-Up Age Threshold (Priority: P3)

A plan administrator needs flexibility to configure the catch-up eligibility age in case IRS regulations change or for modeling "what-if" scenarios with different age thresholds.

**Why this priority**: Currently hardcoded at 50, but regulatory changes or plan-specific modeling may require different thresholds. Seed-based configuration enables flexibility without code changes.

**Independent Test**: Can be fully tested by changing the catch-up age in the seed file from 50 to 55, re-running dbt seed, and verifying that only employees 55+ receive catch-up limit treatment.

**Acceptance Scenarios**:

1. **Given** the seed file specifies catchup_age = 50 for 2025, **When** a 50-year-old employee's contribution is calculated, **Then** they receive the catch-up limit ($31,000) rather than the base limit ($23,500).

2. **Given** the seed file is updated with catchup_age = 55 for 2026, **When** a 52-year-old employee's contribution is calculated for 2026, **Then** they receive only the base limit, not the catch-up limit.

3. **Given** different catchup_age values for different plan years (e.g., 50 for 2025, 55 for 2030), **When** multi-year simulations run, **Then** each year correctly applies its configured catch-up age threshold.

---

### User Story 4 - Property-Based Testing for All Scenarios (Priority: P4)

A quality assurance engineer needs comprehensive automated tests that assert contribution limits are enforced across all possible employee combinations and scenarios, not just specific test cases.

**Why this priority**: Point-in-time tests can miss edge cases. Property-based tests provide mathematical guarantees that the limit invariant holds for all inputs.

**Independent Test**: Can be fully tested by running property-based tests that generate random employee populations with extreme values and verifying the MAX(contribution) <= applicable_limit property holds in 100% of cases.

**Acceptance Scenarios**:

1. **Given** a property-based test framework, **When** 10,000 random employees are generated with ages 18-75, compensation $0-$5M, and deferral rates 0-100%, **Then** no contribution exceeds the applicable IRS limit for any employee.

2. **Given** property-based tests run as part of CI/CD pipeline, **When** a code change introduces a potential limit violation, **Then** the property test fails before deployment.

3. **Given** multiple scenarios (baseline, high_growth, recession), **When** property tests run across all scenarios, **Then** the MAX(contribution) <= applicable_limit invariant holds for every scenario.

---

### Edge Cases

- What happens when an employee turns 50 mid-year? (Use age as of December 31 of plan year for catch-up eligibility)
- What happens when deferral rate is exactly 0%? (Contribution is $0, no limit enforcement needed)
- What happens when compensation is $0 or negative? (Contribution is $0, no limit enforcement needed)
- What happens when limit year is missing from seed file? (Fall back to nearest available year with warning)
- What happens when prorated compensation due to termination results in a contribution naturally below the limit? (No capping needed, irs_limit_applied = FALSE)
- What happens with rounding at exact boundary values? (Use >= for limit comparison, contribution capped to exact limit value)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST cap employee contributions at the IRS 402(g) base limit for employees under the catch-up age threshold
- **FR-002**: System MUST cap employee contributions at the IRS 402(g) catch-up limit for employees at or above the catch-up age threshold
- **FR-003**: System MUST set `irs_limit_applied` flag to TRUE when a contribution is capped, FALSE otherwise
- **FR-004**: System MUST record `amount_capped_by_irs_limit` showing the difference between requested and actual contribution when capped
- **FR-005**: System MUST read IRS limits from a configurable seed file named `config_irs_limits.csv` (renaming from current `irs_contribution_limits.csv` for naming consistency)
- **FR-006**: System MUST support columns: year, base_limit, catchup_limit, catchup_age in the limits seed file
- **FR-007**: System MUST use the catch-up age threshold from the seed file rather than hardcoded value of 50
- **FR-008**: System MUST fall back to the nearest available year's limits when a specific year is not configured
- **FR-009**: System MUST enforce limits across all simulation scenarios without exception
- **FR-010**: System MUST include property-based tests that verify max(contribution) <= applicable_limit for all employees
- **FR-011**: System MUST preserve existing transparency fields: `requested_contribution_amount`, `applicable_irs_limit`, `limit_type`

### Key Entities

- **IRS Limit Configuration**: Represents a year's IRS 402(g) limits (year, base_limit, catchup_limit, catchup_age)
- **Employee Contribution**: Represents calculated contribution with limit enforcement fields (annual_contribution_amount, irs_limit_applied, amount_capped_by_irs_limit)
- **Catch-Up Eligibility**: Derived from employee age compared to configured catchup_age threshold

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of contributions across all simulations comply with applicable IRS 402(g) limits (zero violations allowed)
- **SC-002**: Property-based tests pass with 10,000+ random employee combinations and 100% limit compliance
- **SC-003**: Administrators can add new IRS limit years by updating only the seed file (zero code changes required)
- **SC-004**: Catch-up age threshold changes via seed file take effect immediately after dbt seed (no code deployment needed)
- **SC-005**: All existing IRS compliance tests continue to pass (no regression)
- **SC-006**: `irs_limit_applied` flag accuracy is 100% (flag matches actual capping behavior in all cases)

## Assumptions

- The current `irs_contribution_limits.csv` seed file will be renamed to `config_irs_limits.csv` for naming consistency with other config seeds
- Age is determined as of December 31 of the plan year for catch-up eligibility (consistent with IRS rules)
- The existing fallback logic (nearest year) for missing limit years is acceptable behavior
- Property-based tests will use the Hypothesis Python library (industry standard for property-based testing)
- IRS limits apply per plan year, not calendar year, and plan year equals calendar year in this system
- The catch-up age threshold of 50 is the current IRS standard but the system should support configuration for future-proofing
