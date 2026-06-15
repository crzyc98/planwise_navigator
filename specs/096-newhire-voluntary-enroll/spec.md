# Feature Specification: New Hires Voluntarily Enroll in Their Hire Year

**Feature Branch**: `096-newhire-voluntary-enroll`
**Created**: 2026-06-15
**Status**: Draft
**Input**: User description: "New hires who are eligible in their hire year do not get voluntary enrollment events until the following simulation year, so they appear as not_participating with a zero deferral rate and no match in their hire-year snapshot."

## Overview

Following the fix in feature 095 (voluntary enrollment events now propagate into the annual snapshot), testing revealed a remaining gap specific to **new hires**. A new hire who is eligible for the retirement plan in their hire year does not receive a voluntary enrollment event in that year. Instead, the enrollment event is generated one simulation year later — once the employee is a continuous active employee with non-zero tenure.

The visible symptom: in the hire-year snapshot the new hire appears as `not_participating` with a zero deferral rate and a zero employer match, even though they are recorded as `eligible` with no waiting period. Only in the following year does the same employee show as participating with their selected deferral rate. This systematically delays plan participation by a full year for every new hire who would have voluntarily enrolled, understating first-year participation, contributions, and projected employer match cost.

This feature ensures that an eligible new hire is **considered** for voluntary enrollment in the same simulation year they are hired — and that the new hires who do enroll are reflected in that hire-year snapshot. **Not all new hires enroll**: new hires participate in the same demographic-based voluntary enrollment rate as everyone else, so only the configured share of eligible new hires should produce a hire-year voluntary enrollment. The defect is that this share is currently effectively 0% in the hire year; the fix makes new hires part of the normal voluntary enrollment population in their hire year rather than enrolling all of them.

### Observed Example

Employee `NH_2025_000004` was hired 2025-01-05 and is `eligible` on the same date (waiting period 0 days). In the 2025 (hire-year) snapshot the employee shows `not_participating`, 0% deferral, $0 match. The employee's voluntary enrollment event is dated 2026-01-15 (simulation year 2026), and only the 2026 snapshot shows them participating at 8%. The expected behavior is that the eligible new hire is included in the voluntary enrollment evaluation for 2025 and, if selected per the configured rate, appears as participating in the 2025 snapshot.

## Clarifications

### Session 2026-06-15

- Q: What effective date should a new hire's hire-year voluntary enrollment event carry? → A: The employee's eligibility date (the same day for immediately-eligible hires; the waiting-period end date otherwise). This date drives hire-year contribution and match proration.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Eligible new hires are part of the hire-year voluntary enrollment population (Priority: P1)

A new hire who becomes eligible for the plan during their hire year (including immediate eligibility) is included in the voluntary enrollment evaluation for that same simulation year, using the same demographic-based enrollment rates applied to continuing employees. The configured share of these new hires enroll; the rest do not. New hires who are selected receive a voluntary enrollment event within their hire year with their selected deferral rate.

**Why this priority**: This is the core defect. Eligible new hires are currently excluded from hire-year voluntary enrollment entirely, delaying participation by a full year for the portion of the incoming workforce who would have enrolled. Fixing this restores first-year participation accuracy, which feeds every downstream contribution and cost figure.

**Independent Test**: Run a single simulation year that includes new hires configured to be immediately eligible, with voluntary enrollment enabled and auto-enrollment disabled. Confirm that the share of eligible new hires who receive a hire-year voluntary enrollment event is non-zero and consistent with the configured voluntary enrollment rates for their demographics — and is not 100% of new hires.

**Acceptance Scenarios**:

1. **Given** a population of new hires who are eligible during simulation year Y, **When** the simulation generates events for year Y, **Then** the new hires are included in the voluntary enrollment evaluation for year Y and the configured demographic share of them produce a voluntary enrollment event effective within year Y.
2. **Given** an incoming class of eligible new hires, **When** year Y completes, **Then** the count of new hires with hire-year voluntary enrollment events is greater than zero, approximately matches the configured voluntary enrollment rate applied to that class, and is less than the full count of eligible new hires.
3. **Given** a new hire who enrolled in their hire year, **When** the next simulation year is generated, **Then** no duplicate or one-year-delayed voluntary enrollment event is created for the enrollment already recorded in the hire year.

---

### User Story 2 - Hire-year voluntary enrollment appears in the hire-year snapshot (Priority: P1)

A new hire who voluntarily enrolled in their hire year is recorded in that year's annual snapshot as participating, carrying their selected deferral rate and receiving the appropriate employer match.

**Why this priority**: The snapshot is the record of record. A correctly generated hire-year enrollment event is only useful if it is reflected in the hire-year snapshot. This story makes the fix observable in the artifact analysts and cost projections rely on, and is inseparable from User Story 1.

**Independent Test**: For the subset of new hires who voluntarily enrolled in their hire year, compare their hire-year snapshot records to their enrollment events. Each must show participating status, the enrollment event's deferral rate, and a non-zero employer match (under a non-zero match formula).

**Acceptance Scenarios**:

1. **Given** a new hire with a hire-year voluntary enrollment event at a 6% deferral rate, **When** the hire-year snapshot is generated, **Then** the employee shows participating status with a 6% deferral rate.
2. **Given** the same new hire under a non-zero match formula, **When** the hire-year snapshot is generated, **Then** the employer match is greater than zero and equals the formula's output for their deferral rate and compensation.
3. **Given** a new hire who voluntarily enrolled in their hire year, **When** the hire-year snapshot is generated, **Then** the employee is not shown as `not_participating` with a zero deferral rate.
4. **Given** a new hire who was eligible but not selected to enroll under the configured rate, **When** the hire-year snapshot is generated, **Then** the employee correctly shows as not participating (the fix does not force-enroll all new hires).

---

### User Story 3 - Hire-year enrollment persists into later years without duplication (Priority: P2)

A new hire who voluntarily enrolled in their hire year continues to be reflected as participating in subsequent years' snapshots (until an opt-out or change event applies), with no second, delayed enrollment event created for the same decision.

**Why this priority**: Multi-year accuracy and the absence of duplicate enrollment events build on the single-year correctness in User Stories 1 and 2. It prevents the new behavior from introducing double-counting or conflicting events across years.

**Independent Test**: Run a multi-year simulation where a new hire voluntarily enrolls in their hire year with no later change events; confirm they remain participating with the same deferral rate in each subsequent year and that exactly one voluntary enrollment event exists for that enrollment.

**Acceptance Scenarios**:

1. **Given** a new hire who voluntarily enrolled in hire year Y and has no later change events, **When** the year Y+1 snapshot is generated, **Then** the employee is still participating with the same deferral rate.
2. **Given** a new hire who voluntarily enrolled in hire year Y, **When** all simulation years are examined, **Then** exactly one voluntary enrollment event exists for that enrollment (no duplicate in year Y+1).

---

### Edge Cases

- **New hire with a waiting period that ends within the hire year**: The new hire becomes eligible partway through the hire year and is included in the voluntary enrollment evaluation from their eligibility date onward; any enrollment event is effective on their eligibility date (the waiting-period end date), so hire-year contributions and match prorate from that date.
- **New hire whose eligibility date falls in the following year**: A new hire who is not yet eligible at year-end is correctly excluded from hire-year voluntary enrollment and first evaluated in the year they become eligible (no behavior change for genuinely-not-yet-eligible hires).
- **New hire who voluntarily enrolls and opts out in the same hire year**: Year-end participation resolves per the existing chronological-latest-event rule (from feature 095): they show as not participating at year-end while still credited with contributions and match for the days they were actively enrolled.
- **New hire terminates in their hire year after enrolling**: The employee still appears as participating with their selected deferral rate in their hire-year snapshot; termination is reflected through their status, not by zeroing participation (consistent with feature 095).
- **Auto-enrollment enabled vs disabled**: When auto-enrollment is enabled and applies to new hires, the auto-enrollment path governs; when auto-enrollment is disabled or does not apply, eligible new hires are still included in voluntary enrollment evaluation in their hire year (closing the current gap where they fall through both paths).
- **Voluntary enrollment globally disabled**: When voluntary enrollment is turned off, no new hires are voluntarily enrolled in their hire year, matching the configured behavior for all employees.
- **Configured rate selection determinism**: New hires must be selected by the same deterministic, seed-reproducible mechanism as other employees, so the same scenario and seed produce the same set of hire-year enrollees.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The simulation MUST include new hires who become eligible during their hire year in the voluntary enrollment evaluation for that same simulation year, using the same demographic-based voluntary enrollment rates applied to continuing eligible employees.
- **FR-002**: The system MUST enroll only the configured share of eligible new hires (per the demographic-based voluntary enrollment rates), not all of them; new hires not selected by the configured rate MUST remain not participating.
- **FR-003**: When an eligible new hire is selected to voluntarily enroll in their hire year, the system MUST generate a voluntary enrollment event whose effective date equals the employee's eligibility date (the hire/immediate-eligibility date when there is no waiting period, or the waiting-period end date otherwise). This effective date governs hire-year contribution and match proration.
- **FR-004**: The hire-year annual snapshot MUST record a new hire who voluntarily enrolled in that year as participating, carrying the deferral rate from their enrollment event.
- **FR-005**: The hire-year annual snapshot MUST compute and record the employer match for such new hires using their selected deferral rate, compensation, and the configured match formula.
- **FR-006**: The system MUST NOT generate a duplicate or one-year-delayed voluntary enrollment event in a later year for an enrollment decision already recorded in the hire year.
- **FR-007**: New hires who are not yet eligible by the end of their hire year MUST NOT be voluntarily enrolled in that year and MUST first be evaluated in the simulation year they become eligible.
- **FR-008**: The treatment of new-hire voluntary enrollment MUST be consistent with continuing-employee voluntary enrollment and with auto-enrollment — eligible new hires MUST NOT be systematically excluded from hire-year participation, deferral rate, or match that they would receive in any later year or that an equivalent continuing employee would receive.
- **FR-009**: A hire-year voluntary enrollment MUST persist into subsequent years' snapshots until a later opt-out or change event modifies it, consistent with feature 095's carry-forward behavior.
- **FR-010**: New-hire enrollment selection MUST be deterministic and reproducible for a given scenario and random seed, so identical configurations produce the identical set of hire-year enrollees.
- **FR-011**: The existing reconciliation between voluntary enrollment events and snapshot participation (feature 095) MUST include hire-year new-hire enrollments, so first-year enrollees are counted in the reconciliation rather than missing from it.
- **FR-012**: The system SHOULD include an automated data-quality check that fails the build when eligible new hires who voluntarily enrolled are absent from their hire-year snapshot participation or are delayed to a later year, guarding against regression of this defect.

### Key Entities *(include if data involved)*

- **New Hire**: An employee whose hire date falls within the current simulation year and who was not present in the baseline workforce; characterized by hire date, eligibility date, waiting period, and demographics (age, compensation, job level).
- **Eligibility Status**: The determination of whether and when an employee may participate in the plan, including the eligibility date relative to the hire year.
- **Voluntary Enrollment Rate**: The configured, demographic-based probability that an eligible employee voluntarily enrolls; new hires are part of the population this rate applies to.
- **Voluntary Enrollment Event**: An immutable record that an employee actively chose to enroll, including the selected deferral rate and the hire-year effective date; for selected new hires this must occur in the hire year.
- **Annual Snapshot Record**: The point-in-time, per-employee, per-year record of record, including participation status, deferral rate, and employer match — required to reflect hire-year enrollment in the hire-year record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The share of eligible new hires who receive a voluntary enrollment event dated within their hire year is greater than zero and approximately matches the configured voluntary enrollment rate for their demographics (currently effectively 0%), and is not 100% of eligible new hires.
- **SC-002**: 100% of new hires who voluntarily enrolled in their hire year appear as participating in that hire-year snapshot, carrying their enrollment event's deferral rate.
- **SC-003**: 0 eligible new hires who voluntarily enroll experience a one-year delay between their enrollment event year and the snapshot year in which they first appear as participating.
- **SC-004**: For 100% of hire-year voluntary enrollees under a non-zero match formula, the hire-year snapshot employer match is greater than zero and equals the formula's output for their deferral rate and compensation.
- **SC-005**: Exactly one voluntary enrollment event exists per new-hire enrollment decision; 0 duplicate or delayed second events are created in the following year.
- **SC-006**: In a multi-year simulation, a new hire who voluntarily enrolled in their hire year with no later change events remains participating with the same deferral rate in every subsequent year (100% persistence).
- **SC-007**: Re-running the same scenario with the same seed produces the identical set of hire-year new-hire enrollees (100% reproducibility).
- **SC-008**: The feature 095 reconciliation passes with hire-year new-hire enrollments included, with zero unexplained discrepancy.

## Assumptions

- The voluntary enrollment selection logic, demographic-based rates, and deferral-rate selection are themselves correct (validated by feature 095); the defect is solely that new hires are evaluated one year too late. New hires enroll at the same configured rate as everyone else — only the configured share enrolls, not all new hires.
- New hires are present and marked active/eligible in the workforce for their hire year (confirmed by the observed snapshot showing `new_hire_active` and `eligible`); the fix concerns when they are evaluated for voluntary enrollment, not whether they exist.
- Eligibility and waiting-period determination already function correctly; this feature uses the existing eligibility date to decide whether a new hire is a hire-year voluntary enrollment candidate.
- "Voluntary enrollment" includes the related explicit-decision enrollment methods (voluntary, proactive, executive) as in feature 095, all of which should be available to eligible new hires in their hire year.
- The employer match formula and configuration are out of scope and assumed correct; this feature only ensures selected hire-year enrollees' deferral rates reach the existing match calculation.
- Auto-enrollment, when enabled and applicable to new hires, continues to govern those new hires; this feature targets the case where eligible new hires currently fall through both auto-enrollment and voluntary enrollment in their hire year.
</content>
