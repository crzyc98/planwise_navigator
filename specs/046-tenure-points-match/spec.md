# Feature Specification: Tenure-Based and Points-Based Employer Match Modes

**Feature Branch**: `046-tenure-points-match`
**Created**: 2026-02-11
**Status**: Draft
**Input**: User description: "Add tenure-based and points-based employer match calculation modes that can be configured per scenario alongside existing deferral-based and graded-by-service match types."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Points-Based Match Formula (Priority: P1)

A plan administrator wants to set up a points-based employer match where match rates increase as employees accumulate more combined age and service years. The administrator selects "points_based" as the match mode, defines point-tier breakpoints (e.g., 0-40 points = 25% match, 40-60 = 50%, 60-80 = 75%, 80+ = 100%), and runs a multi-year simulation. The system calculates each employee's points as age + tenure, assigns the correct tier, and computes the match amount accordingly.

**Why this priority**: Points-based matching is entirely new functionality not currently supported by any existing mode. It requires new configuration, new calculation logic, and new audit fields — making it the highest-risk, highest-value deliverable.

**Independent Test**: Can be fully tested by configuring a scenario with `employer_match_status: 'points_based'`, defining 4 point tiers, running a 3-year simulation, and verifying that match amounts reflect each employee's age+tenure points tier.

**Acceptance Scenarios**:

1. **Given** a scenario configured with `employer_match_status: 'points_based'` and 4 point tiers, **When** a simulation year is executed, **Then** each eligible employee's match amount is calculated using the points tier that matches their `FLOOR(current_age) + FLOOR(years_of_service)`.
2. **Given** an employee with age 38 and 7 years of service (points = 45), **When** the points tiers define 40-60 as 50% match with 6% max deferral, **Then** the match equals `0.50 x min(employee_deferral%, 6%) x capped_compensation`.
3. **Given** a 3-year simulation with points-based matching, **When** an employee ages from points=59 in Year 1 to points=61 in Year 2, **Then** the employee's match tier changes from 50% to 75% in Year 2.
4. **Given** a points-based simulation, **When** match results are produced, **Then** each result includes an `applied_points` audit field showing the employee's calculated points value.

---

### User Story 2 - Configure Tenure-Based Match Formula (Priority: P2)

A plan administrator wants to set up an employer match where the match rate increases with employee tenure using configurable breakpoints. The administrator selects "tenure_based" as the match mode, defines tenure tiers (e.g., 0-2 years = 25%, 2-5 years = 50%, 5-10 years = 75%, 10+ years = 100%), and runs a simulation. The system assigns each employee to the correct tenure tier and computes the match.

**Why this priority**: The existing `graded_by_service` mode provides a foundation for tenure-based matching but uses a different configuration structure. This story enhances the system to support the `tenure_based` mode with the same tier schema as points-based (min/max bounds, match_rate, max_deferral_pct), providing a consistent configuration experience across both new modes.

**Independent Test**: Can be fully tested by configuring a scenario with `employer_match_status: 'tenure_based'`, defining 4 tenure tiers, running a simulation, and verifying match amounts match expected tenure-tier rates.

**Acceptance Scenarios**:

1. **Given** a scenario configured with `employer_match_status: 'tenure_based'` and tenure tiers, **When** a simulation year is executed, **Then** each eligible employee's match rate is determined by their years-of-service tier.
2. **Given** an employee with 3 years of tenure, **When** the tenure tiers define 2-5 years as 50% match with 6% max deferral, **Then** the match equals `0.50 x min(employee_deferral%, 6%) x capped_compensation`.
3. **Given** a multi-year simulation, **When** an employee's tenure crosses a tier boundary (e.g., from 4.8 to 5.2 years), **Then** the match rate updates to the new tier rate in the year the boundary is crossed.

---

### User Story 3 - Validate Tier Configurations (Priority: P2)

A plan administrator defines tier breakpoints for either tenure-based or points-based matching. The system validates that the tier configuration is well-formed: no gaps between tiers, no overlapping ranges, the first tier starts at 0, and each tier's upper bound exceeds its lower bound. If validation fails, the administrator receives clear error messages identifying the specific issue.

**Why this priority**: Invalid tier configurations could produce incorrect match calculations or simulation failures. Validation must be in place before either new match mode is usable in production.

**Independent Test**: Can be tested by providing various valid and invalid tier configurations and verifying that validation accepts correct configs and rejects malformed ones with descriptive error messages.

**Acceptance Scenarios**:

1. **Given** a tenure tier configuration with a gap (e.g., tier 1 ends at 2, tier 2 starts at 3), **When** the configuration is validated, **Then** the system reports a "gap between tiers" error.
2. **Given** a points tier configuration with overlapping ranges (e.g., tier 1 is 0-50, tier 2 is 40-60), **When** the configuration is validated, **Then** the system reports an "overlapping tiers" error.
3. **Given** a valid tier configuration with contiguous ranges starting at 0 and ending with a null upper bound, **When** validated, **Then** the configuration is accepted without errors.

---

### User Story 4 - Edit Match Mode in PlanAlign Studio (Priority: P3)

A plan administrator uses the PlanAlign Studio web interface to select one of the four match modes (deferral_based, graded_by_service, tenure_based, points_based) and configure the corresponding tier breakpoints visually. The UI provides an editable table for tier definitions with real-time validation feedback.

**Why this priority**: The web interface enhances usability but is not required for the core calculation logic. Administrators can configure match modes via YAML configuration as an alternative.

**Independent Test**: Can be tested by launching PlanAlign Studio, selecting each match mode, editing tier breakpoints, saving, and verifying the configuration persists and is used in subsequent simulations.

**Acceptance Scenarios**:

1. **Given** a workspace in PlanAlign Studio, **When** the administrator selects "points_based" match mode, **Then** a tier configuration editor appears with columns for min points, max points, match rate, and max deferral percentage.
2. **Given** a points-based tier editor with invalid tiers (gaps), **When** the administrator attempts to save, **Then** validation errors are displayed inline before the configuration is persisted.

---

### Edge Cases

- What happens when an employee's points calculation results in exactly a tier boundary value (e.g., points = 40 with tiers [0,40) and [40,60))? The `[min, max)` convention means 40 points falls into the [40,60) tier.
- What happens when a new hire has 0 years of service and age 22 (points = 22)? They should be assigned to the lowest points tier (e.g., [0, 40)).
- What happens when the highest tier has `max_points: null` (unbounded)? Employees with any points value above the last tier's min_points receive that tier's rate.
- What happens when an employee is not eligible for matching (fails eligibility requirements)? The match amount is 0 regardless of their points or tenure tier; the `applied_points` field is still populated for auditability.
- What happens when an employee has zero deferrals? The match amount is 0 because the formula includes `min(employee_deferral%, max_deferral_pct)` which yields 0. Match status should be "no_deferrals".
- What happens when an employee's compensation exceeds the IRS 401(a)(17) limit? Compensation is capped at the IRS limit before the match formula is applied, consistent with existing modes.
- What happens when `employer_match_status` is set to an unrecognized value? Configuration validation rejects the value with a clear error message listing valid options.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support `employer_match_status` values of `'deferral_based'`, `'graded_by_service'`, `'tenure_based'`, and `'points_based'` as mutually exclusive match calculation modes.
- **FR-002**: System MUST allow configuration of `tenure_match_tiers` as an ordered list of tiers, each specifying `min_years`, `max_years` (nullable for unbounded), `match_rate` (percentage), and `max_deferral_pct` (percentage).
- **FR-003**: System MUST allow configuration of `points_match_tiers` as an ordered list of tiers, each specifying `min_points`, `max_points` (nullable for unbounded), `match_rate` (percentage), and `max_deferral_pct` (percentage).
- **FR-004**: For `tenure_based` mode, system MUST calculate match as: `tenure_tier_rate x min(employee_deferral%, tier_max_deferral_pct) x capped_compensation`, where the tenure tier is determined by the employee's years of service.
- **FR-005**: For `points_based` mode, system MUST calculate match as: `points_tier_rate x min(employee_deferral%, tier_max_deferral_pct) x capped_compensation`, where points = `FLOOR(current_age) + FLOOR(years_of_service)`.
- **FR-006**: System MUST assign tiers using the `[min, max)` interval convention (lower bound inclusive, upper bound exclusive).
- **FR-007**: System MUST include an `applied_points` audit field in match calculation output when using `points_based` mode, containing the employee's calculated points value.
- **FR-008**: System MUST continue to apply the IRS Section 401(a)(17) compensation cap before calculating match amounts in all modes.
- **FR-009**: System MUST validate tier configurations to ensure: no gaps between consecutive tiers, no overlapping ranges, first tier starts at 0, each tier's upper bound exceeds its lower bound, and at least one tier is defined.
- **FR-010**: System MUST leave existing `deferral_based` and `graded_by_service` match modes fully functional and unaffected by the addition of new modes.
- **FR-011**: System MUST correctly recalculate points and tenure each simulation year so that employees crossing tier boundaries receive updated match rates.
- **FR-012**: System MUST apply match eligibility requirements (minimum tenure, active status, minimum hours) consistently across all match modes.

### Key Entities

- **Match Tier (Tenure)**: A range of years-of-service values mapped to a match rate and max deferral percentage. Attributes: min_years, max_years, match_rate, max_deferral_pct.
- **Match Tier (Points)**: A range of age+tenure point values mapped to a match rate and max deferral percentage. Attributes: min_points, max_points, match_rate, max_deferral_pct.
- **Employee Points**: A calculated value per employee per simulation year equal to `FLOOR(current_age) + FLOOR(years_of_service)`, used for tier assignment in points-based mode.
- **Match Calculation Result**: The output of the match formula for each employee, including match amount, formula type, tier assignment, eligibility status, and audit fields (applied_years_of_service for tenure mode, applied_points for points mode).

### Assumptions

- The `tenure_based` mode uses the same match formula structure as the existing `graded_by_service` mode but with a distinct configuration key (`tenure_match_tiers`) to support the new tier schema with explicit `match_rate` and `max_deferral_pct` per tier.
- Points are calculated as integer values using `FLOOR` on both age and tenure before summing, per the acceptance criteria.
- The existing `applied_years_of_service` audit field will also be populated for the `tenure_based` mode (reusing the same field since it represents the same underlying data).
- Match rate values in tier configuration are expressed as percentages (e.g., 50 means 50%) and are converted to decimals (0.50) during calculation, consistent with existing service-tier configuration.
- Only one match mode is active per scenario; switching modes does not require clearing previously configured tiers for other modes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A plan administrator can configure and run a points-based match simulation in under 5 minutes using either YAML configuration or the Studio interface.
- **SC-002**: Match amounts calculated under `tenure_based` and `points_based` modes are mathematically correct for 100% of employees across all tier boundaries in a multi-year simulation.
- **SC-003**: All match calculation results include the appropriate audit fields (`applied_points` for points mode, `applied_years_of_service` for tenure mode) for every employee in every simulation year.
- **SC-004**: Existing simulations using `deferral_based` or `graded_by_service` modes produce identical results before and after the change (zero regression).
- **SC-005**: Invalid tier configurations (gaps, overlaps, missing start-at-zero) are rejected with descriptive error messages within 1 second of submission.
- **SC-006**: Multi-year simulations correctly reflect tier changes when employees cross boundaries — at least 95% of boundary-crossing employees show updated match rates in the following simulation year.
