# Feature Specification: Prorate Contributions & Match for Same-Year Enroll → Opt-Out Window

**Feature Branch**: `101-enroll-window-proration`
**Created**: 2026-06-22
**Status**: Draft
**Input**: User description: "can you work on this issue https://github.com/crzyc98/planwise_navigator/issues/307"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Active-window contributions for same-year enroll → opt-out (Priority: P1)

An employee voluntarily enrolls in the plan partway through a simulation year and then opts out later in that **same** year. For the days they were actively enrolled — from their enrollment effective date through their opt-out effective date — they should be credited with employee contributions, even though by year-end they are recorded as not participating.

**Why this priority**: This is the core defect. Today these employees are credited **$0** in contributions because the year-end deferral rate (0, post-opt-out) is multiplied against full-year compensation. That understates plan contributions and corrupts every downstream contribution, balance, and cost metric for anyone who churns through enrollment within a year.

**Independent Test**: Run a single simulation year configured to produce voluntary enrollments and same-year opt-outs. Identify an employee with both a voluntary enrollment event and a later opt-out event in that year, and confirm their recorded employee contribution for the year is greater than zero and proportional to the enrolled fraction of their active employment window.

**Acceptance Scenarios**:

1. **Given** an employee who voluntarily enrolls on July 1 at a 6% deferral rate and opts out on October 1 of the same year, **When** the year's contributions are computed, **Then** the employee is credited a non-zero contribution reflecting roughly the July 1 → October 1 active window at 6%, not $0 and not a full-year amount.
2. **Given** that same employee, **When** the annual snapshot is generated, **Then** their year-end participation status is "not participating" with a deferral rate of 0.
3. **Given** an employee who enrolls and remains enrolled through year-end (no opt-out), **When** contributions are computed, **Then** their contribution is unchanged from current behavior (no regression for the non-opt-out path).

---

### User Story 2 - Employer match follows the active-window contributions (Priority: P1)

The employer match for a same-year enroll → opt-out employee must be computed from the active-window contributions credited in User Story 1, so the match reflects only the period the employee was actually contributing.

**Why this priority**: Match is a direct function of contributions. If contributions are corrected but match still derives from the year-end (zero) rate or from full-year comp, the two records become internally inconsistent and the employer-cost projection is wrong.

**Independent Test**: For the same enroll → opt-out employee from User Story 1, confirm the employer match for the year is greater than zero and consistent with the active-window contribution amount and the configured match formula.

**Acceptance Scenarios**:

1. **Given** an enroll → opt-out employee credited a non-zero active-window contribution, **When** the employer match is computed, **Then** the match is greater than zero and consistent with that contribution and the configured match formula.
2. **Given** a plan year with no match configured, **When** the match is computed for such an employee, **Then** the match is zero without error and contributions remain correctly credited.

---

### User Story 3 - Reconciliation guard becomes enforcing (Priority: P2)

The planned data-quality guard for this behavior should move from advisory to enforcing once the logic is in place, so the build fails if the active-window crediting regresses.

**Why this priority**: It protects the fix permanently, but it depends on User Stories 1 and 2 being implemented first.

**Independent Test**: With the feature implemented, the guard for same-year enroll → opt-out crediting passes at enforcing severity; temporarily reverting the crediting logic causes the build to fail.

**Acceptance Scenarios**:

1. **Given** the active-window crediting is implemented, **When** the full data-quality suite runs, **Then** the same-year enroll → opt-out guard passes at enforcing severity.
2. **Given** a regression that zeroes out active-window contributions, **When** the suite runs, **Then** the guard fails the build.

---

### Edge Cases

- **Enroll and opt-out on the same day**: The active window is effectively zero days; the employee is credited zero (or a single day's) contribution, never negative, and year-end status is not participating.
- **Enroll → opt-out employee who also terminates mid-year**: The active-enrollment window is further bounded by the employment window; crediting reflects the overlap of "enrolled" and "employed," and is never larger than either window alone.
- **Opt-out effective date before the enrollment effective date** (out-of-order or data error): The window is treated as zero/clamped rather than producing a negative contribution.
- **Multiple enroll/opt-out cycles in one year**: Crediting reflects only the period(s) the employee was actively enrolled; year-end status still resolves from the chronologically latest event.
- **New hire who enrolls and opts out in their hire year**: Both the employment-window and enrollment-window prorations apply together; the credited amount respects both bounds.
- **Enrollee who remains enrolled at year-end**: Existing behavior is preserved exactly — no enrollment-window proration is applied (full participation for the year from their enrollment onward, per current semantics).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The contribution calculation MUST credit a same-year voluntary-enroll-then-opt-out employee with employee contributions for the period they were actively enrolled (enrollment effective date through opt-out effective date), rather than crediting zero.
- **FR-002**: The credited contribution for such an employee MUST be proportional to the enrolled fraction of their active employment window, using the deferral rate that was in effect during the active enrollment period.
- **FR-003**: The active-enrollment window used for crediting MUST be bounded by the employee's employment window for the year (hire/year-start through termination/year-end), so crediting never covers days the employee was not employed.
- **FR-004**: The employer match for such an employee MUST be derived from the active-window contributions and the configured match formula, remaining internally consistent with the credited contribution.
- **FR-005**: The year-end annual snapshot MUST continue to record such an employee as not participating with a zero deferral rate (no regression to the already-correct year-end status from feature 095).
- **FR-006**: Employees who enroll and do **not** opt out within the same year MUST retain their current contribution and match behavior with no change.
- **FR-007**: The crediting logic MUST NOT produce negative contributions or matches for degenerate windows (same-day, out-of-order, or zero-length enrollment periods).
- **FR-008**: A permanent automated data-quality guard MUST assert that same-year enroll → opt-out employees have year-end not-participating status with a zero deferral rate **and** a non-zero active-window contribution, and MUST fail the build (enforcing severity) when violated.
- **FR-009**: The behavior MUST hold across multi-year simulations, so an enroll → opt-out cycle in any given year is credited for that year's active window without affecting other years.

### Key Entities *(include if feature involves data)*

- **Enrollment-related event**: A recorded event marking an employee voluntarily enrolling or opting out, each carrying an effective date and (for enrollment) a deferral rate. The chronological sequence of these per employee-year defines the active-enrollment window(s).
- **Active-enrollment window**: The span(s) within a simulation year during which an employee is enrolled — from an enrollment effective date to the next opt-out effective date — intersected with the employee's employment window.
- **Employee-year contribution record**: The per-employee, per-year record of credited employee contributions, whose compensation base must reflect the active-enrollment window for enroll → opt-out employees.
- **Employer match record**: The per-employee, per-year employer match, derived from the contribution record and the configured match formula.
- **Year-end participation snapshot**: The point-in-time record of whether an employee is participating at year-end and at what deferral rate (resolved from the latest enrollment-related event).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of same-year voluntary-enroll-then-opt-out employees are credited a non-zero employee contribution for their active-enrollment window (currently 0%).
- **SC-002**: For every such employee, the credited contribution is within an acceptable tolerance of the expected enrolled-fraction-of-window amount (e.g., enrolled days ÷ active employment days × full-window contribution), verified by the reconciliation guard.
- **SC-003**: 100% of such employees retain year-end "not participating" status with a zero deferral rate (no regression of the feature-095 behavior).
- **SC-004**: Employer match for such employees is non-zero where a match is configured and is internally consistent with the credited contribution in 100% of cases.
- **SC-005**: Employees who enroll without opting out in the same year show no change in credited contribution or match versus the prior behavior (zero regressions on the non-opt-out path).
- **SC-006**: The previously advisory same-year enroll → opt-out data-quality guard runs at enforcing severity and passes on a representative multi-year simulation.

## Assumptions

- The contribution base for the active window is derived by proportionally scaling the existing employment-window compensation base by the enrolled fraction of that window (enrolled days ÷ employed days), rather than introducing a separate day-rate compensation source. This keeps the change additive to the current proration model.
- The deferral rate applied to the active window is the rate carried by the voluntary enrollment event that opened the window; if multiple enrollment events exist in the window, the rate in effect for each sub-period applies.
- "Same-year enroll → opt-out" is identified from enrollment-related events within a single simulation year; opt-outs carried over from prior years are out of scope (they are already not participating at the start of the year).
- Existing year-end participation status resolution (latest event wins) from feature 095 is correct and is not re-implemented here.
- A placeholder guard (`assert_same_year_enroll_optout_window.sql`, advisory severity) is the intended home for the enforcing reconciliation check per the feature-095 contracts.

## Dependencies

- Builds directly on feature `095-fix-enrollment-snapshot` (FR-008, Phase 6, tasks T017–T020), which established correct year-end status for enroll → opt-out employees.
- Requires enrollment and opt-out effective dates to be available per employee-year from recorded events.
- Downstream employer-match records must consume the corrected contribution base.

## Out of Scope

- Changing year-end participation status resolution logic (already handled by feature 095).
- Auto-enrollment opt-out window crediting beyond what shares the same contribution-base mechanism (the fix should generalize, but auto-enrollment-specific behavior is not separately specified here).
- Introducing a new daily/periodic compensation source or changing pay-period modeling.
- UI/Studio changes — this is a calculation-correctness feature with no required interface change.
