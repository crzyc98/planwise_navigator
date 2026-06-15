# Phase 0 Research: New Hires Voluntarily Enroll in Their Hire Year

**Feature**: 096-newhire-voluntary-enroll
**Date**: 2026-06-15
**Status**: Complete — root cause confirmed empirically against the user's scenario database

## Investigation Summary

The defect was reproduced and root-caused against the scenario database at
`workspaces/049771e9-.../scenarios/d3ab5ad3-.../simulation.duckdb`.

### Empirical findings

| Observation | Evidence |
|-------------|----------|
| New hires never enroll in their hire year | First enrollment year per cohort: NH_2025→2026, NH_2026→2027, NH_2027→2029, NH_2028→2029 (from `fct_yearly_events`) |
| Hire-year new hires are absent from the compensation model | `int_employee_compensation_by_year` has **0** `NH_%` rows in the start year 2025; the NH_2025 cohort first appears in 2026 |
| The voluntary decision engine sources candidates only from that model | `int_voluntary_enrollment_decision.active_workforce` = `SELECT … FROM int_employee_compensation_by_year WHERE simulation_year = current AND employment_status = 'active'` |
| The dedicated new-hire path produces nothing | `int_proactive_voluntary_enrollment` returns **0 rows for all years**; it is gated on `is_eligible_for_auto_enrollment` and a days-7–35 auto-enrollment window that do not apply when auto-enrollment is not enrolling these employees |

### Root cause

`int_voluntary_enrollment_decision` builds its eligible-employee population exclusively from
`int_employee_compensation_by_year`. That compensation model does **not** include an employee in
their hire year — new hires first materialize there the following simulation year. Consequently a
new hire cannot be considered for voluntary enrollment until the year **after** they are hired,
producing the systematic one-year (or more) delay. The path explicitly designed to cover hire-year
new hires (`int_proactive_voluntary_enrollment`) is coupled to auto-enrollment eligibility/window
logic and emits no events when auto-enrollment is not enrolling new hires, leaving the gap uncovered.

This is a *timing/population* defect, not a defect in enrollment-rate selection, deferral-rate
selection, or snapshot propagation (the latter was fixed in feature 095). The snapshot already shows
these employees in their hire year as `new_hire_active`/`eligible`; only the enrollment **decision**
is missing for that year.

## Decisions

### Decision 1: Where to fix — extend the main voluntary decision engine

**Decision**: Add current-year new hires to the candidate population of
`int_voluntary_enrollment_decision`, sourced independently of `int_employee_compensation_by_year`'s
year-lagged availability (from current-year hire events / `int_new_hire_compensation_staging`).

**Rationale**:
- Aligns with the clarified spec: new hires join the *same* demographic-based voluntary enrollment
  population at the *same* configured rate — one coherent decision engine rather than a parallel one.
- Avoids overloading auto-enrollment semantics. The proactive path is intrinsically tied to the
  auto-enrollment window concept; repurposing it for the auto-enrollment-disabled case would conflate
  two distinct behaviors.
- The existing deduplication in `int_enrollment_events` already ranks `voluntary_enrollment` (1) above
  `proactive_voluntary_enrollment` (2), so when both paths fire (auto-enrollment enabled) the voluntary
  decision wins with no double-counting.

**Alternatives considered**:
- *Fix `int_proactive_voluntary_enrollment` to fire without auto-enrollment*: rejected — it would
  decouple a model from the very concept (auto-enrollment window) it is named for, and still leaves
  the main engine blind to new hires.
- *Fix `int_employee_compensation_by_year` to include hire-year new hires*: rejected as the primary
  fix — that model is consumed by many downstream models (compensation, merit, snapshot); changing its
  hire-year population risks broad, unintended ripple effects far beyond enrollment. Out of scope and
  higher-risk than a targeted enrollment fix.

### Decision 2: Effective date of the hire-year enrollment event

**Decision**: Use the employee's **eligibility date** as the enrollment event effective date —
`hire_date + eligibility_waiting_days` (0 by default, i.e., the hire date itself for immediate
eligibility). Per the spec clarification (Session 2026-06-15).

**Rationale**: The eligibility date is the earliest valid participation date, is always within the
hire year for hire-year-eligible employees, and drives correct hire-year contribution/match proration.
The current code path uses `hire_date + auto_enrollment_window_days (45)` for hire-year rows; this is
replaced by the eligibility date for the new-hire voluntary case.

**Alternatives considered**: hire_date+45-day window (current behavior, rejected — couples to
auto-enrollment window and over-delays proration); fixed annual date Jan 15 (rejected — can precede a
mid-year hire date and is invalid).

### Decision 3: Eligibility gating

**Decision**: Only include current-year new hires whose eligibility date falls within the current
simulation year. New hires not yet eligible by year-end are excluded and first evaluated in the year
they become eligible (FR-007). Use the existing `eligibility_waiting_days` variable.

**Rationale**: Matches FR-006/FR-007 and the spec edge cases; reuses existing eligibility configuration
rather than introducing new logic.

### Decision 4: Cross-year duplicate prevention

**Decision**: Rely on the existing `prior_year_enrollments` defensive filter and the
`voluntary > proactive > yoy > auto` deduplication already in `int_enrollment_events`; verify they
correctly suppress any second/delayed enrollment for a new hire who enrolled in their hire year
(FR-006, SC-005).

**Rationale**: The guard already exists; the fix must not regress it. A targeted test asserts exactly
one enrollment event per new-hire enrollment decision.

### Decision 5: Regression guard (data-quality test)

**Decision**: Add a permanent dbt data-quality test that fails the build when an eligible new hire who
voluntarily enrolled in their hire year does not appear as participating in that hire-year snapshot, or
appears only in a later year (FR-012, SC-001/SC-003). Complements the feature-095 reconciliation test.

**Rationale**: Constitution Principle III (Test-First) and the spec's explicit regression-guard
requirement. The test makes the one-year-delay regression detectable in CI.

## Open Questions

None. The single spec clarification (effective date) is resolved; the fix location and mechanism are
confirmed by direct database evidence.

## Constitution Alignment Notes

- **Event Sourcing/Immutability**: fix changes *which year* an enrollment event is generated in, not
  the immutability of events; no events are mutated or deleted. Determinism preserved via the existing
  seeded random columns (`enrollment_random`, `deferral_random`).
- **Modular Architecture / no circular deps**: candidate-source for new hires comes from hire events /
  `int_new_hire_compensation_staging` (upstream), never from `fct_*`; no new circular dependency.
- **Type-Safe**: all references use `{{ ref() }}`; no raw table-name concatenation.
- **Performance**: all added logic is filtered by `{{ var('simulation_year') }}`.
</content>
