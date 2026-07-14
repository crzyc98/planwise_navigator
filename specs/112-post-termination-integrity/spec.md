# Feature Specification: Post-Termination Event Integrity

**Feature Branch**: `[112-post-termination-integrity]`
**Created**: 2026-07-13
**Status**: Draft
**Input**: User description: "Research and fix the post-termination event-sequence validation failures exposed by rerun provenance report c9e319bd-e1bd-4c03-9210-30ced7f42185: 459 affected events across simulation years 2026–2030."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Establish the Root Cause (Priority: P1)

As a simulation maintainer, I need a reproducible, privacy-safe explanation of which event families are being created after termination and why, so that the correction addresses the generating logic rather than concealing the validation result.

**Why this priority**: The supplied audit report proves that the failures are real records rather than missing provenance, but it intentionally omits employee-level data. A reliable correction requires identifying the affected event families and causal paths first.

**Independent Test**: Reproduce the reported failure pattern in an isolated copy of the scenario inputs and produce safe aggregate diagnostics that account for every affected event without exposing employee identifiers or census attributes.

**Acceptance Scenarios**:

1. **Given** the same archived inputs, effective configuration, and random seed represented by the supplied report, **When** the scenario is investigated in an isolated environment, **Then** the investigation identifies the affected event types, simulation years, termination cohorts, and generating paths and reconciles those categories to the reported affected-record totals.
2. **Given** an event classified as occurring after termination, **When** its generation path is traced, **Then** the investigation determines whether it was generated from current-year state, prior-year state, a new-hire path, or another documented source.
3. **Given** investigation output intended for reviewers or developers, **When** it is inspected, **Then** it contains only safe aggregates and synthetic identifiers and does not expose employee-level census data.

---

### User Story 2 - Prevent Invalid Post-Termination Events (Priority: P1)

As an enterprise reviewer, I need completed simulations to contain no non-termination events dated after an employee's termination date, so that event history and derived workforce state are internally consistent.

**Why this priority**: Post-termination activity makes the event stream unreliable as the source of truth and prevents an otherwise complete run from receiving a fully verified provenance disposition.

**Independent Test**: Run a multi-year simulation with the affected scenario in an isolated environment and verify that event-sequence validation passes with zero affected records in every year while workforce reconciliation remains balanced.

**Acceptance Scenarios**:

1. **Given** an employee who terminates during a simulation year, **When** events for that employee are finalized, **Then** no non-termination event has an effective date later than the termination date.
2. **Given** an employee hired and terminated in the same year, **When** events are finalized, **Then** valid events on or before termination are retained and events after termination are absent.
3. **Given** an employee terminated in a prior year, **When** a later year is simulated, **Then** no employment, compensation, eligibility, enrollment, contribution, or deferral event is generated for that employee unless a separately represented rehire restores active status.
4. **Given** a post-termination violation still exists, **When** validation runs, **Then** the check continues to fail with an error severity and an accurate affected-record count.

---

### User Story 3 - Preserve Determinism and Downstream Integrity (Priority: P2)

As an analyst, I need the correction to preserve deterministic simulation behavior and annual workforce reconciliation, so that removing invalid events does not introduce unexplained changes elsewhere.

**Why this priority**: Event ordering affects accumulated state and later-year outcomes. A local correction is insufficient unless the complete multi-year result remains reproducible and balanced.

**Independent Test**: Execute the corrected scenario twice from identical inputs and compare event aggregates, workforce reconciliation, validation outcomes, and provenance fingerprints.

**Acceptance Scenarios**:

1. **Given** identical census input, seed files, effective configuration, and random seed, **When** the corrected simulation is executed twice, **Then** both runs produce identical event aggregates and annual workforce totals.
2. **Given** each corrected simulation year, **When** opening workforce, hires, terminations, and closing workforce are reconciled, **Then** the annual variance is zero.
3. **Given** event families unrelated to the root cause, **When** results before and after the correction are compared, **Then** any differences are explained by the removal or prevention of invalid post-termination activity.

---

### User Story 4 - Produce a Verifiable Audit Outcome (Priority: P3)

As an enterprise reviewer, I need the provenance report for a corrected completed run to show the event-sequence checks and their affected-record counts accurately, so that I can distinguish a resolved integrity issue from hidden or unavailable evidence.

**Why this priority**: The audit report is the reviewer-facing proof that the underlying simulation defect is resolved, not merely bypassed.

**Independent Test**: Generate a provenance report from the corrected archived run without rerunning it and verify that the report contains complete evidence, passing event-sequence results, balanced reconciliation, and a valid deterministic digest.

**Acceptance Scenarios**:

1. **Given** a corrected completed run with all required provenance, **When** its report is generated, **Then** event-sequence validation is shown as passing with zero affected records for every completed year.
2. **Given** a corrected report with no other failed checks or missing evidence, **When** its disposition is calculated, **Then** it is fully verified.
3. **Given** an existing archived report from before the correction, **When** the feature is implemented, **Then** that report and its archived run evidence remain unchanged.

### Edge Cases

- Multiple termination records exist for one employee in the same year; the earliest effective termination date governs later-event validation and duplicates remain independently detectable.
- A non-termination event occurs on the same calendar date as termination; it is allowed because the available evidence does not establish an invalid after-termination ordering within that date.
- A newly hired employee terminates before another generated event in the hire year.
- An employee terminated in a prior year remains present in a retained snapshot or eligibility population.
- Rehire or reinstatement activity exists; post-termination events remain invalid unless active status is restored by an explicit event supported by the event model.
- An event has a missing or invalid effective date; it remains a separate validation failure and is not treated as a valid sequence.
- A failed or partially completed run contains only some yearly validation results; available results remain associated with their original run and are not inferred from later reruns.
- The same inputs are executed through an alternate supported event-generation mode; the event-sequence invariant remains consistent even if the causal fix is mode-specific.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The investigation MUST reproduce the post-termination validation failures using an isolated simulation environment and the same effective inputs and assumptions represented by the supplied run.
- **FR-002**: The investigation MUST account for affected records by simulation year and event type and reconcile the aggregate total to the validation results.
- **FR-003**: The investigation MUST identify the generating path and state source responsible for each affected event category before corrective behavior is selected.
- **FR-004**: Investigation artifacts MUST exclude employee-level census data, direct identifiers, compensation details, and other personally identifiable information.
- **FR-005**: The system MUST define an event as post-termination when it is a non-termination event for the same employee with an effective date later than that employee's earliest effective termination date in the applicable employment period.
- **FR-006**: The system MUST prevent invalid post-termination events from entering the authoritative event stream rather than merely hiding them from validation or reporting.
- **FR-007**: The correction MUST cover both experienced-employee and same-year new-hire termination paths when the investigation shows they can produce affected events.
- **FR-008**: The correction MUST prevent later-year events for employees whose prior-year state is terminated unless an explicit supported rehire or reinstatement restores active status.
- **FR-009**: Valid events dated before or on the termination date MUST be retained.
- **FR-010**: Event-sequence validation MUST continue to examine the authoritative event stream for every simulated year and MUST report an accurate affected-record count.
- **FR-011**: Event-sequence validation MUST retain error severity when one or more invalid post-termination events exist.
- **FR-012**: The correction MUST NOT change a failed event-sequence result to passing through exclusions, severity reduction, missing counts, or report-disposition changes unless the excluded event is supported by a documented business rule.
- **FR-013**: Annual workforce reconciliation MUST remain balanced after the correction, with expected and actual closing workforce equal for every completed year.
- **FR-014**: Repeated runs with identical effective inputs, configuration, and random seed MUST produce identical corrected event aggregates, validation outcomes, and workforce totals.
- **FR-015**: Differences from the pre-correction baseline MUST be attributable to preventing invalid post-termination activity or to its documented downstream consequences.
- **FR-016**: The correction MUST be validated across the complete affected simulation period rather than through a single-year or partial-model check.
- **FR-017**: Validation MUST cover representative edge configurations for new-hire termination, experienced termination, eligibility, enrollment, deferral escalation, promotion, and compensation events.
- **FR-018**: Supported event-generation modes MUST apply the same post-termination invariant; modes not implicated by the defect MUST be shown not to regress.
- **FR-019**: Existing archived run artifacts, audit reports, run history, and shared development data MUST remain unchanged during investigation and validation.
- **FR-020**: A newly archived corrected run MUST preserve complete validation outcomes in its provenance evidence, including check name, severity, outcome, affected-record count, and overall disposition.
- **FR-021**: The provenance report generated from a corrected archived run MUST retain deterministic digest verification and MUST not substitute evidence from another run.
- **FR-022**: The investigation MUST document the root cause, affected paths, correction boundary, before-and-after aggregate results, and any intentional downstream changes.

### Key Entities

- **Employment Period**: The continuous interval during which an employee is active, bounded by hire or rehire and termination events.
- **Termination Event**: The immutable event establishing the effective end date of an employment period.
- **Candidate Post-Termination Event**: A non-termination event associated with the same employee and employment period whose effective date is evaluated against the termination date.
- **Event-Sequence Validation Result**: The yearly check outcome containing severity, pass/fail state, and the count of candidate events determined to be invalid.
- **Root-Cause Category**: A privacy-safe classification linking affected events to event family, year, employment cohort, state source, and generating path.
- **Corrected Run Evidence**: The archived configuration, inputs, event aggregates, workforce reconciliation, validation outcomes, and digest belonging to a post-correction simulation run.

## Assumptions

- Events on the same calendar date as termination are considered valid because no finer ordering evidence is currently available; only later dates violate this feature's invariant.
- The supplied rerun is the baseline symptom: 73, 95, 106, 94, and 91 affected events for 2026 through 2030 respectively, totaling 459.
- Rehire is outside the immediate defect unless the existing event model already represents it explicitly; the correction must not infer rehire from later activity.
- The authoritative validator remains the arbiter of the final audit disposition; provenance reporting is not changed to make a failing simulation appear verified.
- Research may use employee-level records only inside the isolated diagnostic environment. Persisted diagnostics, tests, documentation, and reports use synthetic data or safe aggregates.

## Dependencies

- Access to the archived run's effective configuration, input fingerprints, random seed, and isolated run database or an equivalent isolated reproduction.
- Existing event-generation, state-accumulation, annual validation, run-archiving, and provenance-report capabilities.
- Representative synthetic fixtures for termination timing and affected event families.

## Out of Scope

- Rewriting or upgrading historical provenance reports.
- Weakening, suppressing, or removing event-sequence validation.
- Introducing employee-level details into provenance reports or user-facing diagnostics.
- Adding a new rehire or reinstatement business process when one is not already represented by the event model.
- Broad redesign of unrelated event generators, workforce analytics, or report presentation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The investigation accounts for 100% of the baseline's 459 affected events using privacy-safe root-cause categories whose yearly totals match the captured validation results.
- **SC-002**: The corrected isolated rerun reports zero invalid post-termination events in each simulation year from 2026 through 2030.
- **SC-003**: Annual workforce reconciliation variance is zero in all five corrected simulation years.
- **SC-004**: Two corrected runs using identical effective inputs and assumptions produce identical yearly event counts, validation outcomes, and workforce reconciliation totals.
- **SC-005**: All targeted termination-timing cases pass, including experienced employees, same-year hires, prior-year terminations, same-day events, and the absence of implicit rehire.
- **SC-006**: The corrected run's audit report contains no unavailable required evidence and independently passes its deterministic digest check.
- **SC-007**: When all other captured validations pass, the corrected completed run is classified as fully verified rather than incomplete or unverifiable.
- **SC-008**: Investigation and validation modify zero archived artifacts, historical reports, run-history records, or shared development datasets.
- **SC-009**: No employee-level identifiers or census attributes appear in persisted diagnostic artifacts, automated-test output, documentation, or provenance reports.
- **SC-010**: Corrected end-to-end simulation time does not regress by more than 10% relative to an equivalent isolated baseline run, excluding normal environmental variance.
