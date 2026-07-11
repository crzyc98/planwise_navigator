# Feature Specification: Clear Stale Prior-Run State on Scenario Re-Run

**Feature Branch**: `108-clear-stale-rerun-state`
**Created**: 2026-07-10
**Status**: Draft
**Input**: User description: "Issue #419: Re-running a Studio scenario into the same scenario database leaves stale rows from the previous run in the deferral-rate state accumulator, producing phantom 'participating - census enrollment' participants at a 3% deferral in year 2+ for employees who never enrolled in the current run."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Re-Run Reflects Only Current Configuration (Priority: P1)

As a plan analyst iterating on a Studio scenario, I need every re-run of that scenario to produce results derived solely from the current run's configuration and inputs, so that rows left behind by an earlier run with different settings can never appear in — or influence — the new results.

**Why this priority**: Stale state silently corrupts participation and deferral outcomes (e.g., 242 employees flipping to phantom participation at a 3% rate inherited from a prior auto-enrollment run), invalidating scenario comparisons that drive plan-design decisions.

**Independent Test**: Run a scenario with auto-enrollment enabled, then re-run the same scenario database with auto-enrollment disabled, and verify no yearly state row from the first run survives into the second run's results.

**Acceptance Scenarios**:

1. **Given** a scenario database that previously completed a run with auto-enrollment enabled, **When** the same scenario is re-run with auto-enrollment disabled, **Then** no deferral-rate state rows created by the earlier run remain for any simulated year.
2. **Given** a census employee who never enrolls under the current run's configuration, **When** the re-run completes, **Then** that employee is reported as not participating in every simulated year, with no deferral rate inherited from the prior run.
3. **Given** stale prior-run state exists for an intermediate year, **When** later years are built, **Then** the stale state is not carried forward into later years as fresh-looking rows.

---

### User Story 2 - Re-Runs Without Explicit Cleanup Settings Are Safe (Priority: P2)

As a Studio user, I need scenario re-runs to be safe by default — without having to know about or configure any state-clearing options — so that the standard Studio workflow (edit config, re-run) always yields trustworthy results.

**Why this priority**: Studio-created scenario configurations carry no explicit state-clearing directive today, which is exactly the path that produced the contamination; the fix must not depend on users opting in.

**Independent Test**: Re-run a Studio scenario whose configuration contains no state-clearing settings and verify each simulated year's state is fully rebuilt from the current run.

**Acceptance Scenarios**:

1. **Given** a scenario configuration with no explicit state-clearing directive, **When** the scenario is re-run into its existing database, **Then** each simulated year's rows are purged before that year is rebuilt, for all yearly state produced by the simulation — including rows whose keys the current run does not regenerate.
2. **Given** an employee population where the current run legitimately produces state for only a subset of employees in a year, **When** that year is rebuilt, **Then** rows for employees outside that subset (left over from a prior run) do not survive.
3. **Given** a scenario re-run completes, **When** its yearly state is inspected, **Then** every row is attributable to the current run.

---

### User Story 3 - Participation Labels Reflect True Enrollment Lineage (Priority: P3)

As a model validator, I need participation-status labels in workforce reporting to assert an enrollment source only when the enrollment history actually supports it, so that anomalous participation is surfaced as anomalous instead of being disguised as legitimate census enrollment.

**Why this priority**: The misleading "participating - census enrollment" fallback label masked the contamination and made diagnosis harder; even after the purge fix, unexplained participation should never be branded with a specific legitimate source.

**Independent Test**: Construct a snapshot row with a positive deferral rate but no supporting enrollment state, and verify the reported participation detail does not claim census enrollment.

**Acceptance Scenarios**:

1. **Given** an employee whose enrollment history shows a baseline (census) enrollment, **When** the workforce snapshot is produced, **Then** the participation detail may state census enrollment.
2. **Given** an employee with a positive deferral rate but no enrollment record in the enrollment state history, **When** the workforce snapshot is produced, **Then** the participation detail does not claim census enrollment and instead uses a label that identifies the participation source as undetermined.

---

### Edge Cases

- A scenario is re-run with a shorter year range than the prior run (e.g., 2026–2028 after a 2026–2030 run); years outside the new range must not leak stale rows into results or exports built from the same database.
- A re-run is interrupted partway; a subsequent re-run must still fully purge each year it simulates before rebuilding it.
- A scenario configuration explicitly requests a full one-time reset; that behavior continues to work and supersedes per-year purging.
- The first run into a fresh scenario database has nothing to purge; per-year purging must be a no-op rather than an error.
- Multiple scenarios each own their own database (one-DB-per-scenario invariant); purging is scoped to the scenario's own database and must not assume shared-database semantics.
- A yearly state table does not yet exist on first build; purging must tolerate missing tables.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: On every scenario run, the system MUST remove all previously persisted rows for each simulated year from every yearly simulation-state store before rebuilding that year, regardless of whether the current run regenerates the same row keys.
- **FR-002**: The per-year purge MUST apply by default to scenario runs whose configuration contains no explicit state-clearing directive, including all Studio-created scenarios.
- **FR-003**: An explicit, configured full-database reset MUST remain available and continue to take precedence over per-year purging when requested.
- **FR-004**: After a completed re-run, every row in yearly simulation state MUST be attributable to that run; no row created by an earlier run of the scenario may remain for any simulated year.
- **FR-005**: The purge MUST prevent stale prior-run state from propagating forward: a rebuilt year MUST derive its prior-year inputs only from state produced by the current run.
- **FR-006**: The purge MUST tolerate a fresh database (no existing tables or rows) without error.
- **FR-007**: Workforce reporting MUST assert a census/baseline enrollment source in participation detail only when the enrollment state history records a baseline enrollment for that employee.
- **FR-008**: When an employee shows participation (a positive deferral rate) that the enrollment state history cannot explain, workforce reporting MUST use a distinct label that does not attribute the participation to a specific legitimate enrollment source.
- **FR-009**: Regression coverage MUST include the contamination scenario from the issue: run with auto-enrollment enabled, re-run the same scenario database with auto-enrollment disabled, and assert that (a) no yearly deferral state rows predate the second run and (b) never-enrolled census employees remain not participating in every simulated year.
- **FR-010**: The purge MUST be scoped to the scenario's own database and MUST NOT alter data belonging to other scenarios or other databases.

### Key Entities *(include if feature involves data)*

- **Scenario Run**: One execution of a scenario's simulation into that scenario's dedicated database; identified by its configuration, year range, and start time.
- **Yearly Simulation State**: Per-year persisted rows (events, accumulators, snapshots) produced by a run; the unit that must be purged and rebuilt per simulated year.
- **Deferral-Rate State**: An employee's per-year deferral rate, enrollment flag, and rate source; the store where stale prior-run rows survived and propagated.
- **Enrollment State History**: The authoritative per-year record of whether and how an employee enrolled; the reference that participation labels must reconcile against.
- **Participation Detail Label**: The human-readable classification of an employee's participation status and its source in workforce reporting.

## Assumptions

- Feature 107 (merged) already resolves an omitted state-clearing directive to year-scoped cleanup in the orchestrator; this feature verifies that behavior covers every yearly state store implicated in the issue (notably the deferral-rate state accumulator, whose year-2+ rebuild does not regenerate keys for never-enrolled employees) and closes any remaining gaps.
- Purging each simulated year at the start of a run is acceptable because a run always rebuilds every year it simulates; there is no supported partial-year resume path that depends on retaining prior-run rows for a year being simulated.
- Historical databases already contaminated by prior runs are not retroactively repaired; re-running the scenario after the fix produces clean results.
- The companion year-2 mass re-auto-enrollment defect (start-year state wiped by a mid-run full refresh) is tracked separately (addressed under feature 107) and is out of scope here except where the same validation run exercises both.
- The "undetermined participation source" label's exact wording is a reporting detail; the requirement is only that it must not claim census enrollment without supporting enrollment state.

## Implementation Notes & Limitations (post-validation)

- Years outside a shorter re-run's range are surfaced with a run-start warning, not deleted (deleting data outside the requested range is destructive; years before the start year are legitimate prior-year state for mid-range runs). A clean slate requires explicit `setup.clear_tables: true, clear_mode: 'all'`.
- Employees enrolled by a simulation event whose event carries no enrollment method are labeled voluntary (the model's existing fallback), not "unknown source" — under the old logic they were miscounted as census enrollment. "participating - unknown source" is reserved for participation with no enrollment lineage at all and is empty in a clean database; its presence is the contamination signal.
- Test harnesses that seed tables in lieu of dbt builds must opt out explicitly with `setup.clear_tables: false`; unset does not mean disabled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the AE-on-then-AE-off re-run validation, zero rows in yearly deferral state carry a creation time earlier than the second run's start, across all simulated years.
- **SC-002**: In the same validation, 100% of census employees who never enroll under the second run's configuration are reported as not participating in every simulated year.
- **SC-003**: Zero employees are labeled "participating - census enrollment" in any tested scenario unless the enrollment state history records a baseline enrollment for them.
- **SC-004**: Re-running any Studio scenario twice with identical configuration and seed produces identical participation counts and deferral outcomes (re-run determinism is preserved by the purge).
- **SC-005**: The regression suite includes the contamination scenario and passes in an isolated database, keeping the shared development database untouched.
