# Feature Specification: Preserve Census Enrollment

**Feature Branch**: `main`
**Created**: 2026-07-10
**Status**: Draft
**Input**: User description: "Issue #418: Prevent census-enrolled participants from being treated as never enrolled in year two, re-enrolled at a default contribution rate, and exposed to an inappropriate opt-out after prior simulation-year enrollment history is lost."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preserve Existing Participation (Priority: P1)

As a plan sponsor running a multi-year scenario, I need employees who begin the simulation enrolled through census data to remain recognized as existing participants in later years so that the simulation does not overwrite their participation or expose them to a new-enrollee opt-out.

**Why this priority**: Incorrectly re-enrolling existing participants can change contribution rates and permanently remove valid participation, materially corrupting plan outcomes.

**Independent Test**: Run a two-year scenario containing census-enrolled employees and broad auto-enrollment eligibility, then verify those employees remain enrolled at the start of year two without receiving a duplicate enrollment event or new-enrollee opt-out treatment.

**Acceptance Scenarios**:

1. **Given** an employee is enrolled in the starting census, **When** the simulation advances into year two, **Then** the employee is recognized as previously enrolled and receives no duplicate enrollment event solely because a new simulation year began.
2. **Given** a census-enrolled employee has a contribution rate different from the plan's default enrollment rate, **When** the simulation advances into year two without a legitimate contribution change, **Then** the employee's participation is not reset to the default rate.
3. **Given** a census-enrolled employee remains eligible and has not voluntarily opted out, **When** new-enrollee opt-out behavior is evaluated in year two, **Then** the employee is excluded from that evaluation.

---

### User Story 2 - Preserve Correct Enrollment Decisions (Priority: P2)

As an analyst comparing scenarios, I need enrollment rules to distinguish existing participants from genuinely unenrolled employees so that auto-enrollment and voluntary-enrollment assumptions still apply to the correct population.

**Why this priority**: Fixing existing participants must not suppress valid enrollment events for employees who are truly unenrolled or newly eligible.

**Independent Test**: Run the same multi-year population through scenarios with auto-enrollment enabled and disabled, and verify census participants receive no duplicate enrollment while eligible unenrolled employees continue to receive valid enrollment decisions.

**Acceptance Scenarios**:

1. **Given** auto-enrollment covers all eligible employees, **When** year-two enrollment decisions are generated, **Then** census-enrolled employees are excluded while eligible employees who have never enrolled remain eligible for auto-enrollment.
2. **Given** auto-enrollment is disabled, **When** year-two voluntary-enrollment decisions are generated, **Then** census-enrolled employees are excluded while eligible unenrolled employees remain eligible for voluntary enrollment.
3. **Given** an existing participant legitimately opts out or changes enrollment status during the simulation, **When** later-year decisions are generated, **Then** the employee's recorded event history governs eligibility rather than the starting census status alone.

---

### User Story 3 - Retain Auditable Multi-Year State (Priority: P3)

As a support engineer or model validator, I need each completed simulation year and its enrollment lineage to remain available throughout a multi-year run so that participant outcomes can be reproduced and audited.

**Why this priority**: Preserving historical state prevents hidden year-two corruption and makes anomalous enrollment outcomes diagnosable.

**Independent Test**: Complete a multi-year scenario, inspect its yearly workforce and enrollment history, and verify every completed year remains represented and reconciles to the participant state used for the following year.

**Acceptance Scenarios**:

1. **Given** a scenario completes two or more years, **When** yearly simulation state is reviewed after completion, **Then** each completed year remains available and associated with that scenario.
2. **Given** an employee's prior enrollment state affects a later-year decision, **When** the decision is audited, **Then** the prior state and any intervening enrollment events explain the outcome consistently.
3. **Given** the same scenario inputs, configuration, and random seed, **When** the scenario is rerun, **Then** enrollment decisions and resulting participant states are reproducible.

### Edge Cases

- A census participant is enrolled but has incomplete non-enrollment demographic fields; the participant remains previously enrolled unless an explicit enrollment-status event changes that state.
- A census participant has an explicit opt-out or unenrollment event during year one; later years honor that event rather than restoring the census status.
- A previously unenrolled employee becomes eligible in year two; the employee remains eligible for the applicable enrollment pathway.
- A participant enrolls, opts out, and later becomes eligible for re-enrollment under configured plan rules; the event history, not a duplicate baseline decision, determines the outcome.
- A scenario runs for only one year; starting census participation remains intact and no later-year preservation behavior is required.
- A multi-year scenario resumes after partial execution; completed-year state remains associated with the same scenario and is not mistaken for another run's state.
- Auto-enrollment is disabled; census-enrolled employees are still excluded from voluntary-enrollment decisions intended for never-enrolled employees.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST recognize employees enrolled in the starting census as previously enrolled when making enrollment decisions in every later simulation year.
- **FR-002**: The system MUST NOT create a new enrollment event for an existing census participant solely because the simulation advances to a later year.
- **FR-003**: The system MUST NOT replace an existing participant's contribution rate with a default enrollment rate unless a valid enrollment-change event or configured plan rule requires the change.
- **FR-004**: The system MUST exclude existing participants from opt-out behavior that applies only to newly enrolled employees.
- **FR-005**: The system MUST apply auto-enrollment and voluntary-enrollment rules to genuinely unenrolled employees according to the scenario configuration.
- **FR-006**: The system MUST use recorded simulation events to supersede starting census enrollment state when an employee legitimately enrolls, opts out, or changes enrollment status during the simulation.
- **FR-007**: The system MUST retain the state needed to represent every completed simulation year for the duration of a multi-year scenario run.
- **FR-008**: The system MUST keep retained yearly state and enrollment history isolated to the scenario and run that produced them.
- **FR-009**: The system MUST provide an auditable lineage from an employee's starting enrollment state and enrollment events to each later-year enrollment outcome.
- **FR-010**: The system MUST produce reproducible enrollment outcomes when scenario inputs, configuration, and random seed are unchanged.
- **FR-011**: Regression coverage MUST include a two-year scenario with census-enrolled employees, broad auto-enrollment eligibility, and a non-default census contribution rate.
- **FR-012**: Regression coverage MUST verify that eligible never-enrolled employees continue to receive valid auto-enrollment or voluntary-enrollment decisions after existing-participant protection is applied.

### Key Entities *(include if feature involves data)*

- **Census Participant**: An employee whose starting census record indicates active plan enrollment, including the participant's starting contribution rate and enrollment context.
- **Enrollment State**: An employee's enrolled or unenrolled status for a simulation year, together with its source and relevant contribution information.
- **Enrollment Event**: An immutable simulation decision that enrolls, unenrolls, opts out, or changes the enrollment status or contribution rate of an employee.
- **Yearly Simulation State**: The scenario-specific employee state retained for a completed simulation year and used to support later-year decisions and audit reconstruction.
- **Scenario Run**: A reproducible multi-year execution defined by scenario inputs, configuration, time range, and random seed.

## Assumptions

- Starting census enrollment is authoritative until a later immutable enrollment event changes the participant's status.
- Auto-enrollment opt-out behavior is intended for employees newly enrolled by the applicable enrollment process, not employees already participating at scenario start.
- Existing configured rules for legitimate contribution changes, opt-outs, and re-enrollment remain in scope and must continue to operate.
- The correction applies consistently to Studio-created scenarios and other supported execution paths, regardless of whether they explicitly specify state-clearing behavior.
- Persisted outputs from previously corrupted runs are not retroactively repaired; affected scenarios must be rerun to produce corrected results.
- Cross-run contamination is outside this feature's scope and is tracked separately, while scenario/run isolation remains a required boundary for this correction.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of tested two-year scenarios, census-enrolled employees receive zero duplicate enrollment events in year two when no legitimate enrollment-status change occurred.
- **SC-002**: In 100% of tested scenarios, existing census participants receive zero opt-out events that are attributable to being incorrectly treated as newly enrolled.
- **SC-003**: In 100% of tested scenarios, a census participant's non-default contribution rate remains unchanged across the year boundary unless a valid rule or event changes it.
- **SC-004**: After a completed multi-year run, 100% of simulated years remain represented in the scenario's auditable yearly state.
- **SC-005**: Eligible never-enrolled employees continue to receive the same configured enrollment opportunities in all regression scenarios.
- **SC-006**: For sampled participant records, support engineers can trace a later-year enrollment outcome to the starting census state and subsequent enrollment events in under 5 minutes.
- **SC-007**: Repeated runs with identical inputs, configuration, and random seed produce identical enrollment event counts and participant enrollment outcomes.
