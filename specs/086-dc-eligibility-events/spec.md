# Feature Specification: DC Plan Eligibility Audit Trail

**Feature Branch**: `086-dc-eligibility-events`
**Created**: 2026-05-20
**Status**: Draft
**Input**: https://github.com/crzyc98/planwise_navigator/issues/288

## Clarifications

### Session 2026-05-20

- Q: When an employee's waiting period expires mid-year, what exact date value does the DC_PLAN_ELIGIBILITY event's effective date field record? → A: The exact computed calendar date (`hire_date + waiting_period_days`)
- Q: Are initial census employees (baseline workforce) in scope for DC_PLAN_ELIGIBILITY event generation, or only new hires added during simulation years? → A: All employees including initial census — anyone transitioning to eligible in any simulation year generates an event
- Q: Should employees who become eligible but never enroll (opt out or not subject to auto-enrollment) still receive a DC_PLAN_ELIGIBILITY event? → A: Yes — eligibility events are generated for all eligible employees regardless of whether they enroll
- Q: Should the DC_PLAN_ELIGIBILITY event payload record which specific criteria were evaluated and met (age, waiting period, tenure/1000-hour rule), or just the fact of eligibility? → A: Fact only — record that eligibility was achieved (effective date); individual criteria details are not in the event payload
- Q: Must an employee satisfy all plan eligibility gates (waiting period AND employer eligibility / 1000-hour / tenure rules) before a DC_PLAN_ELIGIBILITY event is generated, or does any single gate suffice? → A: All gates required — employee must satisfy waiting period AND employer eligibility (1000-hour/tenure) rules jointly

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Eligibility Decisions Captured in Audit Trail (Priority: P1)

A compliance officer reviewing simulation output needs to verify that the system correctly identified which employees became eligible for DC plan participation in a given year. Today, eligibility determinations happen invisibly — the system enforces eligibility rules but leaves no record of the determination. After this fix, every employee who crosses the eligibility threshold during a simulation year has a timestamped eligibility event in the event log.

**Why this priority**: This closes a structural gap in the event sourcing guarantee. The system claims full history reconstruction from events, but eligibility — a foundational prerequisite for enrollment — is entirely absent from the event stream. Without this, the audit trail is structurally incomplete regardless of how complete other event types are.

**Independent Test**: Can be fully tested by running a simulation with both known census employees and new hires, then querying `fct_yearly_events` for `DC_PLAN_ELIGIBILITY` events across both groups. Delivers auditable eligibility determinations as a standalone output with no dependency on enrollment behavior.

**Acceptance Scenarios**:

1. **Given** a simulation year with new hires who meet all plan eligibility requirements, **When** the simulation runs, **Then** `fct_yearly_events` contains exactly one `DC_PLAN_ELIGIBILITY` event per newly eligible employee for that year, with an effective date equal to `hire_date + waiting_period_days`
2. **Given** a census employee (present in the baseline workforce) who has not previously been recorded as eligible, **When** the first simulation year runs, **Then** a `DC_PLAN_ELIGIBILITY` event is recorded for that employee if they satisfy the eligibility criteria during that year
3. **Given** an employee hired in a prior year who is still in their waiting period, **When** the waiting period expires during the current simulation year, **Then** a `DC_PLAN_ELIGIBILITY` event is recorded for that employee in the current year with an effective date equal to their exact computed eligibility date
4. **Given** an employee already captured as eligible in a prior simulation year, **When** the simulation runs the current year, **Then** no duplicate `DC_PLAN_ELIGIBILITY` event is generated — only new eligibility transitions are recorded

---

### User Story 2 - Enrollment Events Always Preceded by Eligibility Events (Priority: P2)

A plan administrator needs assurance that the simulation never auto-enrolls an employee who hasn't been documented as eligible. Currently, the system silently gates enrollment on eligibility but leaves no evidence of the eligibility check. After this fix, the event log establishes a verifiable prerequisite chain: eligibility event → enrollment event.

**Why this priority**: Regulatory compliance requires that enrollment follows documented eligibility. Without this prerequisite chain, the simulation cannot be used to validate plan administration correctness — an enrolled employee with no eligibility record is an unexplainable anomaly.

**Independent Test**: Can be fully tested by running a simulation, querying for enrollment events, and verifying each enrolled employee has a preceding eligibility event in the same simulation year.

**Acceptance Scenarios**:

1. **Given** an employee with a `DC_PLAN_ENROLLMENT` event in `fct_yearly_events`, **When** the event log is audited, **Then** a `DC_PLAN_ELIGIBILITY` event for that employee exists in the same simulation year with an effective date no later than the enrollment effective date
2. **Given** an employee who is ineligible (waiting period not yet complete, or minimum age not met), **When** the simulation runs, **Then** no `DC_PLAN_ELIGIBILITY` event is recorded and no `DC_PLAN_ENROLLMENT` event is generated for that employee

---

### User Story 3 - Waiting Period Configuration Produces Observable Output (Priority: P3)

A simulation analyst modeling the impact of plan design changes needs to see how modifying the DC plan waiting period (e.g., from 0 days to 30 days to 365 days) affects which employees become eligible in a given year. Currently, `waiting_period_days` is silently applied but leaves no trace in the event stream — the analyst cannot verify the configuration was actually honored.

**Why this priority**: Configuration traceability is required for simulation reproducibility. If changing a plan design parameter produces no observable difference in the event log, the parameter's effect cannot be independently validated or demonstrated to stakeholders.

**Independent Test**: Can be fully tested by running two otherwise-identical simulations with different waiting period settings and comparing the resulting `DC_PLAN_ELIGIBILITY` event effective dates and counts.

**Acceptance Scenarios**:

1. **Given** a simulation with a zero-day waiting period, **When** a new hire joins on date D, **Then** a `DC_PLAN_ELIGIBILITY` event is recorded with effective date equal to D (hire date itself)
2. **Given** a simulation with a 365-day waiting period, **When** a new hire joins in year N, **Then** the `DC_PLAN_ELIGIBILITY` event is recorded with effective date = hire_date + 365 days, falling in year N+1
3. **Given** two simulations identical except for `waiting_period_days`, **When** both are compared, **Then** the eligibility event effective dates differ by exactly the difference in waiting period days for the same employees

---

### Edge Cases

- An employee hired on December 31 with a 0-day waiting period receives a `DC_PLAN_ELIGIBILITY` event with effective date December 31 of that year (same-day eligibility)
- An employee hired on December 31 with a 365-day waiting period receives a `DC_PLAN_ELIGIBILITY` event with effective date December 30 of the following year (exact computed date, crossing year boundary)
- What happens when an employee is terminated before their waiting period expires — is any eligibility event generated?
- How does the system handle re-hired employees (terminated then rehired) — is the waiting period clock reset from the rehire date?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record a `DC_PLAN_ELIGIBILITY` event in the simulation event log for every employee — including initial census employees and new hires — who transitions from ineligible to eligible status during a simulation year, regardless of whether that employee subsequently enrolls in the plan; eligibility requires all plan gates to be jointly satisfied (waiting period, minimum age, and employer eligibility / 1000-hour / tenure rules)
- **FR-002**: The system MUST record at most one `DC_PLAN_ELIGIBILITY` event per employee per simulation year — no duplicate eligibility events for the same employee in the same year
- **FR-003**: Each `DC_PLAN_ELIGIBILITY` event MUST include the effective eligibility date, the employee identifier, the simulation year, the scenario identifier, and the plan design identifier; the event payload MUST NOT include a per-criterion breakdown of which eligibility rules were satisfied
- **FR-004**: The system MUST ensure that for every `DC_PLAN_ENROLLMENT` event, a `DC_PLAN_ELIGIBILITY` event for the same employee exists in the same simulation year with an effective date no later than the enrollment effective date
- **FR-005**: The eligibility effective date recorded in the `DC_PLAN_ELIGIBILITY` event MUST be the exact computed calendar date (`hire_date + waiting_period_days`), not an approximation such as January 1 or December 31 of the simulation year
- **FR-006**: Eligibility events MUST be generated after hire events and before enrollment events in the simulation pipeline's execution order, preserving the correct causal sequence in the audit trail
- **FR-007**: `DC_PLAN_ELIGIBILITY` events MUST be included in the `fct_yearly_events` fact table alongside all other event types so that full-event-stream queries work without special-casing eligibility
- **FR-008**: The system MUST provide an automated data quality validation that fails if any enrolled employee lacks a prior eligibility event in the same simulation year

### Key Entities

- **Eligibility Determination**: A point-in-time assessment of whether an employee jointly satisfies all DC plan participation requirements — minimum age, waiting period, and employer eligibility (1000-hour / tenure rules) — for a given simulation year; all three gates must be met simultaneously; currently computed but discarded without producing an event
- **DC_PLAN_ELIGIBILITY Event**: An immutable record capturing the moment an employee's eligibility status transitions to eligible; the effective date is the exact computed calendar date (`hire_date + waiting_period_days`); generated independently of enrollment outcome — an eligible employee who opts out still receives this event
- **Enrollment Prerequisite Chain**: The enforced relationship that every `DC_PLAN_ENROLLMENT` event must be preceded by a `DC_PLAN_ELIGIBILITY` event for the same employee in the same year, making the enrollment decision fully traceable

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a simulation run, 100% of employees who meet DC plan eligibility requirements have a corresponding `DC_PLAN_ELIGIBILITY` event in the event log for the year they first became eligible
- **SC-002**: Zero enrollment events exist without a preceding eligibility event for the same employee in the same simulation year — verifiable via automated validation on every simulation run
- **SC-003**: Changing `waiting_period_days` between two otherwise-identical simulations produces `DC_PLAN_ELIGIBILITY` effective dates that differ by exactly the waiting period difference in days for the same employees
- **SC-004**: The complete DC plan lifecycle for a newly hired, auto-enrolled employee is fully reconstructable from the event log alone — with hire, eligibility, and enrollment events appearing in that causal order

## Assumptions

- Eligibility is a one-way transition per simulation: once an employee is eligible, they remain eligible for the duration of the simulation (eligibility revocation is out of scope)
- Only new eligibility transitions (ineligible → eligible) generate events; employees who were eligible in prior simulation years do not generate duplicate eligibility events in subsequent years
- The `plan_eligibility.waiting_period_days` setting is the authoritative waiting period; the top-level `eligibility_waiting_period_days` is treated as an alias for the same setting
- Re-hired employees are treated as new hires for eligibility purposes, resetting the waiting period clock from the rehire date
- Employees who are terminated before their waiting period expires do not receive a `DC_PLAN_ELIGIBILITY` event
