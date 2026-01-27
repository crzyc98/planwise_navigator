# Feature Specification: Fix 401(a)(17) Compensation Limit for Employer Contributions

**Feature Branch**: `026-fix-401a17-comp-limit`
**Created**: 2026-01-22
**Status**: Draft
**Input**: User description: "Fix 401(a)(17) Compensation Limit for Employer Contributions - For highly compensated employees, employer contributions (match and core) are being calculated on full compensation instead of being limited by the IRS Section 401(a)(17) compensation cap."

## Problem Statement

The workforce simulation engine currently calculates employer contributions (both match and core) using an employee's full compensation, regardless of how high that compensation is. This violates IRS Section 401(a)(17), which caps the compensation amount that can be considered for retirement plan purposes.

**Example of Current Bug**:
- Employee salary: $1,675,000
- Employee contribution: $24,000 (at 402(g) limit)
- Match formula: 100% up to 4% of compensation
- **Current (wrong)**: Match cap = 4% × $1,675,000 = $67,000
- **Correct**: Match cap = 4% × $360,000 (401(a)(17) limit for 2026) = $14,400

This bug results in significantly overstated employer contribution projections for high earners, affecting cost modeling accuracy and compliance reporting.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accurate Match Calculations for High Earners (Priority: P1)

As a plan administrator, I need employer match calculations to respect the IRS 401(a)(17) compensation limit so that projected employer costs are accurate and compliant with federal regulations.

**Why this priority**: This is the core compliance issue. Accurate match calculations directly affect cost projections and regulatory compliance reporting.

**Independent Test**: Can be fully tested by running a simulation with a high-earning employee ($400,000+ salary) and verifying the match amount does not exceed match_rate × $360,000 (for 2026).

**Acceptance Scenarios**:

1. **Given** an employee earning $1,675,000/year with a 4% match cap, **When** the simulation calculates employer match, **Then** the match amount is capped at 4% × $360,000 = $14,400 (for 2026).
2. **Given** an employee earning $200,000/year with a 4% match cap, **When** the simulation calculates employer match, **Then** the match amount is calculated using full compensation (no capping needed).
3. **Given** a simulation spanning 2025-2030, **When** match calculations are performed, **Then** each year uses the appropriate 401(a)(17) limit for that year.

---

### User Story 2 - Accurate Core Contribution Calculations for High Earners (Priority: P1)

As a plan administrator, I need employer core contribution calculations to respect the IRS 401(a)(17) compensation limit so that projected employer costs are accurate and compliant.

**Why this priority**: Core contributions have the same compliance requirement as match contributions. Both must be fixed together for accurate cost modeling.

**Independent Test**: Can be fully tested by running a simulation with a high-earning employee and verifying the core contribution does not exceed core_rate × $360,000 (for 2026).

**Acceptance Scenarios**:

1. **Given** an employee earning $1,675,000/year with a 2% core contribution rate, **When** the simulation calculates employer core contribution, **Then** the core amount is capped at 2% × $360,000 = $7,200 (for 2026).
2. **Given** an employee earning $300,000/year with a 2% core contribution rate, **When** the simulation calculates employer core contribution, **Then** the core amount is calculated using full compensation.

---

### User Story 3 - Multi-Year 401(a)(17) Limit Tracking (Priority: P2)

As a plan administrator, I need the system to apply the correct 401(a)(17) limit for each simulation year so that multi-year projections account for IRS limit adjustments over time.

**Why this priority**: Multi-year accuracy is important for long-term cost forecasting, but depends on the core fix being implemented first.

**Independent Test**: Can be fully tested by running a 5-year simulation and querying the applied compensation limits per year.

**Acceptance Scenarios**:

1. **Given** a simulation from 2025-2030, **When** contribution calculations are performed, **Then** each year uses its respective 401(a)(17) limit (2025: $350,000, 2026: $360,000, etc.).
2. **Given** a simulation for a year not in the configuration, **When** the simulation runs, **Then** the system uses the closest available year's limit and logs a warning.

---

### User Story 4 - Audit Trail for Compensation Capping (Priority: P3)

As an auditor, I need to see when the 401(a)(17) limit was applied to an employee's contribution calculation so that I can verify compliance for reporting purposes.

**Why this priority**: Audit visibility is valuable for compliance verification but is not required for the core fix to function correctly.

**Independent Test**: Can be fully tested by querying contribution records for high earners and verifying a flag or field indicates when capping was applied.

**Acceptance Scenarios**:

1. **Given** a high earner whose compensation exceeds the 401(a)(17) limit, **When** contributions are calculated, **Then** the record includes a flag indicating the limit was applied.
2. **Given** an employee under the 401(a)(17) limit, **When** contributions are calculated, **Then** the audit flag indicates no capping was necessary.

---

### Edge Cases

- What happens when an employee's compensation exactly equals the 401(a)(17) limit? (No capping applied, full compensation used)
- What happens when simulating a year before the earliest configured 401(a)(17) limit? (Use earliest available limit, log warning)
- What happens when simulating a year beyond the latest configured 401(a)(17) limit? (Use latest available limit, log warning)
- How are mid-year hires with prorated compensation handled? (Prorate both compensation and the 401(a)(17) limit proportionally)
- How are terminated employees with partial-year compensation handled? (Apply limit to actual compensation earned during employment period)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST cap compensation used for employer match calculations at the IRS 401(a)(17) limit for the simulation year
- **FR-002**: System MUST cap compensation used for employer core contribution calculations at the IRS 401(a)(17) limit for the simulation year
- **FR-003**: System MUST store 401(a)(17) compensation limits by year in a configurable format
- **FR-004**: System MUST apply year-specific 401(a)(17) limits during multi-year simulations
- **FR-005**: System MUST NOT affect contribution calculations for employees whose compensation is below the 401(a)(17) limit
- **FR-006**: System MUST include an audit indicator when the 401(a)(17) limit is applied to a contribution calculation
- **FR-007**: System MUST handle prorated compensation consistently with the 401(a)(17) limit for mid-year hires and terminations

### Key Entities

- **IRS Compensation Limit**: The annual 401(a)(17) compensation cap that restricts how much compensation can be considered for retirement plan contribution purposes. Key attributes: limit_year, compensation_limit.
- **Employer Match Calculation**: The computed employer match amount based on employee deferral and match formula. Relationship: must use the lesser of actual compensation or 401(a)(17) limit.
- **Employer Core Contribution**: The computed employer core contribution based on compensation and core rate. Relationship: must use the lesser of actual compensation or 401(a)(17) limit.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For employees earning above the 401(a)(17) limit, employer match amounts are at most match_rate × compensation_limit (no violations)
- **SC-002**: For employees earning above the 401(a)(17) limit, employer core contributions are at most core_rate × compensation_limit (no violations)
- **SC-003**: For employees earning below the 401(a)(17) limit, contribution calculations remain unchanged from current behavior
- **SC-004**: All multi-year simulations apply the correct 401(a)(17) limit for each respective year
- **SC-005**: 100% of high-earner contribution records include audit visibility into whether the limit was applied

## Assumptions

- The 401(a)(17) limit values follow IRS published schedules and can be estimated for future years using reasonable extrapolation (approximately $10,000 increase per year based on recent trends)
- Mid-year hires and terminations should have the 401(a)(17) limit prorated proportionally to their employment period within the simulation year
- The existing IRS limits configuration structure can be extended to include the 401(a)(17) compensation limit without breaking existing functionality
- Service-based match calculations use the same compensation capping logic as deferral-based match calculations

## Out of Scope

- Changes to employee deferral calculations (402(g) limits are already implemented separately)
- Changes to catch-up contribution calculations
- Highly Compensated Employee (HCE) testing or ADP/ACP non-discrimination testing
- Section 415 annual additions limit ($69,000 for 2024) enforcement
