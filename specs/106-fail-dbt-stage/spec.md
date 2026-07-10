# Feature Specification: Fail Dbt Stage

**Feature Branch**: `106-fail-dbt-stage`
**Created**: 2026-07-08
**Status**: Draft
**Input**: User description: "Issue #394: Critical failure handling defect where a workflow stage can report failure but the outer simulation orchestrator treats it as completed. Failed foundation, event-generation, state-accumulation, or validation work must stop the simulation, preserve stage/year/error context, and avoid misleading completed runs from partial or invalid data."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stop Failed Simulation Stages (Priority: P1)

As an operations user running simulations, I need any failed workflow stage to stop the simulation immediately so that completed runs only represent valid, fully executed results.

**Why this priority**: This protects simulation correctness and prevents downstream users from making decisions from partial or invalid data.

**Independent Test**: Trigger a stage failure during a simulation run and verify the run is marked failed, later stages do not proceed, and the failure is visible to the operator.

**Acceptance Scenarios**:

1. **Given** a simulation stage reports failure for a specific year, **When** the orchestration layer receives the stage result, **Then** the simulation run stops and is marked failed.
2. **Given** a failed simulation stage, **When** downstream stages are scheduled after the failed stage, **Then** those downstream stages are not executed for that run.
3. **Given** a failed simulation stage, **When** the run status is reviewed, **Then** the status does not indicate successful completion.

---

### User Story 2 - Preserve Failure Context (Priority: P2)

As a developer or support engineer diagnosing a failed simulation, I need the failure report to include the affected stage, simulation year, and error summary so that I can identify the cause without reconstructing the run manually.

**Why this priority**: Clear context shortens diagnosis time and supports auditability for failed batch executions.

**Independent Test**: Trigger a known stage failure and verify the recorded failure details include stage name, year, and error text.

**Acceptance Scenarios**:

1. **Given** a simulation stage fails with an error message, **When** the failure is surfaced, **Then** the failure details include the stage name, simulation year, and error summary.
2. **Given** a user reviews the failed run, **When** they inspect the run details or logs, **Then** the same stage and year context is available consistently.

---

### User Story 3 - Reject Misleading Success Results (Priority: P3)

As a data consumer using simulation outputs, I need invalid or incomplete runs to be excluded from successful result workflows so that reports and audits do not rely on incomplete event lineage.

**Why this priority**: The event-sourced audit trail depends on complete stage execution; incomplete runs should not be treated as reliable results.

**Independent Test**: Run a simulation with a forced validation failure and verify no success-only workflow presents the run as usable output.

**Acceptance Scenarios**:

1. **Given** a simulation fails before all required stages complete, **When** result availability is evaluated, **Then** the run is not presented as successfully completed.
2. **Given** a failed simulation produced partial intermediate outputs, **When** users inspect available runs, **Then** the failed run is clearly distinguishable from completed runs.

### Edge Cases

- A stage returns a failure result without an error message; the run still fails and reports a generic stage failure with stage and year context.
- A stage returns a malformed or incomplete result; the run treats it as a failure rather than assuming success.
- Failure occurs inside an optional observability or timing wrapper; the run still fails and preserves the original stage context.
- A failure occurs after partial outputs were produced; the run status remains failed and does not imply those outputs are valid for decision-making.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST stop a simulation run when any required workflow stage reports an unsuccessful outcome.
- **FR-002**: The system MUST treat missing, malformed, or ambiguous stage outcomes as unsuccessful unless they explicitly indicate success.
- **FR-003**: The system MUST preserve the failed stage name, simulation year, and error summary when reporting a stopped run.
- **FR-004**: The system MUST ensure failed stage outcomes are visible through run status, operational logs, or other run diagnostics used by support teams.
- **FR-005**: The system MUST prevent a run with any failed required stage from being marked or presented as completed successfully.
- **FR-006**: The system MUST avoid executing later required stages for a run after an earlier required stage has failed.
- **FR-007**: The system MUST maintain auditability by making the failure context reproducible from the run record and diagnostics.
- **FR-008**: The system MUST include regression coverage demonstrating that an unsuccessful stage outcome stops the run and surfaces failure context.

### Key Entities *(include if feature involves data)*

- **Simulation Run**: A single execution attempt for a scenario across one or more years, with status, progress, and diagnostics.
- **Workflow Stage**: A required phase of simulation execution, such as preparation, event generation, state accumulation, or validation.
- **Stage Outcome**: The reported result of a workflow stage, including success status, execution context, and failure details when applicable.
- **Failure Context**: The stage name, simulation year, and error summary needed to diagnose and audit a failed run.

## Assumptions

- Required workflow stages are expected to complete successfully before a simulation run can be considered valid.
- A stage outcome that does not explicitly indicate success should not be trusted as successful.
- Existing run status and diagnostics surfaces are the appropriate places for users and support engineers to observe the failure.
- Partial outputs from a failed run may exist, but they must not be treated as completed simulation results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of tested required-stage failure cases, the simulation run stops and is not marked successful.
- **SC-002**: In 100% of tested failure cases, the reported failure includes the affected stage and simulation year.
- **SC-003**: In 100% of tested failure cases with an available error summary, that summary is visible in run diagnostics.
- **SC-004**: Operators can identify the failed stage and year from run diagnostics in under 2 minutes without manually replaying the simulation.
- **SC-005**: No tested failure scenario allows downstream required stages to continue after the first reported stage failure.
