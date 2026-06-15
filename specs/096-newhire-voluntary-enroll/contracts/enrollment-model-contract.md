# Model & Test Contracts: New Hires Voluntarily Enroll in Their Hire Year

**Feature**: 096-newhire-voluntary-enroll

This feature has no external API. Its "interfaces" are dbt model output contracts and dbt/pytest
data-quality checks. Contracts below are the verifiable agreements the implementation must satisfy.

## Contract 1: `int_voluntary_enrollment_decision` candidate population

**Given** a simulation year Y with current-year new hires who are eligible during Y,
**Then** those new hires MUST appear in `int_voluntary_enrollment_decision` for year Y as candidates
(rows with `will_enroll` ∈ {true, false}), evaluated with the same demographic-based rates as
continuing employees.

- Input change: candidate population includes current-year new hires (from hire events /
  `int_new_hire_compensation_staging`), not only `int_employee_compensation_by_year` rows.
- Output (selected new hires): `proposed_effective_date = employee_hire_date + eligibility_waiting_days`.
- Excluded: new hires whose eligibility date is after year-end Y.

## Contract 2: `int_enrollment_events` hire-year voluntary events

**Given** a current-year new hire with `will_enroll = true`,
**Then** `int_enrollment_events` for year Y MUST emit exactly one row with
`event_type = 'enrollment'`, `event_category = 'voluntary_enrollment'`,
`simulation_year = Y`, `effective_date = eligibility_date`, and the selected deferral rate.
**And** no second/delayed enrollment event for that employee may be produced in Y+1+
(existing `prior_year_enrollments` guard).

## Contract 3: `fct_workforce_snapshot` hire-year participation

**Given** a current-year new-hire voluntary enrollee,
**Then** the year-Y snapshot row MUST show participating status, the enrolled deferral rate, and
(under a non-zero match formula) employer match > 0.

## Contract 4: Data-quality regression test (dbt)

A permanent dbt test (e.g., `test_new_hire_voluntary_enrollment_hire_year.sql`, tag `data_quality`)
MUST FAIL when any eligible new hire who voluntarily enrolled:

- (a) is missing a `voluntary_enrollment` event in their hire year, OR
- (b) first appears as participating in the snapshot in a year later than their enrollment event year, OR
- (c) appears in the hire-year snapshot as `not_participating` / zero deferral despite a hire-year
      voluntary enrollment event.

Test returns 0 rows on success (standard dbt test convention).

## Contract 5: Determinism

Re-running the same scenario + seed MUST produce the identical set of hire-year new-hire enrollees
(SC-007). Verified by an integration test comparing two runs (or by asserting the seeded
`enrollment_random`/`deferral_random` columns are stable for new-hire rows).

## Acceptance trace

| Contract | FRs | Success Criteria |
|----------|-----|------------------|
| 1 | FR-001, FR-002, FR-003, FR-007 | SC-001, SC-003 |
| 2 | FR-003, FR-006 | SC-005 |
| 3 | FR-004, FR-005, FR-008, FR-009 | SC-002, SC-004 |
| 4 | FR-011, FR-012 | SC-001, SC-002, SC-003, SC-008 |
| 5 | FR-010 | SC-007 |
</content>
