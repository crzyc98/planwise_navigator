# Feature Specification: Voluntary Enrollment Events Reflected in Annual Snapshot

**Feature Branch**: `095-fix-enrollment-snapshot`
**Created**: 2026-06-15
**Status**: Draft
**Input**: User description: "we are seeing voluntary enrollment events created in the simulation, they look good. but they are not impacting the annual snapshot. meaning, we are seeing voluntary enrollment events but we are not seeing these individuals with a deferral rate in the snapshot and are marked as not participating and are not receiving a match."

## Overview

The simulation correctly generates voluntary enrollment events — employees who actively choose to enroll in the retirement plan, each with a selected deferral rate. However, these decisions are not carried through to the annual workforce snapshot, which is the point-in-time record of record used for reporting, plan-cost analysis, and downstream calculations. As a result, employees who voluntarily enrolled appear in the snapshot as non-participants with a zero deferral rate and receive no employer match, understating plan participation and projected plan costs.

This feature ensures that a voluntary enrollment event reliably propagates into the annual snapshot so that the affected employee shows as participating, carries their selected deferral rate, and receives the appropriate employer match.

## Clarifications

### Session 2026-06-15

- Q: How should a voluntary enrollee who terminates mid-year appear in that year's snapshot, and how does that affect reconciliation? → A: They still show as participating with their deferral rate in their final-year snapshot and are counted in the reconciliation (the enrollment event occurred and is immutable; termination is tracked separately).
- Q: What rule resolves multiple same-year enrollment/opt-out events into the snapshot's final participation status and deferral rate? → A: Timing/chronological — the latest enrollment-related event by effective date determines year-end participation status and deferral rate. An employee who voluntarily enrolls and later opts out in the same year shows as not participating at year-end, but is treated as having actively participated (accruing contributions and employer match) for the days between enrollment and opt-out.
- Q: Should this fix include a permanent automated data-quality check that fails the build if voluntary enrollees don't reconcile to the snapshot? → A: Yes — add a permanent automated reconciliation test that fails the build when voluntarily enrolled, non-opted-out employees do not appear as participating with their deferral rate in the snapshot.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Voluntary enrollees appear as participating with their chosen deferral rate (Priority: P1)

A simulation produces voluntary enrollment events for a set of employees, each with a non-zero deferral rate. When the annual snapshot for that simulation year is produced, every employee who has a voluntary enrollment event for that year (and who has not subsequently opted out) is recorded as participating and carries the deferral rate from their enrollment event.

**Why this priority**: This is the core defect. Without it, the snapshot misrepresents who is participating in the plan, which corrupts every downstream participation metric and cost projection. Fixing this single behavior restores the integrity of the record of record.

**Independent Test**: Run a simulation for a single year configured to produce voluntary enrollments, then compare the voluntary enrollment events against the snapshot for the same year. Every voluntary enrollee (not opted out) must show participating status and a deferral rate equal to their enrollment event's deferral rate.

**Acceptance Scenarios**:

1. **Given** an employee with a voluntary enrollment event at a 6% deferral rate in a simulation year, **When** the annual snapshot for that year is generated, **Then** the employee's snapshot record shows participating status with a 6% deferral rate.
2. **Given** an employee who voluntarily enrolled, **When** the snapshot is generated, **Then** the employee is no longer recorded as "not participating" with a zero deferral rate.
3. **Given** a population with a known count of voluntary enrollment events in a year, **When** the snapshot is generated, **Then** the count of participating employees attributable to voluntary enrollment matches the count of voluntary enrollment events (net of opt-outs).

---

### User Story 2 - Voluntary enrollees receive the correct employer match (Priority: P1)

An employee who voluntarily enrolled and is contributing at their selected deferral rate receives the employer match they are entitled to under the configured match formula, reflected in the annual snapshot.

**Why this priority**: Employer match is a primary driver of plan cost. If voluntary enrollees show no contribution, they receive no match, and projected employer cost is understated. This is a direct financial-accuracy issue and is inseparable from User Story 1 for a correct cost picture.

**Independent Test**: For a set of voluntary enrollees with known deferral rates and a known match formula, verify that each employee's employer match in the snapshot equals the match the formula produces for their deferral rate and compensation, and is greater than zero.

**Acceptance Scenarios**:

1. **Given** a voluntary enrollee contributing 6% under a match formula that matches contributions, **When** the snapshot is generated, **Then** the employee's employer match is greater than zero and equals the formula's output for their deferral rate and compensation.
2. **Given** the same voluntary enrollee, **When** the snapshot is generated, **Then** the employee is not shown with a zero employer match.

---

### User Story 3 - Voluntary enrollment carries forward across simulation years (Priority: P2)

An employee who voluntarily enrolled in an earlier simulation year remains a participant in subsequent years' snapshots (until an opt-out or other change event applies), continuing to carry a deferral rate and receive a match.

**Why this priority**: Multi-year accuracy is essential for the simulation's purpose, but it builds on the single-year correctness established by User Stories 1 and 2. A correct single year is the prerequisite; persistence across years is the next layer.

**Independent Test**: Run a multi-year simulation where an employee voluntarily enrolls in year 1 with no later change events, and confirm the employee remains participating with the same deferral rate and a non-zero match in each subsequent year's snapshot.

**Acceptance Scenarios**:

1. **Given** an employee who voluntarily enrolled in year 1 and has no change or opt-out events afterward, **When** the year 2 snapshot is generated, **Then** the employee is still participating with the same deferral rate.
2. **Given** an employee who voluntarily enrolled in year 1 and opted out in year 2, **When** the year 2 snapshot is generated, **Then** the employee is shown as not participating for year 2.

---

### Edge Cases

- **Voluntary enrollment then opt-out in the same year**: Year-end participation status resolves to not participating (latest event wins) with no stale non-zero deferral rate, but the employee is credited with contributions and employer match for the days they were actively enrolled (enrollment effective date through opt-out effective date).
- **Multiple enrollment-related events for one employee in one year**: The snapshot must resolve to a single, consistent participation status and deferral rate (the active enrollment decision), without double-counting.
- **Voluntary enrollment at the configured minimum or maximum deferral rate**: The snapshot deferral rate and resulting match must honor the exact selected rate within configured bounds.
- **New hires who voluntarily enroll in their hire year**: These employees must appear in the snapshot as participating with their deferral rate even though they were not present in the baseline workforce.
- **Voluntary enrollee terminates mid-year**: The employee still appears as participating with their selected deferral rate in their final-year snapshot and is included in the reconciliation count; termination is reflected through the employee's separate status/active flag, not by zeroing out participation.
- **Voluntary enrollment with a zero or absent match formula configured**: Participation status and deferral rate must still be correct even when the resulting match is legitimately zero, so participation and match accuracy are evaluated independently.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The annual snapshot MUST record any employee who has a voluntary enrollment event for the simulation year (and who has not subsequently opted out) as participating in the plan.
- **FR-002**: The annual snapshot MUST record, for each such employee, the deferral rate selected in their voluntary enrollment event.
- **FR-003**: The annual snapshot MUST NOT record a voluntarily enrolled, non-opted-out employee as "not participating" or with a zero deferral rate.
- **FR-004**: The annual snapshot MUST compute and record the employer match for voluntarily enrolled employees using their selected deferral rate, compensation, and the configured match formula.
- **FR-005**: Participation status, deferral rate, and employer match for voluntary enrollees MUST be consistent with one another within a single snapshot record (a participating employee has a non-zero deferral rate, and a match consistent with that rate and the formula).
- **FR-006**: The treatment of voluntary enrollment in the snapshot MUST be consistent with the treatment of auto-enrollment — voluntary enrollees MUST NOT be systematically excluded from participation, deferral rate, or match that auto-enrollees in equivalent circumstances would receive.
- **FR-007**: A voluntary enrollment from a prior simulation year MUST continue to be reflected in later years' snapshots until a subsequent change or opt-out event modifies it.
- **FR-008**: When an employee has multiple enrollment-related events in the same year, the snapshot MUST resolve year-end participation status and deferral rate from the chronologically latest event by effective date. An employee who voluntarily enrolls and later opts out in the same year MUST show as not participating at year-end (no stale non-zero deferral rate), while still accruing contributions and employer match for the period during which they were actively enrolled (between the enrollment effective date and the opt-out effective date).
- **FR-009**: The total count and identities of participating employees in the snapshot MUST reconcile with the voluntary enrollment events (net of opt-outs) generated for that year, so the discrepancy is independently verifiable.
- **FR-010**: The system MUST include a permanent automated data-quality check that fails the build when any voluntarily enrolled, non-opted-out employee does not appear in the snapshot as participating with their selected deferral rate, guarding against regression of this defect.

### Key Entities *(include if feature involves data)*

- **Voluntary Enrollment Event**: An immutable record that an employee actively chose to enroll in the plan in a given simulation year, including the selected deferral rate and the enrollment method (voluntary, as distinct from auto-enrollment).
- **Annual Snapshot Record**: The point-in-time, per-employee, per-year record of record, including participation status, deferral rate, and employer match. This is the artifact currently failing to reflect voluntary enrollment.
- **Participation Status**: The classification of an employee as participating or not participating in the plan for a given year, with the method of participation (voluntary, auto, census/baseline).
- **Deferral Rate**: The percentage of compensation an employee elects to contribute, originating from an enrollment decision and required to be carried into the snapshot.
- **Employer Match**: The employer contribution derived from the employee's deferral rate, compensation, and the configured match formula.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of voluntary enrollment events in a simulation year (net of same-year opt-outs) result in a corresponding "participating" employee in that year's snapshot.
- **SC-002**: For 100% of voluntarily enrolled, non-opted-out employees, the deferral rate in the snapshot equals the deferral rate in their voluntary enrollment event.
- **SC-003**: 0 voluntarily enrolled, non-opted-out employees appear in the snapshot as "not participating" or with a zero deferral rate.
- **SC-004**: For 100% of voluntarily enrolled employees under a non-zero match formula, the employer match in the snapshot is greater than zero and equals the match the configured formula produces for their deferral rate and compensation.
- **SC-005**: In a multi-year simulation, an employee who voluntarily enrolled and had no later change events remains participating with the same deferral rate in every subsequent year's snapshot (100% persistence).
- **SC-006**: The participating-employee count in the snapshot reconciles to the voluntary enrollment event count (net of opt-outs) with zero unexplained discrepancy.
- **SC-007**: A permanent automated data-quality check fails the build whenever a voluntarily enrolled, non-opted-out employee is missing from snapshot participation or carries a deferral rate inconsistent with their enrollment event.

## Assumptions

- "Voluntary enrollment" includes the related explicit-decision enrollment methods produced by the simulation (voluntary, proactive, and executive enrollment) as distinct from auto-enrollment; all are explicit employee decisions that should be reflected in the snapshot.
- The employer match formula and its configuration are correct and out of scope; this feature only ensures voluntary enrollees' deferral rates reach the match calculation so the existing formula is applied to them.
- Opt-out and other enrollment-change events already function correctly; this feature must remain compatible with them and resolve to the net outcome when they co-occur with voluntary enrollment.
- The deferral rates carried by voluntary enrollment events are themselves correct; the defect is in propagation to the snapshot, not in how the rates are selected.
- No change to the configured definition of "participating" is intended beyond ensuring voluntary enrollees meet it; an employee with a non-zero active deferral rate is considered participating.
