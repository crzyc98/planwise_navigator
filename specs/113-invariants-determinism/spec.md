# Feature Specification: Multi-Year Invariant Suite + Determinism Test

**Feature Branch**: `113-invariants-determinism`
**Created**: 2026-07-14
**Status**: Draft
**Input**: User description: "#435 + #436 — Multi-year invariant suite + determinism test (one work item — they share the same tiny-census fixture and CI job). This is the safety net everything else stands on. Your last two production bugs were exactly this class, and determinism is a prerequisite for seed ensembles and multi-plan comparisons to mean anything. Do this first so every feature below lands on top of it."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cross-Year Regression Caught Before Merge (Priority: P1)

A developer changes simulation logic (an event model, a state accumulator, orchestration code) and opens a pull request. Before the change can merge, an automated check runs a short multi-year simulation on a small reference population in an isolated database and verifies a set of cross-year invariants — the properties that must hold for any correct simulation regardless of configuration. If the change breaks a cross-year property (a duplicate enrollment, a lost enrollment state, headcount that no longer reconciles year-over-year), the check fails with a message naming the violated invariant and the offending employees/years.

**Why this priority**: The last two production bugs (issues #418 and #419) were cross-year state bugs invisible to single-year validation. This is the core safety net; everything else in this feature builds on it.

**Independent Test**: Can be fully tested by intentionally introducing a known cross-year defect (e.g., re-emitting an enrollment event for an already-enrolled employee in year 2) and confirming the suite fails with a diagnostic naming that invariant, then reverting and confirming the suite passes.

**Acceptance Scenarios**:

1. **Given** a correct codebase, **When** the invariant suite runs a 3-year simulation on the reference census, **Then** all invariants pass and the check reports success.
2. **Given** a change that causes an employee to receive a second enrollment event in a later year without an intervening opt-out, **When** the suite runs, **Then** it fails and the failure message identifies the duplicate-enrollment invariant, the employee, and the years involved.
3. **Given** a change that drops census-sourced enrollment state in year 2 (the #418 regression), **When** the suite runs, **Then** it fails on the enrollment-preservation invariant.
4. **Given** a change that leaves stale prior-run rows in a simulated year (the #419 regression), **When** the suite runs, **Then** it fails on a year-over-year reconciliation invariant (headcount continuity or event/snapshot consistency).
5. **Given** any invariant failure, **When** the developer inspects the failed run, **Then** the isolated simulation database is available as a downloadable artifact for debugging.

---

### User Story 2 - Reproducibility Is Enforced, Not Just Promised (Priority: P2)

The platform's headline promise is that identical scenarios with the same random seed produce identical results. A developer (or an auditor) can run a verification that executes the same small simulation twice — same configuration, same seed, two separate isolated databases — and confirms the resulting event history and workforce snapshots are identical row-for-row, apart from an explicitly documented list of run-bookkeeping fields. Any accidental nondeterminism introduced by a code change fails this check before it ships.

**Why this priority**: Reproducibility underpins the audit-trail value proposition and is a hard prerequisite for planned features (seed ensembles, multi-plan comparison), but it currently ships as an untested claim. It is P2 only because the invariant suite (P1) provides the fixture and harness it reuses.

**Independent Test**: Can be fully tested by running the determinism check on a correct codebase (passes), then introducing a deliberate nondeterminism (e.g., an unseeded random draw or iteration over an unordered collection in event generation) and confirming the check fails and identifies which table and rows differ.

**Acceptance Scenarios**:

1. **Given** the same configuration and seed, **When** the simulation is executed twice into two separate isolated databases, **Then** the yearly event history is identical row-for-row under a canonical ordering, excluding only the documented exempt fields.
2. **Given** the same configuration and seed, **When** the simulation is executed twice, **Then** the workforce snapshot is identical the same way.
3. **Given** a difference between the two runs, **When** the check fails, **Then** the failure output names the table(s) that differ and shows a bounded sample of differing rows sufficient to start debugging.
4. **Given** the exempt-field list, **When** a reviewer reads the suite's documentation, **Then** each exempt field is listed with a one-line justification for why it may differ between runs.

---

### User Story 3 - Fast Local Feedback for the Development Loop (Priority: P3)

A developer working on simulation logic wants to run the same safety net locally before pushing. The invariant suite and determinism check are runnable with a single standard test command, complete within a coffee-break time budget, never touch the shared development database, and clean up after themselves.

**Why this priority**: The checks only prevent regressions if they run pre-merge in CI; local ergonomics multiply their value but are not required for the safety net to exist.

**Independent Test**: Run the documented single command on a clean checkout; confirm it passes, completes within the time budget, and leaves the shared development database untouched (byte-identical before/after).

**Acceptance Scenarios**:

1. **Given** a clean checkout with a working environment, **When** the developer runs the documented test command, **Then** the full suite (invariants + determinism) completes successfully within 10 minutes on a typical development laptop.
2. **Given** the suite has run, **When** the developer inspects the shared development database, **Then** it has not been created, modified, or locked by the suite.

---

### Edge Cases

- **Reference census hits a thin demographic cell** (e.g., no employees in a band that hazard configuration covers): the suite must still run; the census is designed to populate every age/tenure band and job level so band-dependent logic is actually exercised.
- **Zero events of a given type in a year** (e.g., no promotions in the small population in year 3): invariants must be vacuously satisfied, not error on empty sets.
- **An invariant query itself errors** (missing table/column after a schema change): the suite must fail loudly and distinguishably from an invariant *violation*, so a schema rename isn't misread as a correctness bug.
- **Simulation aborts partway** (year 2 of 3 fails): the suite must report the simulation failure itself rather than misleading invariant failures against a half-built database.
- **Parallel CI jobs**: two suite runs executing concurrently must not interfere (isolated per-run databases and working directories).
- **Determinism across machines**: the check compares two runs on the *same* machine within one job; cross-machine reproducibility is explicitly out of scope for v1 (documented).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a small reference census fixture (approximately 100–500 employees) that populates every configured age band, tenure band, and job level, includes both enrolled and non-enrolled employees at baseline, and is checked into the repository so results are stable over time.
- **FR-002**: The system MUST run a multi-year simulation (minimum 3 consecutive years) on the reference census into an isolated database that is never the shared development database, using a fixed documented configuration and seed.
- **FR-003**: The suite MUST verify **event uniqueness**: every event carries a globally unique identifier across all years, with no duplicates in the full event history.
- **FR-004**: The suite MUST verify **enrollment coherence**: no employee receives more than one enrollment event without an intervening opt-out/unenrollment; enrollment state established in any year (including census-sourced baseline enrollment) persists into subsequent years unless an event explains its change (regression guard for issue #418).
- **FR-005**: The suite MUST verify **year-over-year continuity**: each year's ending active headcount equals the next year's starting headcount, and no employee is simultaneously active and previously terminated without an intervening rehire.
- **FR-006**: The suite MUST verify **event/snapshot consistency**: the point-in-time workforce snapshot for each year contains no rows unexplained by the event history — in particular, no stale rows from prior runs or prior configurations survive into a year's results (regression guard for issue #419).
- **FR-007**: The suite MUST verify **growth exactness**: simulated headcount growth matches the configured target growth rate within the documented exactness/rounding rule of the growth solver, for every simulated year.
- **FR-008**: The suite MUST verify **deferral-rate coherence**: an employee's deferral rate never changes without a corresponding explaining event, and auto-escalation never exceeds its configured cap.
- **FR-009**: The suite MUST execute the identical configuration-and-seed simulation twice into two separate isolated databases and verify the yearly event history and workforce snapshot are identical row-for-row under a canonical ordering.
- **FR-010**: Any field excluded from the determinism comparison MUST appear on an explicit, documented exempt list with a stated justification; the comparison MUST fail on differences in any non-exempt field.
- **FR-011**: Every invariant failure MUST produce a diagnostic naming the violated invariant and identifying the offending rows (employee, year, and relevant values), bounded to a readable sample size.
- **FR-012**: The suite MUST run automatically on every pull request and block merge on failure; on failure, the isolated database(s) MUST be preserved as a retrievable artifact.
- **FR-013**: The suite MUST be runnable locally via a single documented test command, MUST NOT read from or write to the shared development database, and MUST clean up its isolated databases on success.
- **FR-014**: A simulation execution failure (as opposed to an invariant violation) MUST be reported as such, and invariant evaluation MUST NOT run against a partially built database.

### Key Entities

- **Reference census**: The checked-in small population used by both checks; spans all age/tenure bands and job levels, with a mix of enrollment states and compensation levels.
- **Invariant**: A named, always-true property of a correct multi-year simulation, with a definition, a violation diagnostic, and a linkage to the regression it guards (where applicable).
- **Isolated run database**: A per-execution simulation database — disposable, never shared, preserved only as a failure artifact.
- **Exempt-field list**: The documented set of run-bookkeeping fields excluded from determinism comparison, each with a justification.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Re-introducing either of the two most recent production bugs (issues #418 and #419) on a branch causes the suite to fail that branch's pre-merge check — verified once by deliberate reversion during rollout.
- **SC-002**: The full suite (multi-year invariants + determinism double-run) completes in under 10 minutes locally and under 15 minutes in the pre-merge pipeline.
- **SC-003**: Two executions of the same configuration and seed produce zero differing non-exempt values across 100% of rows in the event history and workforce snapshot.
- **SC-004**: The shared development database is byte-identical before and after a full suite run.
- **SC-005**: For any seeded defect from the acceptance scenarios, the failure diagnostic alone (without opening the database) is sufficient to identify the violated invariant, the affected employee(s), and the affected year(s).
- **SC-006**: The suite passes 20 consecutive runs without a flaky (non-code-caused) failure in its first month; any flake found is treated as a determinism bug, not a test problem.

## Assumptions

- **Horizon**: 3 simulated years is sufficient to exercise the cross-year state machinery (both recent regressions manifested by year 2); longer horizons add runtime without adding a new class of coverage.
- **Census size**: 100–500 employees balances demographic-band coverage against runtime; the exact size is an implementation choice within that range.
- **Configuration**: the suite runs one fixed "representative" configuration (auto-enrollment on, auto-escalation on with a cap, a multi-tier match) so the enrollment, escalation, and match machinery are all exercised. Broader configuration coverage is deliberately deferred to the separate edge-config matrix (issue #438).
- **Growth tolerance**: "exact" per the growth solver's documented rounding rule (integer headcounts round; the rule — not a loose percentage tolerance — is the bar).
- **Determinism scope**: same-machine, same-environment reproducibility. Cross-machine/cross-OS bitwise reproducibility is out of scope for v1 and documented as such.
- **Event identifiers**: if event identifiers are randomly generated per run, they are expected to appear on the exempt list with justification; switching to derivable identifiers is a possible follow-up noted in issue #436, not part of this scope.
- **Blocking policy**: the check blocks merges from day one, with no advisory/warn-only phase, because the suite starts from a known-green baseline.
