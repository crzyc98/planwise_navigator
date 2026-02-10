# Feature Specification: Fix Yearly Participation Rate Consistency

**Feature Branch**: `041-fix-yearly-participation-rate`
**Created**: 2026-02-10
**Status**: Draft
**Input**: User description: "Fix participation rate to be computed consistently per year in the analytics service contribution summary"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consistent Per-Year Participation Rate (Priority: P1)

As a plan analyst viewing single-scenario DC plan analytics, I need the participation rate for each simulation year to be computed using the same population filter (active employees only) as the top-level participation rate, so that the year-by-year trend and the summary number tell a consistent story.

Currently, the top-level participation rate filters to active employees only, while the per-year participation rate in the contribution summary includes all employees (active and terminated). This creates a misleading discrepancy where per-year rates appear lower than the summary rate because terminated employees dilute the denominator.

**Why this priority**: This is the core data consistency fix. Without it, analysts cannot trust the year-by-year participation trend because it uses a different calculation methodology than the headline number.

**Independent Test**: Can be fully tested by running a multi-year simulation, querying the analytics endpoint, and verifying that the per-year participation rate for the final year matches the top-level participation rate.

**Acceptance Scenarios**:

1. **Given** a completed multi-year simulation with active and terminated employees, **When** I request DC plan analytics for that scenario, **Then** each year's participation rate in the contribution summary is computed using only active employees as the denominator.
2. **Given** a completed simulation, **When** I request DC plan analytics, **Then** the participation rate for the final year in the contribution summary matches the top-level participation rate (within rounding tolerance).
3. **Given** a simulation where all employees remain active across all years, **When** I request DC plan analytics, **Then** the per-year participation rates are identical to what they were before this fix (no behavioral change for the no-termination case).

---

### User Story 2 - Backward-Compatible Top-Level Participation Rate (Priority: P2)

As a consumer of the DC plan analytics API, I need the top-level `participation_rate`, `total_eligible`, and `total_enrolled` fields in `DCPlanAnalytics` to remain unchanged (final-year values), so that existing dashboards, reports, and comparison views continue to work without modification.

**Why this priority**: Breaking backward compatibility would cascade failures across the frontend and any integrations consuming the analytics response.

**Independent Test**: Can be tested by comparing the analytics API response structure and top-level field values before and after the fix against the same simulation database.

**Acceptance Scenarios**:

1. **Given** the same simulation database, **When** I request DC plan analytics before and after this fix, **Then** the top-level `participation_rate`, `total_eligible`, and `total_enrolled` fields return identical values.
2. **Given** a multi-scenario comparison, **When** I request the comparison endpoint, **Then** each scenario's top-level participation rate continues to reflect the final-year value.

---

### Edge Cases

- What happens when a simulation year has zero active employees? The participation rate for that year should be 0.0 (not an error or null).
- What happens when all active employees in a given year are enrolled? The participation rate should be exactly 100.0.
- What happens for years where employees were hired and terminated within the same year? Only active employees at year-end should count toward the participation rate.
- What happens when a single-year simulation is run? The per-year participation rate and the top-level rate should be identical.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute participation rate per simulation year using only active employees as the population (denominator = count of active employees, numerator = count of active enrolled employees).
- **FR-002**: System MUST include the per-year participation rate in each `ContributionYearSummary` entry in the analytics response.
- **FR-003**: System MUST preserve the top-level `participation_rate` in `DCPlanAnalytics` as the final-year participation rate for backward compatibility.
- **FR-004**: System MUST return 0.0 as the participation rate for any year with zero active employees (graceful handling of division by zero).
- **FR-005**: System MUST use a consistent definition of "active employee" across the top-level participation summary and the per-year contribution summary (same employment status filter).

### Key Entities

- **ContributionYearSummary**: Per-year contribution and participation data. The `participation_rate` field must reflect active-employee-only calculation.
- **DCPlanAnalytics**: Top-level analytics response. The `participation_rate` field continues to reflect final-year active-employee participation.
- **fct_workforce_snapshot**: Source data table containing per-employee, per-year records with `employment_status`, `is_enrolled_flag`, and contribution amounts.

## Assumptions

- The existing `participation_rate` field on `ContributionYearSummary` is the correct place to store the per-year rate (no new fields needed).
- "Active employee" is defined by `UPPER(employment_status) = 'ACTIVE'`, consistent with the existing `_get_participation_summary()` method.
- The contribution totals in `_get_contribution_by_year()` should continue to include all employees (active + terminated) since terminated employees may have made contributions during the year before leaving. Only the participation rate calculation changes scope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any completed simulation, the participation rate for the final year in the contribution summary matches the top-level participation rate within 0.01 percentage points.
- **SC-002**: All existing analytics tests continue to pass without modification to expected values (or with intentional updates reflecting the corrected calculation).
- **SC-003**: The analytics endpoint returns a valid response with per-year participation rates for 100% of simulation years present in the data.
- **SC-004**: The analytics response structure (field names, types, nesting) remains identical to the current schema, ensuring zero breaking changes for consumers.
